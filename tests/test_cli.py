import json

import pytest

from pagecite import __main__ as cli
from pagecite import __version__, summarize
from pagecite.store import Store

from .conftest import GOOD_SUMMARY, FakeClient, cite, make_pdf, response, text_block


@pytest.fixture
def env(tmp_path, monkeypatch):
    """An isolated library and a fake Anthropic client for every command."""
    monkeypatch.setenv("PAGECITE_DB", str(tmp_path / "lib.db"))
    monkeypatch.delenv("PAGECITE_NOTES_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    client = FakeClient()
    monkeypatch.setattr(summarize.anthropic, "Anthropic", lambda: client)
    return client


def run(capsys, *argv):
    code = cli.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_no_command_prints_help(env, capsys):
    code, out, _ = run(capsys)
    assert code == 0 and "summarize" in out and "ask" in out


def test_version(env, capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.strip() == f"pagecite {__version__}"


def test_demo_needs_no_key(env, capsys):
    code, out, err = run(capsys, "demo")
    assert code == 0 and env.calls == []
    assert "✓ 5 verified   ⚠ 2 flagged" in out
    assert "not verified: quote is on p. 3, not the cited p. 1" in out
    assert "not verified: 27 not on the cited page" in out
    assert "no API call" in err


def test_summarize_file(env, capsys, pdf_file):
    code, out, err = run(capsys, "summarize", str(pdf_file))
    assert code == 0 and len(env.calls) == 1
    assert out.startswith("Battery Storage Outlook") and "✓ 5 verified" in out
    assert "from your library" not in err


def test_summarize_twice_uses_library(env, capsys, pdf_file):
    run(capsys, "summarize", str(pdf_file))
    code, out, err = run(capsys, "sum", str(pdf_file))
    assert code == 0 and len(env.calls) == 1 and "from your library, #1" in err


def test_summarize_refresh(env, capsys, pdf_file):
    run(capsys, "summarize", str(pdf_file))
    run(capsys, "summarize", "--refresh", str(pdf_file))
    assert len(env.calls) == 2


def test_summarize_writes_notes(env, capsys, pdf_file, tmp_path):
    code, _, err = run(capsys, "summarize", str(pdf_file), "-o", str(tmp_path / "notes"))
    note = tmp_path / "notes" / "Battery Storage Outlook.md"
    assert code == 0 and note.exists() and f"Note: {note}" in err


def test_notes_dir_from_env(env, capsys, pdf_file, tmp_path, monkeypatch):
    monkeypatch.setenv("PAGECITE_NOTES_DIR", str(tmp_path / "vault" / "Papers"))
    run(capsys, "summarize", str(pdf_file))
    assert (tmp_path / "vault" / "Papers" / "Battery Storage Outlook.md").exists()


def test_summarize_folder(env, capsys, tmp_path):
    folder = tmp_path / "papers"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(make_pdf(["Alpha paper text about storage"]))
    (folder / "b.pdf").write_bytes(make_pdf(["Beta paper text about wind"]))
    (folder / "readme.txt").write_text("x")
    code, out, err = run(capsys, "summarize", str(folder))
    assert code == 0 and len(env.calls) == 2
    assert "[1/2]" in err and "[2/2]" in err and "─" * 60 in out


def test_empty_folder(env, capsys, tmp_path):
    (tmp_path / "empty").mkdir()
    code, _, err = run(capsys, "summarize", str(tmp_path / "empty"))
    assert code == 0 and "No PDFs in" in err


def test_one_bad_file_does_not_stop_the_rest(env, capsys, tmp_path, pdf_file):
    code, out, err = run(capsys, "summarize", str(tmp_path / "missing.pdf"), str(pdf_file))
    assert code == 1 and "Error: No such file" in err and "Battery Storage Outlook" in out


def test_claude_error_is_reported(env, capsys, pdf_file):
    env.queue.append(response("{}", stop_reason="refusal"))
    code, _, err = run(capsys, "summarize", str(pdf_file))
    assert code == 1 and "Error: Claude declined" in err


def test_list(env, capsys, pdf_file):
    assert "library is empty" in run(capsys, "list")[1]
    run(capsys, "summarize", str(pdf_file))
    code, out, _ = run(capsys, "ls")
    assert code == 0 and out.startswith("#1    Battery Storage Outlook  ·  3 pages")


def test_list_marks_unsummarised(env, capsys, tmp_path, pdf_file):
    env.queue.append(response("not json"))
    run(capsys, "summarize", str(pdf_file))
    assert "(not summarised)" in run(capsys, "list")[1]


def test_show(env, capsys, pdf_file):
    run(capsys, "summarize", str(pdf_file))
    code, out, _ = run(capsys, "show", "1")
    assert code == 0 and "✓ 5 verified" in out
    code, out, _ = run(capsys, "show", "1", "--markdown")
    assert out.startswith("---\ntitle: \"Battery Storage Outlook\"")


def test_show_missing(env, capsys):
    code, _, err = run(capsys, "show", "4")
    assert code == 1 and "No document #4" in err


def test_show_without_summary(env, capsys, pdf_file):
    env.queue.append(response("not json"))
    run(capsys, "summarize", str(pdf_file))
    code, _, err = run(capsys, "show", "1")
    assert code == 1 and "has no summary yet" in err


def test_search(env, capsys, pdf_file):
    run(capsys, "summarize", str(pdf_file))
    code, out, _ = run(capsys, "search", "lithium", "supply")
    assert code == 0 and out.startswith("#1 Battery Storage Outlook, p. 2") and "[lithium]" in out
    assert run(capsys, "search", "zebra")[1].strip() == "No matching pages."


def test_ask(env, capsys, pdf_file):
    run(capsys, "summarize", str(pdf_file))
    env.queue.append(response(content=[
        text_block("Prices fell to USD 115 per kWh.", [cite(1, "The average pack price fell to USD 115 per kWh")]),
        text_block(" Queues are the bottleneck.", [cite(2, "Grid connection queues")]),
    ]))
    code, out, _ = run(capsys, "ask", "what", "happened?", "--doc", "1")
    assert code == 0
    assert out.startswith("Prices fell to USD 115 per kWh.[1] Queues are the bottleneck.[2]")
    assert "[1] Battery Storage Outlook, p. 2 (#1): “The average pack price fell to USD 115 per kWh”" in out
    assert env.calls[-1]["messages"][0]["content"][-1]["text"] == "what happened?"


def test_ask_empty_library(env, capsys):
    code, out, _ = run(capsys, "ask", "anything")
    assert code == 0 and "Nothing in your library" in out


def test_ask_unknown_doc(env, capsys):
    code, _, err = run(capsys, "ask", "q", "--doc", "9")
    assert code == 1 and "No document #9" in err


def test_db_flag(env, capsys, pdf_file, tmp_path):
    run(capsys, "--db", str(tmp_path / "other.db"), "summarize", str(pdf_file))
    assert len(Store(tmp_path / "other.db").docs()) == 1
    assert not (tmp_path / "lib.db").exists() or Store(tmp_path / "lib.db").docs() == []


def test_env_file_is_loaded(env, capsys, tmp_path, monkeypatch, pdf_file):
    monkeypatch.delenv("PAGECITE_MODEL", raising=False)
    (tmp_path / ".env").write_text("PAGECITE_MODEL=claude-sonnet-5-5\n")
    run(capsys, "summarize", str(pdf_file))
    assert env.calls[0]["model"] == "claude-sonnet-5-5"


def test_summary_json_is_stored(env, capsys, pdf_file, tmp_path):
    run(capsys, "summarize", str(pdf_file))
    stored = json.loads(Store(tmp_path / "lib.db").doc(1)["summary"])
    assert stored["title"] == GOOD_SUMMARY["title"] and stored["model"] == "claude-opus-5-5"
