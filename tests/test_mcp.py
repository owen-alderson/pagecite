import pytest
from mcp import Client

from pagecite import mcp_server
from pagecite.ask import Asker
from pagecite.summarize import ClaudeError, Summarizer

from .conftest import FakeClient, cite, response, text_block


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture
def parts(store, client):
    return store, Summarizer(client), Asker(store, client)


def test_summarize_returns_checked_claims(parts, pdf_file):
    store, summarizer, _ = parts
    out = mcp_server.summarize(store, summarizer, str(pdf_file))
    assert out["title"] == "Battery Storage Outlook" and out["pages"] == 3 and not out["from_cache"]
    assert out["counts"] == {"verified": 5, "flagged": 0, "cited": 1}
    assert out["data_points"][0] == {"text": "Worldwide grid-scale battery capacity.", "pages": [1],
                                     "quote": "Grid-scale battery capacity reached 41.5 GW worldwide",
                                     "value": "41.5 GW", "check": "verified"}
    assert mcp_server.summarize(store, summarizer, str(pdf_file))["from_cache"]


def test_summarize_bad_source(parts, tmp_path):
    store, summarizer, _ = parts
    with pytest.raises(mcp_server.ToolError, match="No such file"):
        mcp_server.summarize(store, summarizer, str(tmp_path / "x.pdf"))


def test_flagged_claims_carry_a_reason(parts, pdf_file, client):
    import json

    from .conftest import GOOD_SUMMARY

    client.queue.append(response(json.dumps({**GOOD_SUMMARY, "open_questions": [{"text": "q", "pages": [8]}]})))
    store, summarizer, _ = parts
    out = mcp_server.summarize(store, summarizer, str(pdf_file))
    assert out["open_questions"] == [{"text": "q", "pages": [8], "check": "flagged",
                                      "reason": "cites p. 8, but the document has 3 pages"}]


def test_documents_search_and_read(parts, document):
    store = parts[0]
    doc_id = store.add(document)
    assert mcp_server.list_documents(store) == [{"id": doc_id, "title": "Battery Storage Outlook",
                                                 "source": "battery-outlook.pdf", "pages": 3, "summarized": False}]
    hits = mcp_server.search_pages(store, "lithium")
    assert hits[0]["page"] == 2 and "[lithium]" in hits[0]["snippet"]
    assert len(mcp_server.search_pages(store, "battery grid price", limit=500)) <= 50
    pages = mcp_server.read_pages(store, doc_id, [3, 3, 1, 99])
    assert [p["page"] for p in pages] == [3, 1] and "bottleneck" in pages[0]["text"]


def test_read_errors(parts, document):
    store = parts[0]
    doc_id = store.add(document)
    with pytest.raises(mcp_server.ToolError, match="No document #42"):
        mcp_server.read_pages(store, 42, [1])
    with pytest.raises(mcp_server.ToolError, match="has pages 1-3"):
        mcp_server.read_pages(store, doc_id, [0, 4])


def test_ask(parts, document, client):
    store, _, asker = parts
    doc_id = store.add(document)
    client.queue.append(response(content=[text_block("Queues.", [cite(2, "Grid connection queues")])]))
    out = mcp_server.ask(asker, "risks?", doc_id)
    assert out == {"answer": "Queues.", "sources": [{"doc_id": doc_id, "title": "Battery Storage Outlook",
                                                     "page": 3, "cited_text": "Grid connection queues"}]}


def test_ask_unknown_doc(parts):
    with pytest.raises(ClaudeError):
        mcp_server.ask(parts[2], "q", 5)


async def test_server_over_the_mcp_protocol(parts, pdf_file, document):
    """A real MCP client talking to the real server in-process."""
    store, summarizer, asker = parts
    server = mcp_server.build_server(store, summarizer, asker)
    async with Client(server) as mcp:
        tools = {t.name for t in (await mcp.list_tools()).tools}
        assert tools == {"documents", "search", "read", "summarize_pdf", "ask_library"}
        result = await mcp.call_tool("summarize_pdf", {"source": str(pdf_file)})
        assert not result.is_error and "Battery Storage Outlook" in result.content[0].text
        hits = await mcp.call_tool("search", {"query": "lithium"})
        assert not hits.is_error and "lithium" in hits.content[0].text
        bad = await mcp.call_tool("read", {"doc_id": 99, "pages": [1]})
        assert bad.is_error
