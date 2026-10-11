"""SQLite library: every PDF you've read (keyed by its SHA-256, so the same file is never summarised
twice), its page texts, full-text indexed (FTS5), and its summary."""

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .pdf import Document
from .summarize import Summary

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
    id INTEGER PRIMARY KEY,
    sha TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    summary TEXT NOT NULL DEFAULT '',   -- JSON, '' until summarised
    added_at TEXT NOT NULL,
    summarized_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS pages (
    doc_id INTEGER NOT NULL REFERENCES docs(id) ON DELETE CASCADE,
    n INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (doc_id, n)
);
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    text, doc_id UNINDEXED, n UNINDEXED, tokenize = 'porter unicode61'
);
"""

STOPWORDS = set(
    "a an and are as at be but by did do does for from had has have how i if in into is it its me my of on or "
    "our so than that the their them then there these they this to was we were what when where which who whom "
    "why will with you your about any can could should would just also not no".split()
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fts_query(query: str) -> str:
    """A safe FTS5 query: any of the meaningful words, each quoted so user text can't inject syntax."""
    words = [w for w in dict.fromkeys(re.findall(r"\w+", query.lower())) if len(w) > 1 and w not in STOPWORDS]
    return " OR ".join(f'"{w}"' for w in words)


class Store:
    def __init__(self, path: Path | str = ":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # The MCP server runs tools on worker threads; sqlite3 serialises access to one connection.
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def _all(self, sql: str, args=()) -> list[dict]:
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def _one(self, sql: str, args=()) -> dict | None:
        row = self.db.execute(sql, args).fetchone()
        return dict(row) if row else None

    def add(self, doc: Document) -> int:
        """Store a document's pages; returns its id. A file already in the library keeps its id."""
        existing = self._one("SELECT id FROM docs WHERE sha = ?", (doc.sha,))
        if existing:
            return existing["id"]
        with self.db:
            cur = self.db.execute("INSERT INTO docs (sha, title, source, page_count, added_at) VALUES (?,?,?,?,?)",
                                  (doc.sha, doc.title, doc.source, doc.page_count, now()))
            doc_id = cur.lastrowid
            rows = [(doc_id, n, text) for n, text in enumerate(doc.pages, 1)]
            self.db.executemany("INSERT INTO pages (doc_id, n, text) VALUES (?,?,?)", rows)
            self.db.executemany("INSERT INTO pages_fts (doc_id, n, text) VALUES (?,?,?)", rows)
        return doc_id

    def save_summary(self, doc_id: int, summary: Summary) -> None:
        with self.db:
            self.db.execute("UPDATE docs SET summary = ?, summarized_at = ?, title = ? WHERE id = ?",
                            (json.dumps(summary.to_json()), now(), summary.title or self.doc(doc_id)["title"], doc_id))

    def doc(self, doc_id: int) -> dict | None:
        return self._one("SELECT * FROM docs WHERE id = ?", (doc_id,))

    def doc_by_sha(self, sha: str) -> dict | None:
        return self._one("SELECT * FROM docs WHERE sha = ?", (sha,))

    def docs(self) -> list[dict]:
        return self._all("SELECT * FROM docs ORDER BY added_at DESC, id DESC")

    def summary(self, doc_id: int) -> Summary | None:
        d = self.doc(doc_id)
        return Summary.from_json(json.loads(d["summary"])) if d and d["summary"] else None

    def pages(self, doc_id: int) -> list[str]:
        return [r["text"] for r in self._all("SELECT text FROM pages WHERE doc_id = ? ORDER BY n", (doc_id,))]

    def search(self, query: str, limit: int = 10, doc_id: int | None = None) -> list[dict]:
        """Best-matching pages (BM25) across the library, or within one document."""
        match = fts_query(query)
        if not match:
            return []
        where = "AND f.doc_id = ?" if doc_id is not None else ""
        args = (match, doc_id, limit) if doc_id is not None else (match, limit)
        return self._all(
            f"""SELECT f.doc_id, f.n, f.text, d.title, bm25(pages_fts) AS rank,
                       snippet(pages_fts, 0, '[', ']', ' … ', 16) AS snippet
                FROM pages_fts f JOIN docs d ON d.id = f.doc_id
                WHERE pages_fts MATCH ? {where} ORDER BY rank LIMIT ?""",
            args,
        )
