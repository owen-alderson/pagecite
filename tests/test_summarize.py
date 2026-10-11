import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from pagecite import summarize
from pagecite.pdf import Document
from pagecite.summarize import ClaudeError, Summarizer, Summary

from .conftest import GOOD_SUMMARY, FakeClient, response


def test_from_json_normalises():
    s = Summary.from_json({**GOOD_SUMMARY, "tldr_pages": [3, 1, 3],
                           "arguments": [{"text": "x", "pages": [2, 1, 2], "quote": "q"}, {"text": " ", "pages": [], "quote": ""}]})
    assert s.tldr_pages == [1, 3]
    assert [a.pages for a in s.arguments] == [[1, 2]]
    assert s.tags == ["energy-storage", "batteries", "grid"]


def test_from_json_tolerates_missing_sections():
    s = Summary.from_json({"title": "T", "tldr": "x"})
    assert s.arguments == [] and s.tags == [] and s.tldr_pages == []


def test_roundtrip():
    s = Summary.from_json(GOOD_SUMMARY, model="m")
    again = Summary.from_json(s.to_json())
    assert again == s and again.model == "m"


def test_checks_on_good_summary(document):
    s = Summary.from_json(GOOD_SUMMARY)
    checked = s.checked(document.pages)
    assert all(c.status == "verified" for rows in ("arguments", "data_points", "quotes") for _, c in checked[rows])
    assert [c.status for _, c in checked["open_questions"]] == ["cited"]
    assert s.counts(document.pages) == {"verified": 5, "flagged": 0, "cited": 1}


def test_data_point_needs_value_and_quote(document):
    s = Summary.from_json({**GOOD_SUMMARY, "data_points": [
        {"text": "Capacity", "value": "45 GW", "pages": [1], "quote": "Grid-scale battery capacity reached 41.5 GW worldwide"},
        {"text": "Capacity", "value": "41.5 GW", "pages": [1], "quote": "capacity reached a record 41.5 GW worldwide"},
    ]})
    first, second = (c for _, c in s.checked(document.pages)["data_points"])
    assert first.status == "flagged" and "45" in first.reason
    assert second.status == "flagged" and "quote not found" in second.reason


def test_open_question_with_bad_page_is_flagged(document):
    s = Summary.from_json({**GOOD_SUMMARY, "open_questions": [{"text": "q", "pages": [12]}]})
    assert s.counts(document.pages)["flagged"] == 1


def test_page_blocks():
    out = summarize.page_blocks(["first", "  ", "third"])
    assert out.splitlines()[0] == '<page n="1">'
    assert "(no extractable text on this page)" in out and '<page n="3">\nthird\n</page>' in out


def test_summarize_request(document):
    client = FakeClient(response(json.dumps(GOOD_SUMMARY), model="claude-opus-5-5"))
    s = Summarizer(client, model="claude-opus-5-5").summarize(document)
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": summarize.SCHEMA}
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    prompt = call["messages"][0]["content"]
    assert prompt.startswith("Document: Battery Storage Outlook (3 pages)") and '<page n="3">' in prompt
    assert s.title == "Battery Storage Outlook" and s.model == "claude-opus-5-5"
    assert len(s.arguments) == 2


def test_schema_is_strict():
    assert summarize.SCHEMA["additionalProperties"] is False
    item = summarize.SCHEMA["properties"]["data_points"]["items"]
    assert set(item["required"]) == {"text", "value", "quote", "pages"} and item["additionalProperties"] is False


@pytest.mark.parametrize("stop,msg", [("refusal", "declined"), ("max_tokens", "cut off")])
def test_bad_stop_reasons(document, stop, msg):
    with pytest.raises(ClaudeError, match=msg):
        Summarizer(FakeClient(response("{}", stop_reason=stop))).summarize(document)


def test_malformed_output(document):
    with pytest.raises(ClaudeError, match="malformed"):
        Summarizer(FakeClient(response("not json"))).summarize(document)


def test_no_text_block(document):
    with pytest.raises(ClaudeError, match="malformed"):
        Summarizer(FakeClient(response(content=[SimpleNamespace(type="thinking", thinking="")]))).summarize(document)


def test_scanned_pdf_is_refused_before_any_call():
    client = FakeClient()
    with pytest.raises(ClaudeError, match="no text layer"):
        Summarizer(client).summarize(Document("x", "Scan", "scan.pdf", ["", "  "]))
    assert client.calls == []


def test_too_long_is_refused_not_truncated(monkeypatch, document):
    monkeypatch.setattr(summarize, "MAX_CHARS", 100)
    client = FakeClient()
    with pytest.raises(ClaudeError, match="too long"):
        Summarizer(client).summarize(document)
    assert client.calls == []


def _status_error(cls, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx2.Response(status, request=request), body=None)


@pytest.mark.parametrize("error,msg", [
    (lambda: _status_error(anthropic.AuthenticationError, 401), "API key missing or invalid"),
    (lambda: _status_error(anthropic.RateLimitError, 429), "Rate limited"),
    (lambda: _status_error(anthropic.InternalServerError, 500), "API error 500"),
    (lambda: anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com")), "Could not reach"),
])
def test_api_errors_become_claude_errors(document, error, msg):
    with pytest.raises(ClaudeError, match=msg):
        Summarizer(FakeClient(error())).summarize(document)


def test_missing_credentials_with_the_real_sdk(monkeypatch, tmp_path, document):
    """No key, no token, no `ant` profile: the real client fails before any network call."""
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "ANTHROPIC_CONFIG_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    with pytest.raises(ClaudeError, match="No Anthropic credentials"):
        Summarizer().summarize(document)


def test_unrelated_type_errors_are_not_swallowed(document):
    with pytest.raises(TypeError, match="something else"):
        Summarizer(FakeClient(TypeError("something else"))).summarize(document)


def test_other_sdk_errors(document):
    with pytest.raises(ClaudeError, match="Anthropic client error"):
        Summarizer(FakeClient(anthropic.AnthropicError("weird"))).summarize(document)
