"""`pagecite demo`: a fictional four-page report, built as a real PDF, and a sample summary written
for the demo (no API call). The verification that runs on it is the real one: two of the sample
claims are deliberately wrong, so you can see what a flagged claim looks like."""

import pymupdf

from .pdf import Document, from_bytes
from .summarize import Summary

PAGES = [
    """The State of Urban Cargo Bikes 2026
Northside Mobility Lab - Annual Report (fictional demo document)

Executive summary
Cargo bikes moved from niche to mainstream in European city logistics this year. Across the 14 cities
we tracked, operators made 2.3 million deliveries by cargo bike, up from 1.6 million in 2025.
Our central finding is that cargo bikes now beat vans on cost per parcel in dense city centres,
but only where cities provide loading space and protected lanes.""",
    """Market size
We estimate the European cargo bike logistics market at EUR 1.9bn in 2026, growing at roughly 18% a year.
This estimate is based on operator surveys and should be read as a range rather than a point figure.

Cost per parcel
In the densest districts the average cost per parcel was EUR 1.42 by cargo bike against EUR 2.10 by van.
Outside the city centre the advantage disappears: vans were cheaper beyond a 6 km delivery radius.""",
    """What holds adoption back
Operators named the lack of loading bays as the single biggest obstacle, ahead of theft and weather.
Insurance premiums rose 22% year on year, which several smaller operators said threatens their margins.
Where cities built protected lanes, delivery times fell by 11% on average.""",
    """Outlook
We expect growth to continue but slow, as the easiest routes have already been converted.
The open question is whether cities will reallocate kerb space from parking to loading at the pace
operators need. Without that, the cost advantage we measured may not survive outside a few showcase districts.""",
]

SAMPLE = {
    "title": "The State of Urban Cargo Bikes 2026",
    "model": "sample summary (written for the demo, not by Claude)",
    "tldr": "A fictional annual report on cargo-bike delivery in 14 European cities: volumes grew sharply and cargo "
            "bikes now undercut vans on cost per parcel in dense centres, but only with loading space and protected lanes.",
    "tldr_pages": [1, 2],
    "arguments": [
        {"text": "Cargo bikes are cheaper than vans per parcel in dense city centres, conditional on city infrastructure.",
         "pages": [1], "quote": "cargo bikes now beat vans on cost per parcel in dense city centres"},
        {"text": "Beyond a short delivery radius the cost advantage reverses in favour of vans.",
         "pages": [2], "quote": "vans were cheaper beyond a 6 km delivery radius"},
        {"text": "Missing loading bays are the main barrier to adoption.",
         "pages": [1], "quote": "the lack of loading bays as the single biggest obstacle"},
    ],
    "data_points": [
        {"text": "Cargo-bike deliveries across the 14 cities in 2026 (1.6 million in 2025).", "value": "2.3 million",
         "pages": [1], "quote": "operators made 2.3 million deliveries by cargo bike"},
        {"text": "Estimated European market size, an estimate from operator surveys.", "value": "EUR 1.9bn",
         "pages": [2], "quote": "European cargo bike logistics market at EUR 1.9bn in 2026"},
        {"text": "Rise in insurance premiums year on year.", "value": "27%",
         "pages": [3], "quote": "Insurance premiums rose 22% year on year"},
    ],
    "quotes": [
        {"quote": "Without that, the cost advantage we measured may not survive outside a few showcase districts.",
         "pages": [4], "why": "The report's own caveat on its headline finding."},
    ],
    "open_questions": [
        {"text": "Will cities reallocate kerb space from parking to loading fast enough?", "pages": [4]},
        {"text": "How wide is the range around the EUR 1.9bn market estimate?", "pages": [2]},
    ],
    "tags": ["cargo-bikes", "urban-logistics", "last-mile", "transport-policy"],
}


def sample_pdf() -> bytes:
    doc = pymupdf.open()
    for text in PAGES:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(60, 60, 540, 780), text, fontsize=11)
    doc.set_metadata({"title": "The State of Urban Cargo Bikes 2026"})
    data = doc.tobytes()
    doc.close()
    return data


def sample() -> tuple[Document, Summary]:
    return from_bytes(sample_pdf(), "cargo-bikes-2026.pdf (demo)"), Summary.from_json(SAMPLE)
