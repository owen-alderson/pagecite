import json
from types import SimpleNamespace

import pymupdf
import pytest

from pagecite.pdf import from_bytes
from pagecite.store import Store

PAGES = [
    "Battery Storage Outlook\nGrid-scale battery capacity reached 41.5 GW worldwide by the end of the year,\n"
    "more than double the previous year.",
    "Costs\nThe average pack price fell to USD 115 per kWh, a decline of 14% on the year before.\n"
    "Analysts warn that lithium supply could become a con-\nstraint after 2028.",
    "Risks\nGrid connection queues, not hardware, are now the main bottleneck for new projects.\n"
    "Interconnection waits averaged 3,200 days in the slowest regions.",
]


def make_pdf(pages: list[str], title: str = "") -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=10)
    if title:
        doc.set_metadata({"title": title})
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_bytes():
    return make_pdf(PAGES, title="Battery Storage Outlook")


@pytest.fixture
def pdf_file(tmp_path, pdf_bytes):
    path = tmp_path / "battery-outlook.pdf"
    path.write_bytes(pdf_bytes)
    return path


@pytest.fixture
def document(pdf_bytes):
    return from_bytes(pdf_bytes, "battery-outlook.pdf", "battery-outlook")


GOOD_SUMMARY = {
    "title": "Battery Storage Outlook",
    "tldr": "Battery storage capacity doubled while pack prices fell; grid connection is now the bottleneck.",
    "tldr_pages": [1, 3],
    "arguments": [
        {"text": "Grid connection, not hardware, limits new projects.", "pages": [3],
         "quote": "Grid connection queues, not hardware, are now the main bottleneck for new projects."},
        {"text": "Lithium supply may constrain growth later this decade.", "pages": [2],
         "quote": "lithium supply could become a constraint after 2028"},
    ],
    "data_points": [
        {"text": "Worldwide grid-scale battery capacity.", "value": "41.5 GW", "pages": [1],
         "quote": "Grid-scale battery capacity reached 41.5 GW worldwide"},
        {"text": "Average pack price.", "value": "USD 115 per kWh", "pages": [2],
         "quote": "The average pack price fell to USD 115 per kWh"},
    ],
    "quotes": [{"quote": "Grid connection queues, not hardware, are now the main bottleneck", "pages": [3],
                "why": "The report's main warning."}],
    "open_questions": [{"text": "How fast can interconnection queues be cleared?", "pages": [3]}],
    "tags": ["energy-storage", "Batteries", "#grid", "grid"],
}


def response(text: str = "", stop_reason: str = "end_turn", content=None, model: str = "claude-opus-5-5"):
    blocks = content if content is not None else [SimpleNamespace(type="text", text=text, citations=None)]
    return SimpleNamespace(stop_reason=stop_reason, content=blocks, model=model)


class FakeClient:
    """Stands in for anthropic.Anthropic: returns queued responses (or raises queued exceptions)
    and records every request's keyword arguments."""

    def __init__(self, *responses):
        self.queue, self.calls = list(responses), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.queue.pop(0) if self.queue else response(json.dumps(GOOD_SUMMARY))
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def store():
    s = Store()
    yield s
    s.close()


def cite(index: int, text: str):
    return SimpleNamespace(type="search_result_location", search_result_index=index, start_block_index=0,
                           end_block_index=1, cited_text=text, source="", title="")


def text_block(text: str, citations=None):
    return SimpleNamespace(type="text", text=text, citations=citations)


def anthropic_client(handler):
    """A real Anthropic SDK client whose HTTP goes to `handler(request) -> httpx2.Response`."""
    import anthropic
    import httpx2

    return anthropic.Anthropic(api_key="sk-test", max_retries=0,
                               http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def message(content, stop_reason="end_turn"):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": content, "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10}}
