"""Check every claim in a summary against the PDF's own text, with no model involved.

- Pages must exist.
- A quote must appear on the page(s) it cites. Matching ignores case, punctuation, spacing,
  ligatures and words split across lines, but keeps decimal points, so "4.2" never matches "42".
  An ellipsis splits a quote into parts that must appear in order.
- A data point's numbers must all appear on the cited page(s).

Anything that fails is flagged with the reason (and the page it is really on, when it is
somewhere else in the document). Nothing is silently dropped or corrected.
"""

import re
import unicodedata
from dataclasses import dataclass, field

MIN_QUOTE_WORDS = 4

VERIFIED, FLAGGED, CITED = "verified", "flagged", "cited"  # CITED: pages exist, nothing quotable to check


@dataclass
class Check:
    status: str
    reason: str = ""
    found_on: list[int] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status != FLAGGED


def squash(text: str) -> str:
    """Lowercase letters and digits only, keeping a '.' between digits."""
    text = unicodedata.normalize("NFKC", text).replace("­", "").casefold()
    return re.sub(r"(?!(?<=\d)\.(?=\d))[\W_]", "", text)


NUMBER = re.compile(r"\d(?:[\d,]|(?<=\d)[   ](?=\d{3}\b))*(?:\.\d+)?")


def numbers(text: str) -> set[float]:
    out = set()
    for raw in NUMBER.findall(unicodedata.normalize("NFKC", text)):
        try:
            out.add(float(re.sub(r"[,\s  ]", "", raw)))
        except ValueError:
            pass
    return out


def _bad_pages(pages: list[int], page_count: int) -> str:
    if not pages:
        return "no page cited"
    wrong = [p for p in pages if not 1 <= p <= page_count]
    if wrong:
        return f"cites p. {', '.join(map(str, wrong))}, but the document has {page_count} pages"
    return ""


def _contains(haystack: str, quote: str) -> bool:
    pos = 0
    for part in re.split(r"\.\.\.|…", quote):
        part = squash(part)
        if not part:
            continue
        pos = haystack.find(part, pos)
        if pos < 0:
            return False
        pos += len(part)
    return True


def _text(pages: list[str], cited: list[int]) -> str:
    return "".join(squash(pages[n - 1]) for n in sorted(set(cited)))


def locate(quote: str, pages: list[str]) -> list[int]:
    """The page (or pair of consecutive pages) a quote is actually on, or []."""
    for n in range(1, len(pages) + 1):
        if _contains(_text(pages, [n]), quote):
            return [n]
    for n in range(1, len(pages)):
        if _contains(_text(pages, [n, n + 1]), quote):
            return [n, n + 1]
    return []


def check_pages(cited: list[int], pages: list[str]) -> Check:
    bad = _bad_pages(cited, len(pages))
    return Check(FLAGGED, bad) if bad else Check(CITED)


def check_quote(quote: str, cited: list[int], pages: list[str]) -> Check:
    if not quote.strip():
        return Check(FLAGGED, "no supporting quote")
    if len(re.findall(r"\w+", quote)) < MIN_QUOTE_WORDS:
        return Check(FLAGGED, f"quote too short to verify (under {MIN_QUOTE_WORDS} words)")
    bad = _bad_pages(cited, len(pages))
    if not bad and _contains(_text(pages, cited), quote):
        return Check(VERIFIED)
    elsewhere = locate(quote, pages)
    where = "p. " + "–".join(map(str, elsewhere))
    if bad:
        return Check(FLAGGED, f"{bad}; the quote is on {where}" if elsewhere else f"{bad}; quote not found in the document", elsewhere)
    if elsewhere:
        return Check(FLAGGED, f"quote is on {where}, not the cited p. {', '.join(map(str, cited))}", elsewhere)
    return Check(FLAGGED, "quote not found in the document")


def check_value(value: str, cited: list[int], pages: list[str]) -> Check:
    if _bad_pages(cited, len(pages)):
        return check_pages(cited, pages)
    wanted = numbers(value)
    if not wanted:
        if value.strip() and squash(value) in _text(pages, cited):
            return Check(VERIFIED)
        return Check(FLAGGED, f"value {value!r} not found on the cited page")
    have = set().union(*(numbers(pages[n - 1]) for n in set(cited)))
    missing = sorted(wanted - have)
    if missing:
        shown = ", ".join(f"{m:g}" for m in missing)
        return Check(FLAGGED, f"{shown} not on the cited page")
    return Check(VERIFIED)


def worst(*checks: Check) -> Check:
    flagged = [c for c in checks if c.status == FLAGGED]
    if flagged:
        return Check(FLAGGED, "; ".join(c.reason for c in flagged), next((c.found_on for c in flagged if c.found_on), []))
    return Check(VERIFIED) if any(c.status == VERIFIED for c in checks) else Check(CITED)
