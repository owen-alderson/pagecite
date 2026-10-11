import io
import urllib.error

import pymupdf
import pytest

from pagecite import pdf
from pagecite.pdf import PDFError

from .conftest import PAGES, make_pdf


def test_pages_are_split_and_titled(document):
    assert document.page_count == 3
    assert "41.5 GW" in document.pages[0] and "USD 115" in document.pages[1]
    assert document.title == "Battery Storage Outlook"
    assert len(document.sha) == 64


def test_title_falls_back_to_file_name():
    doc = pdf.from_bytes(make_pdf(["Some text"]), "/x/annual-report.pdf", "annual-report")
    assert doc.title == "annual-report"


def test_same_bytes_same_sha(pdf_bytes):
    assert pdf.from_bytes(pdf_bytes, "a").sha == pdf.from_bytes(pdf_bytes, "b").sha


def test_not_a_pdf():
    with pytest.raises(PDFError, match="is not a PDF"):
        pdf.from_bytes(b"<html>nope</html>", "page.html")


def test_damaged_pdf():
    with pytest.raises(PDFError, match="Could not read"):
        pdf.from_bytes(b"%PDF-1.7\n garbage garbage", "broken.pdf")


def test_password_protected_pdf():
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 50), "secret")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    with pytest.raises(PDFError, match="password-protected"):
        pdf.from_bytes(data, "locked.pdf")


def test_has_text():
    assert pdf.from_bytes(make_pdf(PAGES), "a").has_text()
    assert not pdf.from_bytes(make_pdf(["", ""]), "scan").has_text()


def test_load_file(pdf_file):
    doc = pdf.load(str(pdf_file))
    assert doc.source == str(pdf_file) and doc.page_count == 3


def test_load_missing_file(tmp_path):
    with pytest.raises(PDFError, match="No such file"):
        pdf.load(str(tmp_path / "nope.pdf"))


def test_load_directory_is_not_a_file(tmp_path):
    with pytest.raises(PDFError, match="No such file"):
        pdf.load(str(tmp_path))


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_load_url(monkeypatch, pdf_bytes):
    seen = {}

    def urlopen(request, timeout, context):
        seen["url"], seen["ua"], seen["context"] = request.full_url, request.get_header("User-agent"), context
        return FakeResponse(pdf_bytes)

    monkeypatch.setattr(pdf.urllib.request, "urlopen", urlopen)
    doc = pdf.load("https://example.org/papers/battery-outlook.pdf?download=1")
    assert seen["url"].startswith("https://example.org/") and seen["ua"].startswith("pagecite")
    assert seen["context"] is not None
    assert doc.source.startswith("https://") and doc.page_count == 3


def test_url_title_fallback(monkeypatch):
    monkeypatch.setattr(pdf.urllib.request, "urlopen", lambda r, timeout, context: FakeResponse(make_pdf(["x"])))
    assert pdf.load("https://arxiv.org/pdf/1706.03762").title == "1706.03762"
    assert pdf.load("https://example.org/a/Report.PDF?x=1").title == "Report"


def test_url_that_is_not_a_pdf(monkeypatch):
    monkeypatch.setattr(pdf.urllib.request, "urlopen", lambda r, timeout, context: FakeResponse(b"<!doctype html>"))
    with pytest.raises(PDFError, match="is not a PDF"):
        pdf.load("https://example.org/landing")


def test_url_error(monkeypatch):
    def urlopen(request, timeout, context):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(pdf.urllib.request, "urlopen", urlopen)
    with pytest.raises(PDFError, match="Could not download .*no route"):
        pdf.load("https://example.org/x.pdf")


def test_url_too_large(monkeypatch):
    monkeypatch.setattr(pdf, "MAX_BYTES", 10)
    monkeypatch.setattr(pdf.urllib.request, "urlopen", lambda r, timeout, context: FakeResponse(b"%PDF" + b"x" * 50))
    with pytest.raises(PDFError, match="larger than"):
        pdf.fetch("https://example.org/big.pdf")


def test_is_url():
    assert pdf.is_url("https://a.b/c.pdf") and pdf.is_url("http://a.b")
    assert not pdf.is_url("file.pdf") and not pdf.is_url("ftp://x")


def test_find_pdfs(tmp_path):
    for name in ["b.pdf", "a.PDF", "notes.txt"]:
        (tmp_path / name).write_text("x")
    (tmp_path / "sub.pdf").mkdir()
    assert [p.name for p in pdf.find_pdfs(tmp_path)] == ["a.PDF", "b.pdf"]
