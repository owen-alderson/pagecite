"""Load a PDF from a file, a URL or raw bytes and split it into page texts (pages are 1-indexed)."""

import hashlib
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pymupdf
import truststore

MAX_BYTES = 100 * 1024 * 1024  # refuse anything bigger than this from a URL


class PDFError(Exception):
    pass


@dataclass
class Document:
    sha: str
    title: str
    source: str
    pages: list[str]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def has_text(self) -> bool:
        return any(p.strip() for p in self.pages)


def is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def fetch(url: str, timeout: float = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "pagecite (+https://github.com/owen-alderson/pagecite)"})
    try:
        # The OS trust store, so downloads work on python.org builds that ship without CA certificates.
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            data = response.read(MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise PDFError(f"Could not download {url}: {getattr(e, 'reason', e)}") from e
    if len(data) > MAX_BYTES:
        raise PDFError(f"{url} is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    return data


def from_bytes(data: bytes, source: str, name: str = "") -> Document:
    if not data.lstrip()[:5].startswith(b"%PDF"):
        raise PDFError(f"{source} is not a PDF.")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # pymupdf raises its own error types for damaged files
        raise PDFError(f"Could not read {source}: {e}") from e
    if doc.needs_pass:
        raise PDFError(f"{source} is password-protected.")
    with doc:
        pages = [page.get_text() for page in doc]
        title = ((doc.metadata or {}).get("title") or "").strip()
    return Document(hashlib.sha256(data).hexdigest(), title or name or source, source, pages)


def load(source: str) -> Document:
    """A path or an http(s) URL."""
    if is_url(source):
        name = source.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
        return from_bytes(fetch(source), source, name[:-4] if name.lower().endswith(".pdf") else name)
    path = Path(source).expanduser()
    if not path.is_file():
        raise PDFError(f"No such file: {source}")
    return from_bytes(path.read_bytes(), str(path), path.stem)


def find_pdfs(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
