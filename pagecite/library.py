"""Read a PDF into the library and summarise it, reusing the stored summary when the same file
(same SHA-256) was summarised before."""

from dataclasses import dataclass

from . import pdf
from .store import Store
from .summarize import Summarizer, Summary


@dataclass
class Result:
    doc_id: int
    summary: Summary
    cached: bool


def summarize(source: str, store: Store, summarizer: Summarizer, refresh: bool = False) -> Result:
    doc = pdf.load(source)
    doc_id = store.add(doc)
    if not refresh:
        cached = store.summary(doc_id)
        if cached is not None:
            return Result(doc_id, cached, True)
    summary = summarizer.summarize(doc)
    store.save_summary(doc_id, summary)
    return Result(doc_id, summary, False)
