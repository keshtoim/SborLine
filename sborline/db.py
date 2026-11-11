import os
import sqlite3
import sys
from pathlib import Path


def _resource(name: str) -> Path:
    # в собранном .exe ресурсы распакованы во временную папку PyInstaller
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "sborline" / name


def default_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home())) / "SborLine"
    base.mkdir(parents=True, exist_ok=True)
    return base / "sborline.db"


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn, table) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def init_schema(conn: sqlite3.Connection) -> None:
    # базы первой версии: CREATE IF NOT EXISTS не добавит новые колонки, поэтому сначала ALTER
    if "operations" in {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}:
        if "requires_permit" not in _columns(conn, "operations"):
            conn.execute("ALTER TABLE operations ADD COLUMN requires_permit INTEGER NOT NULL DEFAULT 0")
        if "details" not in _columns(conn, "audit_log"):
            conn.execute("ALTER TABLE audit_log ADD COLUMN details TEXT")
    conn.executescript(_resource("schema.sql").read_text(encoding="utf-8"))


def is_empty(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
