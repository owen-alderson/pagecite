"""Settings come from environment variables, optionally loaded from a .env file."""

import os
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(os.environ.get("PAGECITE_HOME", Path.home() / ".pagecite"))


def load_env(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ without overriding variables already set."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    db_path: Path = DATA_DIR / "library.db"
    model: str = "claude-opus-5-5"
    notes_dir: Path | None = None  # where `summarize` writes Markdown notes when no -o is given

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ.get
        notes = e("PAGECITE_NOTES_DIR", "").strip()
        return cls(
            db_path=Path(e("PAGECITE_DB", str(DATA_DIR / "library.db"))).expanduser(),
            model=e("PAGECITE_MODEL", "claude-opus-5-5"),
            notes_dir=Path(notes).expanduser() if notes else None,
        )
