"""SQLite connection (WAL) and schema.

Single shared connection guarded by a threading.Lock: FastAPI handlers and the
background sync (run via asyncio.to_thread) both touch it, and serializing at
this scale is simpler and safer than a pool.
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

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(db_path(), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("PRAGMA busy_timeout=5000")
        _conn.executescript(SCHEMA)
    return _conn


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
