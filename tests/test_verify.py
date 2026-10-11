import pytest

from pagecite import verify
from pagecite.verify import CITED, FLAGGED, VERIFIED, Check

PAGES = [
    "Grid-scale battery capacity reached 41.5 GW world-\nwide by the end of the year.",
    "The average pack price fell to USD 115 per kWh, a decline of 14% on the year before.\n"
    "Analysts warn that lithium supply could become a con-\nstraint after 2028.",
    "Interconnection waits averaged 3,200 days in the slowest regions. Grid connection queues,\n"
    "not hardware, are now the main",
    "bottleneck for new projects. The ﬁnal ﬁgure was 2 500 units.",
]


@pytest.mark.parametrize("a,b", [
    ("Hello,   World!", "helloworld"),
    ("“curly” quotes — and dashes", "curlyquotesanddashes"),
    ("ﬁnance ﬂow", "financeflow"),
    ("soft­hyphen", "softhyphen"),
    ("4.2 billion", "4.2billion"),
    ("end. Next", "endnext"),
])
def test_squash(a, b):
    assert verify.squash(a) == b


def test_squash_keeps_decimal_points_apart_from_integers():
    assert verify.squash("rose 4.2%") != verify.squash("rose 42%")


@pytest.mark.parametrize("text,expected", [
    ("41.5 GW", {41.5}),
    ("USD 115 per kWh", {115.0}),
    ("3,200 days", {3200.0}),
    ("2 500 units", {2500.0}),
    ("2 500 units", {2500.0}),
    ("$4.2bn and 37%", {4.2, 37.0}),
    ("no numbers here", set()),
    ("1,234,567.89", {1234567.89}),
])
def test_numbers(text, expected):
    assert verify.numbers(text) == expected


def test_numbers_do_not_merge_separate_figures():
    assert verify.numbers("in 2025 12 cities") == {2025.0, 12.0}


def test_quote_verified_on_cited_page():
    assert verify.check_quote("The average pack price fell to USD 115 per kWh", [2], PAGES).status == VERIFIED


def test_quote_matching_ignores_case_and_punctuation():
    assert verify.check_quote("the AVERAGE pack price -- fell to usd 115, per kWh", [2], PAGES).ok


def test_quote_across_hyphenated_line_break():
    assert verify.check_quote("lithium supply could become a constraint after 2028", [2], PAGES).status == VERIFIED


def test_quote_across_a_line_break_with_real_hyphen():
    assert verify.check_quote("reached 41.5 GW worldwide by the end", [1], PAGES).status == VERIFIED


def test_quote_with_ligatures_in_pdf_text():
    assert verify.check_quote("The final figure was 2 500 units", [4], PAGES).status == VERIFIED


def test_quote_spanning_two_cited_pages():
    check = verify.check_quote("not hardware, are now the main bottleneck for new projects", [3, 4], PAGES)
    assert check.status == VERIFIED


def test_quote_spanning_pages_found_when_only_one_cited():
    check = verify.check_quote("not hardware, are now the main bottleneck for new projects", [3], PAGES)
    assert check.status == FLAGGED and check.found_on == [3, 4]
    assert "p. 3–4" in check.reason


def test_quote_on_another_page_is_flagged_with_the_real_page():
    check = verify.check_quote("The average pack price fell to USD 115 per kWh", [1], PAGES)
    assert check.status == FLAGGED
    assert check.found_on == [2]
    assert check.reason == "quote is on p. 2, not the cited p. 1"


def test_quote_not_in_document():
    check = verify.check_quote("The average pack price rose to USD 150 per kWh", [2], PAGES)
    assert check == Check(FLAGGED, "quote not found in the document", [])


def test_changed_decimal_is_not_a_match():
    assert not verify.check_quote("battery capacity reached 415 GW worldwide", [1], PAGES).ok


def test_ellipsis_parts_must_appear_in_order():
    assert verify.check_quote("The average pack price … a decline of 14%", [2], PAGES).status == VERIFIED
    assert verify.check_quote("a decline of 14% ... The average pack price", [2], PAGES).status == FLAGGED


def test_three_dot_ellipsis():
    assert verify.check_quote("Analysts warn that ... after 2028", [2], PAGES).status == VERIFIED


def test_empty_quote_is_flagged():
    assert verify.check_quote("  ", [1], PAGES) == Check(FLAGGED, "no supporting quote")


def test_short_quote_is_flagged():
    check = verify.check_quote("pack price", [2], PAGES)
    assert check.status == FLAGGED and "too short" in check.reason


def test_quote_with_no_page():
    check = verify.check_quote("The average pack price fell to USD 115 per kWh", [], PAGES)
    assert check.status == FLAGGED and check.reason.startswith("no page cited")
    assert check.found_on == [2]


def test_quote_citing_a_page_past_the_end():
    check = verify.check_quote("The average pack price fell to USD 115 per kWh", [9], PAGES)
    assert check.status == FLAGGED
    assert check.reason == "cites p. 9, but the document has 4 pages; the quote is on p. 2"


def test_bad_page_and_missing_quote():
    check = verify.check_quote("words that are nowhere at all", [0], PAGES)
    assert check.reason == "cites p. 0, but the document has 4 pages; quote not found in the document"


def test_locate():
    assert verify.locate("Interconnection waits averaged 3,200 days", PAGES) == [3]
    assert verify.locate("nothing like this exists in it", PAGES) == []


def test_check_pages():
    assert verify.check_pages([1, 4], PAGES).status == CITED
    assert verify.check_pages([], PAGES) == Check(FLAGGED, "no page cited")
    assert verify.check_pages([5], PAGES).status == FLAGGED


def test_value_found():
    assert verify.check_value("USD 115 per kWh", [2], PAGES).status == VERIFIED
    assert verify.check_value("3,200 days", [3], PAGES).status == VERIFIED
    assert verify.check_value("3200", [3], PAGES).status == VERIFIED


def test_value_with_several_numbers_needs_all():
    assert verify.check_value("USD 115 per kWh, down 14%", [2], PAGES).status == VERIFIED
    check = verify.check_value("USD 115 per kWh, down 16%", [2], PAGES)
    assert check == Check(FLAGGED, "16 not on the cited page")


def test_value_on_wrong_page():
    check = verify.check_value("41.5 GW", [2], PAGES)
    assert check.status == FLAGGED and "41.5" in check.reason


def test_value_without_digits_must_appear_verbatim():
    assert verify.check_value("more than double", [1], ["Capacity was more than double last year."]).status == VERIFIED
    assert verify.check_value("tripled", [1], PAGES).status == FLAGGED


def test_value_with_bad_page():
    assert verify.check_value("41.5 GW", [7], PAGES).reason == "cites p. 7, but the document has 4 pages"


def test_worst():
    ok, bad = Check(VERIFIED), Check(FLAGGED, "x", [2])
    assert verify.worst(ok, ok) == Check(VERIFIED)
    assert verify.worst(ok, bad) == Check(FLAGGED, "x", [2])
    assert verify.worst(Check(FLAGGED, "a"), Check(FLAGGED, "b", [3])) == Check(FLAGGED, "a; b", [3])
    assert verify.worst(Check(CITED)) == Check(CITED)


def test_check_ok_property():
    assert Check(VERIFIED).ok and Check(CITED).ok and not Check(FLAGGED).ok
