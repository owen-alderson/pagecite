import streamlit as st
import os
from datetime import datetime
from utils import load_env, extract_pdf_text, truncate_text, summarize, MAX_CHARS

load_env()

# ── UI ────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="PDF Summarizer", page_icon="📄", layout="wide")

st.markdown("""
<style>
    .truncation-warning {
        background: #2a1a00;
        border: 1px solid #ff9900;
        border-radius: 8px;
        padding: 10px 16px;
        color: #ffbb44;
        font-size: 0.9rem;
        margin-bottom: 16px;
    }
</style>
""", unsafe_allow_html=True)

st.title("📄 PDF Research Summarizer")
st.caption("Upload any PDF — research reports, papers, pitch decks — and get a structured summary in seconds.")

# ── API key check ─────────────────────────────────────────────────────────────

if not os.environ.get("ANTHROPIC_API_KEY"):
    st.warning("No API key found. Add `ANTHROPIC_API_KEY=your_key` to a `.env` file in the project folder.")
    st.stop()

# ── File uploader ─────────────────────────────────────────────────────────────

uploaded_file = st.file_uploader(
    "Drop a PDF here or click to browse",
    type=["pdf"],
)

if not uploaded_file:
    st.info("Upload a PDF to get started. Works best with text-based PDFs (not scanned images).")
    st.stop()

file_bytes = uploaded_file.read()
filename = uploaded_file.name

# ── Extract ───────────────────────────────────────────────────────────────────

with st.spinner("Reading PDF..."):
    try:
        raw_text, meta = extract_pdf_text(file_bytes)
    except Exception as e:
        st.error(f"Could not read PDF: {e}")
        st.stop()

if not raw_text.strip():
    st.error("No text found. This may be a scanned image PDF — text-based PDFs only.")
    st.stop()

text, was_truncated = truncate_text(raw_text)

# ── Metadata ──────────────────────────────────────────────────────────────────

pages = meta.get("pages", "?")
title = meta.get("title") or filename.replace(".pdf", "")
word_count = len(raw_text.split())

col1, col2, col3, col4 = st.columns(4)
col1.metric("Pages", pages)
col2.metric("Words", f"{word_count:,}")
col3.metric("Characters", f"{len(raw_text):,}")
col4.metric("Sent to Claude", f"{len(text):,}" + (" ✂️" if was_truncated else " ✓"))

if was_truncated:
    st.markdown(f"""
    <div class="truncation-warning">
        ⚠️ This document is very long ({len(raw_text):,} chars). Summary covers the first ~{MAX_CHARS // 1500} pages.
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ── Summarize ─────────────────────────────────────────────────────────────────

if "summary" not in st.session_state or st.session_state.get("last_file") != filename:
    with st.spinner("Summarizing with Claude..."):
        st.session_state.summary = summarize(text, filename)
        st.session_state.last_file = filename

summary = st.session_state.summary

# ── Display ───────────────────────────────────────────────────────────────────

st.markdown(f"## Summary — *{title}*")
st.markdown(summary)
st.divider()

# ── Download ──────────────────────────────────────────────────────────────────

timestamp = datetime.now().strftime("%Y-%m-%d")
safe_name = filename.replace(".pdf", "").replace(" ", "-").lower()
md_content = f"# Summary — {title}\n\n*Summarized {timestamp} · {pages} pages · {word_count:,} words*\n\n---\n\n{summary}"

st.download_button(
    label="⬇️ Download as Markdown",
    data=md_content.encode("utf-8"),
    file_name=f"{safe_name}-summary-{timestamp}.md",
    mime="text/markdown",
    use_container_width=True,
)
st.caption("The downloaded .md file is formatted for Obsidian — drop it straight into your vault.")
