"""An MCP server over your PDF library, so Claude Desktop, Claude Code or any MCP client can
summarise PDFs with checked citations, search every page you've read, and ask cited questions.
Runs locally over stdio: `pagecite mcp`.

search, documents and read_pages need no Anthropic key: they return page text and the client's own
model does the reasoning. summarize (for a new file) and ask call Claude.
"""

from . import library
from .ask import Asker
from .pdf import PDFError
from .store import Store
from .summarize import Summarizer


class ToolError(Exception):
    pass


def _claim(claim, check) -> dict:
    out = {k: v for k, v in vars(claim).items() if v not in ("", [])}
    out["check"] = check.status
    if check.reason:
        out["reason"] = check.reason
    return out


def _checked(store: Store, doc_id: int) -> dict:
    doc, summary, pages = store.doc(doc_id), store.summary(doc_id), store.pages(doc_id)
    out = {"id": doc_id, "title": summary.title or doc["title"], "source": doc["source"], "pages": doc["page_count"],
           "tldr": summary.tldr, "tldr_pages": summary.tldr_pages, "tags": summary.tags, "counts": summary.counts(pages)}
    for section, rows in summary.checked(pages).items():
        out[section] = [_claim(c, check) for c, check in rows]
    return out


def list_documents(store: Store) -> list[dict]:
    return [{"id": d["id"], "title": d["title"], "source": d["source"], "pages": d["page_count"],
             "summarized": bool(d["summary"])} for d in store.docs()]


def search_pages(store: Store, query: str, limit: int = 10, doc_id: int | None = None) -> list[dict]:
    hits = store.search(query, max(1, min(limit, 50)), doc_id)
    return [{"doc_id": h["doc_id"], "title": h["title"], "page": h["n"], "snippet": h["snippet"]} for h in hits]


def read_pages(store: Store, doc_id: int, pages: list[int]) -> list[dict]:
    doc = store.doc(doc_id)
    if doc is None:
        raise ToolError(f"No document #{doc_id}.")
    texts = store.pages(doc_id)
    wanted = [p for p in dict.fromkeys(pages) if 1 <= p <= len(texts)][:20]
    if not wanted:
        raise ToolError(f"Document #{doc_id} has pages 1-{len(texts)}.")
    return [{"page": p, "text": texts[p - 1]} for p in wanted]


def summarize(store: Store, summarizer: Summarizer, source: str, refresh: bool = False) -> dict:
    try:
        result = library.summarize(source, store, summarizer, refresh)
    except PDFError as e:
        raise ToolError(str(e)) from e
    return _checked(store, result.doc_id) | {"from_cache": result.cached}


def ask(asker: Asker, question: str, doc_id: int | None = None) -> dict:
    answer = asker.ask(question, doc_id)
    return {"answer": answer.text,
            "sources": [{"doc_id": c.doc_id, "title": c.title, "page": c.page, "cited_text": c.text} for c in answer.sources()]}


def build_server(store: Store, summarizer: Summarizer, asker: Asker):
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(
        "pagecite",
        instructions=(
            "The user's library of PDFs (papers, reports, decks) with page-level text and summaries. Every "
            "summary claim cites pages; check='verified' means its quote and numbers were found on that page, "
            "'flagged' means they were not (reason given). Cite documents by title and page as p. N."
        ),
    )

    @server.tool(description="List the PDFs in the library, newest first.")
    def documents() -> list[dict]:
        return list_documents(store)

    @server.tool(description="Full-text search over every page of every PDF (or one document). Returns doc id, title, page and a snippet.")
    def search(query: str, limit: int = 10, doc_id: int | None = None) -> list[dict]:
        return search_pages(store, query, limit, doc_id)

    @server.tool(description="The full text of up to 20 pages of one document.")
    def read(doc_id: int, pages: list[int]) -> list[dict]:
        return read_pages(store, doc_id, pages)

    @server.tool(description="Summarise a PDF (local path or http(s) URL): TL;DR, arguments, data points, quotes, open "
                             "questions, each with pages and a verification result. Reuses the stored summary unless refresh.")
    def summarize_pdf(source: str, refresh: bool = False) -> dict:
        return summarize(store, summarizer, source, refresh)

    @server.tool(description="Ask a question of one document (doc_id) or the whole library. The answer cites document and page.")
    def ask_library(question: str, doc_id: int | None = None) -> dict:
        return ask(asker, question, doc_id)

    return server
