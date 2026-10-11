"""Print a checked summary in the terminal, or write it as an Obsidian-ready Markdown note."""

import json
import re
from datetime import date
from pathlib import Path

from . import verify
from .summarize import Claim, Summary

HEADINGS = {"arguments": "Key arguments", "data_points": "Data points", "quotes": "Quotes worth keeping",
            "open_questions": "Open questions"}
MARK = {verify.VERIFIED: "✓", verify.FLAGGED: "⚠", verify.CITED: "·"}


def pages_label(pages: list[int]) -> str:
    if not pages:
        return "(no page)"
    return ("p. " if len(pages) == 1 else "pp. ") + ", ".join(map(str, pages))


def _paint(on: bool):
    codes = {"green": "32", "yellow": "33", "dim": "2", "bold": "1"}
    return lambda text, style: f"\033[{codes[style]}m{text}\033[0m" if on else text


def headline(claim: Claim, section: str) -> str:
    if section == "data_points":
        return f"{claim.value}: {claim.text}" if claim.value else claim.text
    if section == "quotes":
        return f"“{claim.quote}”"
    return claim.text


def terminal(summary: Summary, doc: dict, pages: list[str], color: bool = False) -> str:
    paint = _paint(color)
    counts = summary.counts(pages)
    out = [paint(summary.title or doc["title"], "bold"),
           paint(f"{doc['source']} · {doc['page_count']} pages · {summary.model or 'model unknown'}", "dim"),
           f"{paint('✓', 'green')} {counts[verify.VERIFIED]} verified   "
           f"{paint('⚠', 'yellow')} {counts[verify.FLAGGED]} flagged   · {counts[verify.CITED]} page-cited only",
           "", paint("TL;DR", "bold"), f"  {summary.tldr} ({pages_label(summary.tldr_pages)})"]
    for section, rows in summary.checked(pages).items():
        if not rows:
            continue
        out += ["", paint(HEADINGS[section], "bold")]
        for claim, check in rows:
            mark = paint(MARK[check.status], {"verified": "green", "flagged": "yellow", "cited": "dim"}[check.status])
            out.append(f"  {mark} {headline(claim, section)} ({pages_label(claim.pages)})")
            if claim.quote and section != "quotes":
                out.append(paint(f"      “{claim.quote}”", "dim"))
            if claim.why:
                out.append(paint(f"      {claim.why}", "dim"))
            if check.status == verify.FLAGGED:
                out.append(paint(f"      not verified: {check.reason}", "yellow"))
    if summary.tags:
        out += ["", paint("Tags: " + ", ".join(summary.tags), "dim")]
    return "\n".join(out)


def slug(title: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|#^\[\]]', "", title).strip()
    return re.sub(r"\s+", " ", cleaned)[:120] or "Untitled"


def markdown(summary: Summary, doc: dict, pages: list[str]) -> str:
    counts = summary.counts(pages)
    title = summary.title or doc["title"]
    front = {
        "title": title,
        "source": doc["source"],
        "pages": doc["page_count"],
        "summarized": (doc.get("summarized_at") or date.today().isoformat())[:10],
        "model": summary.model,
        "verified": counts[verify.VERIFIED],
        "flagged": counts[verify.FLAGGED],
        "tags": summary.tags,
    }
    lines = ["---"] + [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in front.items()] + ["---", "",
             f"# {title}", "", "> [!summary] TL;DR", f"> {summary.tldr} ({pages_label(summary.tldr_pages)})"]
    for section, rows in summary.checked(pages).items():
        if not rows:
            continue
        lines += ["", f"## {HEADINGS[section]}", ""]
        for claim, check in rows:
            if section == "quotes":
                lines += [f"> “{claim.quote}” ({pages_label(claim.pages)})"]
                if claim.why:
                    lines += [">", f"> {claim.why}"]
            else:
                head = f"**{claim.value}**: {claim.text}" if section == "data_points" and claim.value else claim.text
                lines.append(f"- {head} ({pages_label(claim.pages)})")
                if claim.quote:
                    lines.append(f"    > “{claim.quote}”")
            if check.status == verify.FLAGGED:
                lines.append(("> " if section == "quotes" else "    ") + f"⚠ **Not verified:** {check.reason}")
            if section == "quotes":
                lines.append("")
    lines += ["", "---", "<small>Summarised by pagecite. Every quote and number was checked against the PDF text "
              "and found on its cited page, except those marked ⚠ Not verified.</small>", ""]
    return "\n".join(lines).replace("\n\n\n", "\n\n")


def write_note(summary: Summary, doc: dict, pages: list[str], folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{slug(summary.title or doc['title'])}.md"
    path.write_text(markdown(summary, doc, pages))
    return path
