"""Ask a question of one document or your whole library. Pages go to Claude as search-result
blocks with citations on, so every sentence of the answer points to a document and a page, and
the cited text is returned by the API itself rather than written by the model.

For one document every page is sent, with a cache breakpoint after the last one, so follow-up
questions about the same PDF read the pages from the prompt cache. Across the library, only the
best-matching pages (full-text search) are sent."""

from dataclasses import dataclass, field

import anthropic

from .store import Store
from .summarize import MAX_CHARS, ClaudeError, call_errors

SYSTEM_PROMPT = """You answer questions about the user's documents using only the pages provided. Each
search result is one page of one document. Be brief and concrete. If the pages don't answer the
question, say so plainly instead of guessing. Keep the document's hedges: an estimate stays an
estimate."""


@dataclass
class Cite:
    doc_id: int
    title: str
    page: int
    text: str


@dataclass
class Part:
    text: str
    cites: list[Cite] = field(default_factory=list)


@dataclass
class Answer:
    parts: list[Part]
    pages_sent: int = 0

    @property
    def text(self) -> str:
        return "".join(p.text for p in self.parts)

    def sources(self) -> list[Cite]:
        """Distinct citations in the order they first appear."""
        seen, out = set(), []
        for p in self.parts:
            for c in p.cites:
                if (c.doc_id, c.page) not in seen:
                    seen.add((c.doc_id, c.page))
                    out.append(c)
        return out


def search_blocks(pages: list[dict], cache: bool = False) -> list[dict]:
    blocks = [
        {
            "type": "search_result",
            "source": f"doc:{p['doc_id']}#page={p['n']}",
            "title": f"{p['title']}, p. {p['n']}",
            "content": [{"type": "text", "text": p["text"].strip() or "(no text on this page)"}],
            "citations": {"enabled": True},
        }
        for p in pages
    ]
    if cache and blocks:
        blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def to_parts(content, pages: list[dict]) -> list[Part]:
    parts = []
    for block in content:
        if block.type != "text":
            continue
        cites = []
        for c in getattr(block, "citations", None) or []:
            if getattr(c, "type", "") != "search_result_location" or not 0 <= c.search_result_index < len(pages):
                continue
            p = pages[c.search_result_index]
            cites.append(Cite(p["doc_id"], p["title"], p["n"], c.cited_text))
        parts.append(Part(block.text, cites))
    return parts


class Asker:
    def __init__(self, store: Store, client: anthropic.Anthropic | None = None, model: str = "claude-opus-5-5"):
        self.store = store
        self._client = client
        self.model = model

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def pages_for(self, question: str, doc_id: int | None, limit: int) -> tuple[list[dict], bool]:
        """The pages to send, and whether they are a whole document (worth caching)."""
        if doc_id is not None:
            doc = self.store.doc(doc_id)
            if doc is None:
                raise ClaudeError(f"No document #{doc_id} in the library.")
            texts = self.store.pages(doc_id)
            if sum(len(t) for t in texts) <= MAX_CHARS:
                return [{"doc_id": doc_id, "n": n, "text": t, "title": doc["title"]} for n, t in enumerate(texts, 1)], True
        return self.store.search(question, limit, doc_id), False

    def ask(self, question: str, doc_id: int | None = None, limit: int = 12) -> Answer:
        pages, whole = self.pages_for(question, doc_id, limit)
        if not pages:
            return Answer([Part("Nothing in your library matches that question.")])
        response = call_errors(lambda: self.client.beta.messages.create(
            model=self.model,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": [*search_blocks(pages, cache=whole), {"type": "text", "text": question}]}],
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ))
        if response.stop_reason == "refusal":
            raise ClaudeError("Claude declined to answer this one.")
        return Answer(to_parts(response.content, pages), len(pages))
