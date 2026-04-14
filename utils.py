import anthropic
import os
from pathlib import Path

MAX_CHARS = 90_000

SYSTEM_PROMPT = """You are a research analyst. Your job is to read documents and produce a clean, structured summary that saves the reader time without losing the substance.

Always respond in exactly this format:

## TL;DR
2–3 sentences max. What is this document, what is its main argument or finding, and who should care about it?

## Key Arguments
Bullet list of the 4–7 most important claims, findings, or recommendations in the document. Each bullet should be a complete thought — not a fragment.

## Notable Data & Statistics
Bullet list of the most striking numbers, percentages, market sizes, or quantitative findings. If the document has no notable data, write "None."

## Quotes Worth Keeping
1–3 direct quotes that best capture the document's voice or most important points. Format each as:
> "quote" — source/section if identifiable

If there are no quotable passages, write "None."

## Open Questions
What does this document leave unanswered? What would you want to investigate further after reading it? Bullet list of 2–4 questions.

## Suggested Obsidian Tags
A comma-separated list of 4–8 lowercase tags suitable for filing this document in a knowledge base (e.g. fintech, private-equity, AI, regulation, healthcare).
"""


def load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def extract_pdf_text(file_bytes: bytes) -> tuple[str, dict]:
    """Extract text and metadata from PDF bytes. Returns (text, metadata)."""
    import pymupdf
    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    meta = doc.metadata or {}
    pages = doc.page_count
    text_parts = [page.get_text() for page in doc]
    full_text = "\n\n".join(text_parts)
    return full_text, {
        "pages": pages,
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
    }


def truncate_text(text: str, max_chars: int = MAX_CHARS) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    truncated = text[:max_chars]
    last_break = truncated.rfind("\n\n")
    if last_break > max_chars * 0.8:
        truncated = truncated[:last_break]
    return truncated, True


def summarize(text: str, filename: str) -> str:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Summarize this document. Filename: {filename}\n\n---\n\n{text}"
            }
        ]
    )
    return message.content[0].text
