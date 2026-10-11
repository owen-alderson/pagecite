"""Claude reads the page-tagged text of a PDF and returns a structured summary in which every
claim lists its pages and, where there is something to quote, a verbatim quote. The quotes and
numbers are then checked against the PDF text by `verify` (no model involved)."""

import json
from dataclasses import asdict, dataclass, field

import anthropic

from . import verify
from .pdf import Document

MAX_CHARS = 3_000_000  # roughly 750k tokens; longer documents are refused rather than truncated

SYSTEM_PROMPT = """You summarise research documents (papers, consulting and analyst reports, pitch decks)
for a reader who will rely on the summary without rereading the document, so precision matters
more than coverage.

The document is given page by page as <page n="..."> blocks. Text was extracted from the PDF, so
expect broken lines, headers, footers and table cells out of order.

Return:
- title: the document's real title.
- tldr: two or three sentences: what the document is, its main finding or argument, and who
  should care. tldr_pages: the pages that support it.
- arguments: the 3-7 most important claims, findings or recommendations, each as one complete
  sentence in your own words.
- data_points: the most decision-relevant numbers (market sizes, growth rates, results, sample
  sizes). value: the figure exactly as the document writes it, with its unit ("$4.2bn", "37%").
  Skip numbers you cannot tie to a page.
- quotes: 1-3 passages worth keeping verbatim; why: one line on why it matters.
- open_questions: 2-4 things the document leaves unanswered or asserts without support.
- tags: 4-8 lowercase topic tags, hyphenated, no # sign.

Rules:
- pages: the page numbers (from the n attribute) where the support is. Never guess a page.
- quote: copied exactly from one of those pages, 6-40 words, no ellipses unless you skip words,
  no added or changed words. Every argument and data point needs one.
- Only state what the document says. If it hedges, keep the hedge. If a number is an estimate or
  forecast, say so. Leave a section empty rather than stretching."""


def _claims(extra: dict) -> dict:
    props = {**extra, "pages": {"type": "array", "items": {"type": "integer"}}}
    return {"type": "array", "items": {"type": "object", "properties": props,
                                       "required": list(props), "additionalProperties": False}}


S = {"type": "string"}
SCHEMA = {
    "type": "object",
    "properties": {
        "title": S,
        "tldr": S,
        "tldr_pages": {"type": "array", "items": {"type": "integer"}},
        "arguments": _claims({"text": S, "quote": S}),
        "data_points": _claims({"text": S, "value": S, "quote": S}),
        "quotes": _claims({"quote": S, "why": S}),
        "open_questions": _claims({"text": S}),
        "tags": {"type": "array", "items": S},
    },
    "required": ["title", "tldr", "tldr_pages", "arguments", "data_points", "quotes", "open_questions", "tags"],
    "additionalProperties": False,
}


class ClaudeError(Exception):
    pass


@dataclass
class Claim:
    text: str = ""
    pages: list[int] = field(default_factory=list)
    quote: str = ""
    value: str = ""
    why: str = ""


@dataclass
class Summary:
    title: str
    tldr: str
    tldr_pages: list[int] = field(default_factory=list)
    arguments: list[Claim] = field(default_factory=list)
    data_points: list[Claim] = field(default_factory=list)
    quotes: list[Claim] = field(default_factory=list)
    open_questions: list[Claim] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    model: str = ""

    SECTIONS = ("arguments", "data_points", "quotes", "open_questions")

    @classmethod
    def from_json(cls, data: dict, model: str = "") -> "Summary":
        def claims(key):
            out = []
            for c in data.get(key) or []:
                claim = Claim(**{k: c[k] for k in Claim.__dataclass_fields__ if k in c})
                claim.pages = sorted({int(p) for p in claim.pages})
                if claim.text.strip() or claim.quote.strip():
                    out.append(claim)
            return out

        tags = [t.strip().lstrip("#").lower().replace(" ", "-") for t in data.get("tags") or []]
        return cls(
            title=(data.get("title") or "").strip(),
            tldr=(data.get("tldr") or "").strip(),
            tldr_pages=sorted({int(p) for p in data.get("tldr_pages") or []}),
            arguments=claims("arguments"),
            data_points=claims("data_points"),
            quotes=claims("quotes"),
            open_questions=claims("open_questions"),
            tags=[t for t in dict.fromkeys(tags) if t],
            model=data.get("model", model),
        )

    def to_json(self) -> dict:
        return asdict(self)

    def check(self, section: str, claim: Claim, pages: list[str]) -> verify.Check:
        if section == "arguments":
            return verify.check_quote(claim.quote, claim.pages, pages)
        if section == "data_points":
            return verify.worst(verify.check_value(claim.value, claim.pages, pages),
                                verify.check_quote(claim.quote, claim.pages, pages))
        if section == "quotes":
            return verify.check_quote(claim.quote, claim.pages, pages)
        return verify.check_pages(claim.pages, pages)

    def checked(self, pages: list[str]) -> dict[str, list[tuple[Claim, verify.Check]]]:
        return {s: [(c, self.check(s, c, pages)) for c in getattr(self, s)] for s in self.SECTIONS}

    def counts(self, pages: list[str]) -> dict[str, int]:
        out = {verify.VERIFIED: 0, verify.FLAGGED: 0, verify.CITED: 0}
        for rows in self.checked(pages).values():
            for _, check in rows:
                out[check.status] += 1
        return out


def page_blocks(pages: list[str]) -> str:
    return "\n".join(f'<page n="{n}">\n{text.strip() or "(no extractable text on this page)"}\n</page>'
                     for n, text in enumerate(pages, 1))


def call_errors(fn):
    """Turn SDK exceptions into one readable ClaudeError."""
    try:
        return fn()
    except anthropic.AuthenticationError as e:
        raise ClaudeError("Anthropic API key missing or invalid (set ANTHROPIC_API_KEY).") from e
    except anthropic.RateLimitError as e:
        raise ClaudeError("Rate limited by the Anthropic API; try again in a minute.") from e
    except anthropic.APIStatusError as e:
        raise ClaudeError(f"Anthropic API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise ClaudeError("Could not reach the Anthropic API.") from e
    except anthropic.AnthropicError as e:
        raise ClaudeError(f"Anthropic client error: {e}") from e
    except TypeError as e:  # the SDK's only signal for "no credentials at all" (no typed error for it)
        if "authentication method" not in str(e):
            raise
        raise ClaudeError("No Anthropic credentials: set ANTHROPIC_API_KEY, or run `ant auth login`.") from e


class Summarizer:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = "claude-opus-5-5"):
        self._client = client
        self.model = model

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def summarize(self, doc: Document) -> Summary:
        if not doc.has_text():
            raise ClaudeError(f"{doc.source} has no text layer (a scan?). Run it through OCR first.")
        body = page_blocks(doc.pages)
        if len(body) > MAX_CHARS:
            raise ClaudeError(f"{doc.source} is too long to summarise in one pass ({len(body):,} characters).")
        prompt = f"Document: {doc.title} ({doc.page_count} pages)\n\n{body}"
        response = call_errors(lambda: self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            # On a policy decline the API re-runs the request on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ))
        if response.stop_reason == "refusal":
            raise ClaudeError("Claude declined to summarise this document.")
        if response.stop_reason == "max_tokens":
            raise ClaudeError("The summary was cut off (max_tokens).")
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ClaudeError("Claude returned malformed output.") from e
        return Summary.from_json(data, getattr(response, "model", "") or self.model)
