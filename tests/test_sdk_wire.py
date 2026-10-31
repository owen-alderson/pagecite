"""The real Anthropic SDK against a mocked HTTP transport: checks the exact request on the wire and
that real response objects (citations included) are read correctly."""

import json

import httpx2
import pytest

from pagecite.ask import Asker
from pagecite.summarize import ClaudeError, Summarizer

from .conftest import GOOD_SUMMARY, anthropic_client, message


def test_summarize_on_the_wire(document):
    seen = {}

    def handler(request):
        seen["url"], seen["headers"], seen["body"] = str(request.url), request.headers, json.loads(request.content)
        return httpx2.Response(200, json=message([{"type": "text", "text": json.dumps(GOOD_SUMMARY)}]))

    summary = Summarizer(anthropic_client(handler)).summarize(document)
    body = seen["body"]
    assert seen["url"].split("?")[0].endswith("/v1/messages")  # anthropic 2.x dropped the "?beta=true" query
    assert "server-side-fallback-2026-07-01" in seen["headers"]["anthropic-beta"]
    assert body["model"] == "claude-opus-5-5" and body["fallbacks"] == "default"
    assert body["output_config"]["effort"] == "medium"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "thinking" not in body and "temperature" not in body
    assert '<page n="2">' in body["messages"][0]["content"]
    assert summary.title == "Battery Storage Outlook" and summary.model == "claude-opus-5-5"


def test_summarize_http_error(document):
    def handler(request):
        return httpx2.Response(529, json={"type": "error", "error": {"type": "overloaded_error", "message": "busy"}})

    with pytest.raises(ClaudeError, match="API error 529"):
        Summarizer(anthropic_client(handler)).summarize(document)


def test_ask_on_the_wire(store, document):
    doc_id = store.add(document)
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json=message([
            {"type": "text", "text": "Pack prices fell to USD 115 per kWh.", "citations": [
                {"type": "search_result_location", "cited_text": "The average pack price fell to USD 115 per kWh",
                 "source": f"doc:{doc_id}#page=2", "title": "Battery Storage Outlook, p. 2",
                 "search_result_index": 1, "start_block_index": 0, "end_block_index": 1}]},
        ]))

    answer = Asker(store, anthropic_client(handler)).ask("prices?", doc_id)
    content = seen["body"]["messages"][0]["content"]
    assert [b["type"] for b in content] == ["search_result"] * 3 + ["text"]
    assert content[2]["cache_control"] == {"type": "ephemeral"}
    assert seen["body"]["output_config"] == {"effort": "low"}
    assert [(c.page, c.text) for c in answer.sources()] == [(2, "The average pack price fell to USD 115 per kWh")]


def test_ask_auth_error(store, document):
    doc_id = store.add(document)

    def handler(request):
        return httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "bad"}})

    with pytest.raises(ClaudeError, match="API key"):
        Asker(store, anthropic_client(handler)).ask("q", doc_id)
