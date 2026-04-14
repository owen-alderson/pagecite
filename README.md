# pdf-research-summarizer

Upload any PDF and get a structured summary in seconds — TL;DR, key arguments, notable data, quotable passages, open questions, and Obsidian tags. Built with Streamlit and Claude API.

Works great for: McKinsey reports, academic papers, pitch decks, legal docs, investor memos.

## Output format

Every summary follows the same structure:

| Section | What it contains |
|---|---|
| **TL;DR** | 2–3 sentence overview |
| **Key Arguments** | 4–7 most important claims or findings |
| **Notable Data & Statistics** | Striking numbers worth keeping |
| **Quotes Worth Keeping** | 1–3 direct quotes from the document |
| **Open Questions** | What the document leaves unanswered |
| **Suggested Obsidian Tags** | Tags for filing in a knowledge base |

The downloaded `.md` file is formatted for Obsidian — drop it straight into your vault.

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/owen-alderson/pdf-research-summarizer.git
cd pdf-research-summarizer
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Add your API key**
```bash
cp .env.example .env
# open .env and replace 'your_api_key_here' with your key from console.anthropic.com
```

**4. Run**
```bash
streamlit run app.py
```

Opens at `http://localhost:8501`.

## Notes

- Works with text-based PDFs. Scanned image PDFs (no embedded text layer) are not supported.
- Very long documents (90,000+ characters) are truncated — the summary covers the first ~60 pages. A warning is shown when this happens.
- Summaries are cached per session — re-uploading the same file won't re-call the API.

## Requirements

- Python 3.8+
- An [Anthropic API key](https://console.anthropic.com/)
