import json

from pagecite import render
from pagecite.summarize import Summary

from .conftest import GOOD_SUMMARY

DOC = {"title": "battery-outlook", "source": "battery-outlook.pdf", "page_count": 3, "summarized_at": "2026-10-11T10:00:00+00:00"}

BAD = {**GOOD_SUMMARY, "arguments": [
    {"text": "Prices fell.", "pages": [1], "quote": "The average pack price fell to USD 115 per kWh"},
]}


def test_pages_label():
    assert render.pages_label([3]) == "p. 3"
    assert render.pages_label([1, 4]) == "pp. 1, 4"
    assert render.pages_label([]) == "(no page)"


def test_terminal_shows_counts_marks_and_quotes(document):
    out = render.terminal(Summary.from_json(GOOD_SUMMARY, model="claude-opus-5-5"), DOC, document.pages)
    assert out.splitlines()[0] == "Battery Storage Outlook"
    assert "battery-outlook.pdf · 3 pages · claude-opus-5-5" in out
    assert "✓ 5 verified   ⚠ 0 flagged   · 1 page-cited only" in out
    assert "  ✓ 41.5 GW: Worldwide grid-scale battery capacity. (p. 1)" in out
    assert "“Grid-scale battery capacity reached 41.5 GW worldwide”" in out
    assert "  · How fast can interconnection queues be cleared? (p. 3)" in out
    assert "Tags: energy-storage, batteries, grid" in out
    assert "\033[" not in out


def test_terminal_flags_with_reason(document):
    out = render.terminal(Summary.from_json(BAD), DOC, document.pages)
    assert "  ⚠ Prices fell. (p. 1)" in out
    assert "not verified: quote is on p. 2, not the cited p. 1" in out


def test_terminal_color():
    out = render.terminal(Summary.from_json(GOOD_SUMMARY), DOC, ["x"] * 3, color=True)
    assert "\033[1mBattery Storage Outlook\033[0m" in out


def test_terminal_skips_empty_sections(document):
    s = Summary.from_json({**GOOD_SUMMARY, "quotes": [], "open_questions": [], "tags": []})
    out = render.terminal(s, DOC, document.pages)
    assert "Quotes worth keeping" not in out and "Open questions" not in out and "Tags:" not in out


def test_markdown_frontmatter(document):
    md = render.markdown(Summary.from_json(GOOD_SUMMARY, model="claude-opus-5-5"), DOC, document.pages)
    front = md.split("---\n")[1]
    fields = {k: json.loads(v) for k, v in (line.split(": ", 1) for line in front.strip().splitlines())}
    assert fields == {"title": "Battery Storage Outlook", "source": "battery-outlook.pdf", "pages": 3,
                      "summarized": "2026-10-11", "model": "claude-opus-5-5", "verified": 5, "flagged": 0,
                      "tags": ["energy-storage", "batteries", "grid"]}


def test_markdown_body(document):
    md = render.markdown(Summary.from_json(GOOD_SUMMARY), DOC, document.pages)
    assert "# Battery Storage Outlook" in md
    assert "> [!summary] TL;DR" in md
    assert "- **41.5 GW**: Worldwide grid-scale battery capacity. (p. 1)" in md
    assert "> “Grid connection queues, not hardware, are now the main bottleneck” (p. 3)" in md
    assert "Not verified" not in md.split("---")[-2]
    assert "\n\n\n" not in md


def test_markdown_flags(document):
    md = render.markdown(Summary.from_json(BAD), DOC, document.pages)
    assert "    ⚠ **Not verified:** quote is on p. 2, not the cited p. 1" in md


def test_markdown_flagged_quote(document):
    s = Summary.from_json({**GOOD_SUMMARY, "quotes": [{"quote": "words the report never actually says at all", "pages": [2], "why": ""}]})
    assert "> ⚠ **Not verified:** quote not found in the document" in render.markdown(s, DOC, document.pages)


def test_slug():
    assert render.slug('AI: "Hype" or #Real? [2026]') == "AI Hype or Real 2026"
    assert render.slug("   ") == "Untitled"
    assert len(render.slug("x" * 500)) == 120


def test_write_note(tmp_path, document):
    path = render.write_note(Summary.from_json(GOOD_SUMMARY), DOC, document.pages, tmp_path / "Papers")
    assert path == tmp_path / "Papers" / "Battery Storage Outlook.md"
    assert path.read_text().startswith("---\ntitle: ")
