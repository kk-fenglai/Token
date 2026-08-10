"""Incremental scan of JSONL roots into SQLite.

A file is re-parsed whole whenever (mtime_ns, size) changed; the last-wins
upsert makes that idempotent. Events are never deleted when a log file
disappears — the DB is the system of record (Claude Code prunes old logs).
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config
from .db import locked_conn, set_meta
from .parser import UPSERT_SQL, parse_file


class SyncService:
    def __init__(self) -> None:
        self._run_lock = threading.Lock()
        self.syncing = False
        self.last_sync_at: str | None = None
        self.last_error: str | None = None
        self.missing_roots: list[str] = []
        self.files_seen = 0
        self.files_parsed = 0

    def sync_once(self) -> dict:
        """Blocking incremental sync. Returns a status dict; raises nothing."""
        if not self._run_lock.acquire(blocking=False):
            return {"busy": True, **self.status()}
        self.syncing = True
        try:
            self._scan()
            self.last_error = None
        except Exception as e:  # keep the service alive whatever happens
            self.last_error = f"{type(e).__name__}: {e}"
        finally:
            self.last_sync_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            set_meta("last_sync_at", self.last_sync_at)
            self.syncing = False
            self._run_lock.release()
        return self.status()

    def _scan(self) -> None:
        cfg = load_config()
        self.missing_roots = []
        files: list[Path] = []
        for root in cfg.get("scan_roots", []):
            rp = Path(root)
            if not rp.exists():
                self.missing_roots.append(root)
                continue
            files.extend(rp.glob("**/*.jsonl"))
        self.files_seen = len(files)

        with locked_conn() as conn:
            known = {
                r["path"]: (r["mtime_ns"], r["size"])
                for r in conn.execute("SELECT path, mtime_ns, size FROM sync_files")
            }

        parsed = 0
        for fp in files:
            try:
                st = fp.stat()
            except OSError:
                continue
            key = str(fp)
            if known.get(key) == (st.st_mtime_ns, st.st_size):
                continue
            res = parse_file(fp)
            with locked_conn() as conn:
                if res.events:
                    conn.executemany(UPSERT_SQL, res.events)
                conn.execute(
                    "INSERT INTO sync_files(path, mtime_ns, size, parsed_at, line_count, skipped_count, error_count) "
                    "VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET "
                    "mtime_ns=excluded.mtime_ns, size=excluded.size, parsed_at=excluded.parsed_at, "
                    "line_count=excluded.line_count, skipped_count=excluded.skipped_count, error_count=excluded.error_count",
                    (key, st.st_mtime_ns, st.st_size,
                     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     res.line_count, res.skipped_count, res.error_count),
                )
                conn.commit()
            parsed += 1
        self.files_parsed = parsed

    def status(self) -> dict:
        with locked_conn() as conn:
            events_total = conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
            errors = conn.execute("SELECT COALESCE(SUM(error_count),0) c FROM sync_files").fetchone()["c"]
        return {
            "syncing": self.syncing,
            "last_sync_at": self.last_sync_at,
            "files_seen": self.files_seen,
            "files_parsed": self.files_parsed,
            "events_total": events_total,
            "parse_errors": errors,
            "missing_roots": self.missing_roots,
            "last_error": self.last_error,
        }


service = SyncService()


if __name__ == "__main__":  # manual run: python -m app.sync
    import json as _json

    print(_json.dumps(service.sync_once(), indent=2, ensure_ascii=False))
