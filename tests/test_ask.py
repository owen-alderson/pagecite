import pytest

from pagecite import ask as ask_mod
from pagecite.ask import Asker
from pagecite.pdf import from_bytes
from pagecite.summarize import ClaudeError

from .conftest import FakeClient, cite, make_pdf, response, text_block


@pytest.fixture
def doc_id(store, document):
    return store.add(document)


def answer_response(*blocks):
    return response(content=list(blocks))


def test_one_document_sends_every_page_and_caches_them(store, doc_id):
    client = FakeClient(answer_response(text_block("Prices fell.")))
    Asker(store, client).ask("what happened to prices?", doc_id)
    content = client.calls[0]["messages"][0]["content"]
    results = [b for b in content if b["type"] == "search_result"]
    assert [r["source"] for r in results] == [f"doc:{doc_id}#page={n}" for n in (1, 2, 3)]
    assert results[-1]["cache_control"] == {"type": "ephemeral"}
    assert all("cache_control" not in r for r in results[:-1])
    assert all(r["citations"] == {"enabled": True} for r in results)
    assert content[-1] == {"type": "text", "text": "what happened to prices?"}


def test_library_question_sends_only_matching_pages(store, doc_id):
    store.add(from_bytes(make_pdf(["Wind turbines and offshore farms"]), "wind.pdf", "wind"))
    client = FakeClient(answer_response(text_block("x")))
    answer = Asker(store, client).ask("lithium supply")
    results = [b for b in client.calls[0]["messages"][0]["content"] if b["type"] == "search_result"]
    assert [r["title"] for r in results] == ["Battery Storage Outlook, p. 2"]
    assert "cache_control" not in results[0] and answer.pages_sent == 1


def test_huge_document_falls_back_to_search(monkeypatch, store, doc_id):
    monkeypatch.setattr(ask_mod, "MAX_CHARS", 10)
    client = FakeClient(answer_response(text_block("x")))
    Asker(store, client).ask("lithium", doc_id)
    results = [b for b in client.calls[0]["messages"][0]["content"] if b["type"] == "search_result"]
    assert len(results) == 1 and "cache_control" not in results[0]


def test_no_matches_means_no_call(store, doc_id):
    client = FakeClient()
    answer = Asker(store, client).ask("zebra migration")
    assert "Nothing in your library" in answer.text and client.calls == []


def test_unknown_document(store):
    with pytest.raises(ClaudeError, match="No document #7"):
        Asker(store, FakeClient()).ask("q", 7)


def test_citations_map_to_document_and_page(store, doc_id):
    client = FakeClient(answer_response(
        text_block("Pack prices fell to USD 115 per kWh", [cite(1, "The average pack price fell to USD 115 per kWh")]),
        text_block(", while connection queues are the bottleneck.", [cite(2, "Grid connection queues"), cite(2, "again")]),
    ))
    answer = Asker(store, client).ask("prices and risks?", doc_id)
    assert answer.text == "Pack prices fell to USD 115 per kWh, while connection queues are the bottleneck."
    assert [(c.doc_id, c.page) for c in answer.parts[0].cites] == [(doc_id, 2)]
    assert [(c.page, c.title) for c in answer.sources()] == [(2, "Battery Storage Outlook"), (3, "Battery Storage Outlook")]


def test_bogus_citations_are_ignored(store, doc_id):
    other = type(cite(0, "x"))(type="char_location", search_result_index=0, cited_text="x")
    client = FakeClient(answer_response(text_block("a", [cite(99, "x"), other])))
    assert Asker(store, client).ask("q", doc_id).sources() == []


def test_non_text_blocks_are_skipped(store, doc_id):
    thinking = type(text_block(""))(type="thinking", thinking="")
    client = FakeClient(answer_response(thinking, text_block("Answer.")))
    assert Asker(store, client).ask("q", doc_id).text == "Answer."


def test_refusal(store, doc_id):
    with pytest.raises(ClaudeError, match="declined"):
        Asker(store, FakeClient(response("", stop_reason="refusal"))).ask("q", doc_id)


def test_request_settings(store, doc_id):
    client = FakeClient(answer_response(text_block("x")))
    Asker(store, client, model="claude-opus-5-5").ask("q", doc_id)
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["output_config"] == {"effort": "low"}
    assert call["fallbacks"] == "default"


def test_empty_page_gets_placeholder_text():
    blocks = ask_mod.search_blocks([{"doc_id": 1, "n": 4, "text": "  ", "title": "T"}])
    assert blocks[0]["content"][0]["text"] == "(no text on this page)"
