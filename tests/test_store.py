from pagecite import library
from pagecite.pdf import from_bytes
from pagecite.store import Store, fts_query
from pagecite.summarize import Summarizer, Summary

from .conftest import GOOD_SUMMARY, PAGES, FakeClient, make_pdf


def test_add_is_idempotent_by_content(store, document):
    first = store.add(document)
    assert store.add(document) == first
    assert len(store.docs()) == 1
    assert store.pages(first) == document.pages


def test_new_doc_has_no_summary(store, document):
    doc_id = store.add(document)
    assert store.summary(doc_id) is None and store.doc(doc_id)["summary"] == ""


def test_save_and_load_summary(store, document):
    doc_id = store.add(document)
    summary = Summary.from_json({**GOOD_SUMMARY, "title": "Better Title"}, model="claude-opus-5-5")
    store.save_summary(doc_id, summary)
    assert store.summary(doc_id) == summary
    assert store.doc(doc_id)["title"] == "Better Title" and store.doc(doc_id)["summarized_at"]


def test_doc_by_sha(store, document):
    doc_id = store.add(document)
    assert store.doc_by_sha(document.sha)["id"] == doc_id
    assert store.doc_by_sha("nope") is None and store.doc(99) is None


def test_docs_newest_first(store):
    a = store.add(from_bytes(make_pdf(["alpha"]), "a.pdf", "a"))
    b = store.add(from_bytes(make_pdf(["beta"]), "b.pdf", "b"))
    assert [d["id"] for d in store.docs()] == [b, a]


def test_search_ranks_pages(store, document):
    doc_id = store.add(document)
    hits = store.search("lithium supply constraint")
    assert hits[0]["doc_id"] == doc_id and hits[0]["n"] == 2
    assert "[lithium]" in hits[0]["snippet"]


def test_search_within_one_document(store, document):
    other = store.add(from_bytes(make_pdf(["Lithium mining in Chile and lithium prices"]), "c.pdf", "chile"))
    store.add(document)
    assert {h["doc_id"] for h in store.search("lithium", doc_id=other)} == {other}


def test_search_stemming(store, document):
    store.add(document)
    assert store.search("analyst warnings")[0]["n"] == 2


def test_search_nothing_meaningful(store, document):
    store.add(document)
    assert store.search("the and of") == [] and store.search("") == []


def test_fts_query_is_injection_safe():
    assert fts_query('price" OR NEAR(xy) -- *') == '"price" OR "near" OR "xy"'


def test_store_on_disk(tmp_path, document):
    path = tmp_path / "deep" / "library.db"
    s = Store(path)
    s.add(document)
    s.close()
    assert len(Store(path).docs()) == 1


def test_library_summarize_caches(store, pdf_file):
    client = FakeClient()
    first = library.summarize(str(pdf_file), store, Summarizer(client))
    second = library.summarize(str(pdf_file), store, Summarizer(client))
    assert not first.cached and second.cached and first.doc_id == second.doc_id
    assert len(client.calls) == 1 and second.summary == first.summary


def test_library_summarize_refresh(store, pdf_file):
    client = FakeClient()
    library.summarize(str(pdf_file), store, Summarizer(client))
    again = library.summarize(str(pdf_file), store, Summarizer(client), refresh=True)
    assert not again.cached and len(client.calls) == 2


def test_library_same_content_different_path(store, tmp_path, pdf_bytes):
    for name in ["one.pdf", "two.pdf"]:
        (tmp_path / name).write_bytes(pdf_bytes)
    client = FakeClient()
    library.summarize(str(tmp_path / "one.pdf"), store, Summarizer(client))
    assert library.summarize(str(tmp_path / "two.pdf"), store, Summarizer(client)).cached
    assert len(client.calls) == 1


def test_library_failed_summary_keeps_pages_for_search(store, tmp_path):
    path = tmp_path / "x.pdf"
    path.write_bytes(make_pdf(PAGES))
    client = FakeClient(ValueError("boom"))
    try:
        library.summarize(str(path), store, Summarizer(client))
    except ValueError:
        pass
    assert store.search("lithium") and store.summary(store.docs()[0]["id"]) is None
