"""SQLite connection (WAL) and schema.

Single shared connection guarded by a threading.Lock: FastAPI handlers and the
background sync (run via asyncio.to_thread) both touch it, and serializing at
this scale is simpler and safer than a pool.

Schema changes are additive: `MIGRATIONS` lists columns that later versions
added to `events`, and `get_conn` applies whichever are missing. Existing rows
keep NULL/0 in the new columns until the file they came from is re-parsed —
`sync` forces that when the parser version changes.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager

from .config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id                 INTEGER PRIMARY KEY,
  message_id         TEXT NOT NULL,
  request_id         TEXT NOT NULL DEFAULT '',
  ts                 TEXT NOT NULL,
  model              TEXT NOT NULL,
  model_family       TEXT NOT NULL,
  project_path       TEXT NOT NULL,
  project_name       TEXT NOT NULL,
  session_id         TEXT,
  input_tokens       INTEGER NOT NULL DEFAULT 0,
  output_tokens      INTEGER NOT NULL DEFAULT 0,
  cache_write_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens  INTEGER NOT NULL DEFAULT 0,
  source             TEXT NOT NULL DEFAULT 'claude_code',
  src_file           TEXT,
  UNIQUE (message_id, request_id)
);
CREATE INDEX IF NOT EXISTS idx_events_ts        ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_proj_ts   ON events(project_path, ts);
CREATE INDEX IF NOT EXISTS idx_events_family_ts ON events(model_family, ts);
CREATE INDEX IF NOT EXISTS idx_events_session   ON events(session_id);

CREATE TABLE IF NOT EXISTS sync_files (
  path          TEXT PRIMARY KEY,
  mtime_ns      INTEGER NOT NULL,
  size          INTEGER NOT NULL,
  parsed_at     TEXT NOT NULL,
  line_count    INTEGER,
  skipped_count INTEGER,
  error_count   INTEGER
);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

# (column, declaration) pairs added after v1.1. Order matters only for
# readability; each is applied independently when absent.
MIGRATIONS: list[tuple[str, str]] = [
    # JSON list of tool names the assistant message invoked, e.g. ["Read","Bash"].
    ("tool_names", "TEXT"),
    ("tool_count", "INTEGER NOT NULL DEFAULT 0"),
    # 1 when the message came from a subagent transcript (isSidechain).
    ("is_sidechain", "INTEGER NOT NULL DEFAULT 0"),
    # Subagent type ("Explore", "general-purpose", ...) when known.
    ("agent_name", "TEXT"),
]

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()


def _migrate(conn: sqlite3.Connection) -> None:
    have = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    for col, decl in MIGRATIONS:
        if col not in have:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col} {decl}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_side ON events(is_sidechain)")
    conn.commit()


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(db_path(), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("PRAGMA busy_timeout=5000")
        _conn.executescript(SCHEMA)
        _migrate(_conn)
    return _conn


def reset_conn() -> None:
    """Close the shared connection (tests point the DB elsewhere between runs)."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


@contextmanager
def locked_conn():
    conn = get_conn()
    with _lock:
        yield conn


def set_meta(key: str, value: str) -> None:
    with locked_conn() as conn:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()


def get_meta(key: str) -> str | None:
    with locked_conn() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None
