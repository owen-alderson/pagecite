"""pagecite: summarise research PDFs where every claim cites its page and is checked against the text."""

import argparse
import importlib.util
import sys
from pathlib import Path

from . import __version__
from .config import DATA_DIR, Settings, load_env


def fail(message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return 1


def open_store(settings: Settings):
    from .store import Store

    return Store(settings.db_path)


def expand(sources: list[str]) -> list[str]:
    """Folders become the PDFs inside them; files and URLs pass through."""
    from .pdf import find_pdfs, is_url

    out = []
    for s in sources:
        path = Path(s).expanduser()
        if not is_url(s) and path.is_dir():
            found = find_pdfs(path)
            if not found:
                print(f"No PDFs in {s}", file=sys.stderr)
            out += [str(p) for p in found]
        else:
            out.append(s)
    return out


def cmd_summarize(args, settings: Settings) -> int:
    from . import library, render
    from .pdf import PDFError
    from .summarize import ClaudeError, Summarizer

    store, summarizer = open_store(settings), Summarizer(model=settings.model)
    notes = Path(args.output).expanduser() if args.output else settings.notes_dir
    sources, failed = expand(args.sources), 0
    for i, source in enumerate(sources):
        if len(sources) > 1:
            print(f"[{i + 1}/{len(sources)}] {source}", file=sys.stderr)
        try:
            result = library.summarize(source, store, summarizer, args.refresh)
        except (PDFError, ClaudeError) as e:
            failed += 1
            fail(str(e))
            continue
        doc, pages = store.doc(result.doc_id), store.pages(result.doc_id)
        if i:
            print("\n" + "─" * 60 + "\n")
        print(render.terminal(result.summary, doc, pages, color=sys.stdout.isatty()))
        if result.cached:
            print(f"\n(from your library, #{result.doc_id}; --refresh to summarise again)", file=sys.stderr)
        if notes:
            print(f"Note: {render.write_note(result.summary, doc, pages, notes)}", file=sys.stderr)
    return 1 if failed else 0


def cmd_ask(args, settings: Settings) -> int:
    from .ask import Asker

    answer = Asker(open_store(settings), model=settings.model).ask(" ".join(args.question), args.doc)
    sources = answer.sources()
    index = {(c.doc_id, c.page): n for n, c in enumerate(sources, 1)}
    text = ""
    for part in answer.parts:
        marks = sorted({index[(c.doc_id, c.page)] for c in part.cites})
        text += part.text + "".join(f"[{m}]" for m in marks)
    print(text.strip())
    if sources:
        print("\nSources")
        for n, c in enumerate(sources, 1):
            excerpt = " ".join(c.text.split())
            print(f"  [{n}] {c.title}, p. {c.page} (#{c.doc_id}): “{excerpt[:160]}{'…' if len(excerpt) > 160 else ''}”")
    return 0


def cmd_list(args, settings: Settings) -> int:
    docs = open_store(settings).docs()
    if not docs:
        print("Your library is empty. Start with: pagecite summarize paper.pdf")
    for d in docs:
        mark = "" if d["summary"] else "  (not summarised)"
        print(f"#{d['id']:<4} {d['title']}  ·  {d['page_count']} pages  ·  {d['added_at'][:10]}{mark}")
    return 0


def cmd_show(args, settings: Settings) -> int:
    from . import render

    store = open_store(settings)
    doc, summary = store.doc(args.id), store.summary(args.id)
    if doc is None:
        return fail(f"No document #{args.id}. See `pagecite list`.")
    if summary is None:
        return fail(f"#{args.id} has no summary yet: pagecite summarize {doc['source']}")
    pages = store.pages(args.id)
    print(render.markdown(summary, doc, pages) if args.markdown else
          render.terminal(summary, doc, pages, color=sys.stdout.isatty()))
    return 0


def cmd_search(args, settings: Settings) -> int:
    hits = open_store(settings).search(" ".join(args.query), args.limit, args.doc)
    if not hits:
        print("No matching pages.")
    for h in hits:
        print(f"#{h['doc_id']} {h['title']}, p. {h['n']}\n    {' '.join(h['snippet'].split())}")
    return 0


def cmd_mcp(args, settings: Settings) -> int:
    if importlib.util.find_spec("mcp") is None:
        return fail("The MCP server needs the mcp extra: pipx install 'pagecite[mcp]'")
    from .ask import Asker
    from .mcp_server import build_server
    from .summarize import Summarizer

    store = open_store(settings)
    build_server(store, Summarizer(model=settings.model), Asker(store, model=settings.model)).run("stdio")
    return 0


def cmd_demo(args, settings: Settings) -> int:
    from . import render
    from .demo import sample

    doc, summary = sample()
    meta = {"title": doc.title, "source": doc.source, "page_count": doc.page_count}
    print("Demo: a fictional 4-page report and a sample summary bundled with pagecite (no API call).\n"
          "The checks are real: two sample claims are deliberately wrong.\n", file=sys.stderr)
    print(render.terminal(summary, meta, doc.pages, color=sys.stdout.isatty()))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pagecite", description=__doc__)
    p.add_argument("--version", action="version", version=f"pagecite {__version__}")
    p.add_argument("--db", help=f"library file (default {DATA_DIR / 'library.db'})")
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("summarize", aliases=["sum"], help="summarise PDFs: files, folders or http(s) URLs")
    s.add_argument("sources", nargs="+")
    s.add_argument("-o", "--output", help="also write each summary as a Markdown note into this folder")
    s.add_argument("--refresh", action="store_true", help="summarise again even if the file is in your library")

    a = sub.add_parser("ask", help="ask your library (or one document) a question; the answer cites pages")
    a.add_argument("question", nargs="+")
    a.add_argument("--doc", type=int, help="only this document (id from `pagecite list`)")

    sub.add_parser("list", aliases=["ls"], help="the PDFs in your library")

    sh = sub.add_parser("show", help="print a stored summary")
    sh.add_argument("id", type=int)
    sh.add_argument("--markdown", action="store_true", help="as an Obsidian note")

    se = sub.add_parser("search", help="full-text search over every page you've read")
    se.add_argument("query", nargs="+")
    se.add_argument("--doc", type=int, help="only this document")
    se.add_argument("-n", "--limit", type=int, default=10)

    sub.add_parser("mcp", help="run the MCP server over stdio (for Claude Desktop, Claude Code, …)")
    sub.add_parser("demo", help="see a checked summary on a fictional report (no API key needed)")
    return p


COMMANDS = {"summarize": cmd_summarize, "sum": cmd_summarize, "ask": cmd_ask, "list": cmd_list, "ls": cmd_list,
            "show": cmd_show, "search": cmd_search, "mcp": cmd_mcp, "demo": cmd_demo}


def main(argv: list[str] | None = None) -> int:
    load_env(Path.cwd() / ".env")
    load_env(DATA_DIR / ".env")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    settings = Settings.from_env()
    if args.db:
        settings.db_path = Path(args.db).expanduser()

    from .summarize import ClaudeError

    try:
        return COMMANDS[args.command](args, settings)
    except ClaudeError as e:
        return fail(str(e))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
