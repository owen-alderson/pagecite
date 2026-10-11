from pagecite import demo


def test_sample_is_a_real_pdf():
    doc, summary = demo.sample()
    assert doc.page_count == 4 and doc.title == "The State of Urban Cargo Bikes 2026"
    assert summary.model.startswith("sample summary")


def test_exactly_the_two_planted_errors_are_flagged():
    doc, summary = demo.sample()
    flagged = [(section, claim.text, check.reason) for section, rows in summary.checked(doc.pages).items()
               for claim, check in rows if not check.ok]
    assert flagged == [
        ("arguments", "Missing loading bays are the main barrier to adoption.", "quote is on p. 3, not the cited p. 1"),
        ("data_points", "Rise in insurance premiums year on year.", "27 not on the cited page"),
    ]
    assert summary.counts(doc.pages) == {"verified": 5, "flagged": 2, "cited": 2}
