"""SQLite persistence for the assistant.

Messages are append-only and stored exactly as the API needs them back —
including `reasoning_content`, which DeepSeek requires on every assistant
message of a request that carries `tools`. Never rewriting earlier rows also
keeps the request prefix byte-stable, which is what DeepSeek's prompt cache
keys on.

The assistant's own spend lives in `agent_requests`, not in `events`, so it
never distorts the Claude Code analytics the rest of the app is about.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from ..db import locked_conn

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_conversations (
  id           TEXT PRIMARY KEY,
  kind         TEXT NOT NULL DEFAULT 'chat',
  title        TEXT NOT NULL DEFAULT '',
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL,
  model        TEXT,
  page_context TEXT,
  archived     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS agent_messages (
  id                INTEGER PRIMARY KEY,
  conversation_id   TEXT NOT NULL,
  seq               INTEGER NOT NULL,
  run_id            TEXT,
  role              TEXT NOT NULL,
  content           TEXT,
  reasoning_content TEXT,
  tool_calls        TEXT,
  tool_call_id      TEXT,
  display           TEXT,
  created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_messages_conv ON agent_messages(conversation_id, seq);
CREATE TABLE IF NOT EXISTS agent_runs (
  id                TEXT PRIMARY KEY,
  conversation_id   TEXT NOT NULL,
  trigger           TEXT NOT NULL DEFAULT 'chat',
  model             TEXT,
  started_at        TEXT NOT NULL,
  ended_at          TEXT,
  status            TEXT NOT NULL DEFAULT 'running',
  error             TEXT,
  iterations        INTEGER NOT NULL DEFAULT 0,
  hit_tokens        INTEGER NOT NULL DEFAULT 0,
  miss_tokens       INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  reasoning_tokens  INTEGER NOT NULL DEFAULT 0,
  cost_usd          REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS agent_tool_calls (
  id              INTEGER PRIMARY KEY,
  run_id          TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  tool_call_id    TEXT NOT NULL,
  name            TEXT NOT NULL,
  kind            TEXT,
  args            TEXT,
  status          TEXT NOT NULL,
  result_preview  TEXT,
  result_chars    INTEGER,
  duration_ms     INTEGER,
  started_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_conv ON agent_tool_calls(conversation_id);
CREATE TABLE IF NOT EXISTS agent_requests (
  id          INTEGER PRIMARY KEY,
  run_id      TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  ts          TEXT NOT NULL,
  model       TEXT NOT NULL,
  hit         INTEGER NOT NULL DEFAULT 0,
  miss        INTEGER NOT NULL DEFAULT 0,
  completion  INTEGER NOT NULL DEFAULT 0,
  reasoning   INTEGER NOT NULL DEFAULT 0,
  cost_usd    REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_agent_requests_ts ON agent_requests(ts);
"""

def _conn():
    """locked_conn() with the schema ensured. Checked against sqlite_master
    each time (cheap) rather than cached, because tests swap the database."""
    ctx = locked_conn()
    conn = ctx.__enter__()
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_requests'").fetchone() is None:
        conn.executescript(_SCHEMA)
    return ctx, conn


class _Tx:
    def __enter__(self):
        self.ctx, conn = _conn()
        return conn

    def __exit__(self, *exc):
        return self.ctx.__exit__(*exc)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _j(v) -> str | None:
    return None if v is None else json.dumps(v, ensure_ascii=False)


def _unj(v, default=None):
    if v is None:
        return default
    try:
        return json.loads(v)
    except ValueError:
        return default


# ---------------------------------------------------------- conversations ----

def create_conversation(kind: str = "chat", title: str = "", page_context: dict | None = None,
                        model: str | None = None) -> str:
    cid = uuid.uuid4().hex[:16]
    ts = now_iso()
    with _Tx() as conn:
        conn.execute("INSERT INTO agent_conversations(id, kind, title, created_at, updated_at, model, page_context)"
                     " VALUES(?,?,?,?,?,?,?)", (cid, kind, title, ts, ts, model, _j(page_context)))
        conn.commit()
    return cid


def _conv_row(r) -> dict:
    return {"id": r["id"], "kind": r["kind"], "title": r["title"], "created_at": r["created_at"],
            "updated_at": r["updated_at"], "model": r["model"],
            "page_context": _unj(r["page_context"]), "archived": bool(r["archived"])}


def list_conversations(kind: str | None = None, limit: int = 100) -> list[dict]:
    q = ("SELECT c.*, (SELECT COALESCE(SUM(cost_usd),0) FROM agent_runs r WHERE r.conversation_id=c.id) cost "
         "FROM agent_conversations c WHERE archived=0")
    params: list = []
    if kind:
        q += " AND kind=?"
        params.append(kind)
    q += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    with _Tx() as conn:
        rows = conn.execute(q, params).fetchall()
    return [{**_conv_row(r), "cost_usd": round(r["cost"] or 0, 6)} for r in rows]


def get_conversation(cid: str) -> dict | None:
    with _Tx() as conn:
        r = conn.execute("SELECT * FROM agent_conversations WHERE id=?", (cid,)).fetchone()
    return _conv_row(r) if r else None


def update_conversation(cid: str, *, title: str | None = None, archived: bool | None = None,
                        touch: bool = False) -> None:
    sets, params = [], []
    if title is not None:
        sets.append("title=?")
        params.append(title)
    if archived is not None:
        sets.append("archived=?")
        params.append(int(archived))
    if touch or sets:
        sets.append("updated_at=?")
        params.append(now_iso())
    if not sets:
        return
    with _Tx() as conn:
        conn.execute(f"UPDATE agent_conversations SET {', '.join(sets)} WHERE id=?", (*params, cid))
        conn.commit()


def delete_conversation(cid: str) -> None:
    with _Tx() as conn:
        for table in ("agent_messages", "agent_tool_calls", "agent_requests", "agent_runs"):
            conn.execute(f"DELETE FROM {table} WHERE conversation_id=?", (cid,))
        conn.execute("DELETE FROM agent_conversations WHERE id=?", (cid,))
        conn.commit()


# --------------------------------------------------------------- messages ----

def append_message(cid: str, msg: dict, run_id: str | None = None, display: dict | None = None) -> int:
    """`msg` is an API message dict. `display` holds UI-only extras (e.g. the
    user's text without the page-context preamble) and is never sent back."""
    with _Tx() as conn:
        seq = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM agent_messages WHERE conversation_id=?",
                           (cid,)).fetchone()[0]
        conn.execute(
            "INSERT INTO agent_messages(conversation_id, seq, run_id, role, content, reasoning_content, tool_calls,"
            " tool_call_id, display, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (cid, seq, run_id, msg["role"], msg.get("content"), msg.get("reasoning_content"),
             _j(msg.get("tool_calls")), msg.get("tool_call_id"), _j(display), now_iso()))
        conn.execute("UPDATE agent_conversations SET updated_at=? WHERE id=?", (now_iso(), cid))
        conn.commit()
    return seq


def load_api_messages(cid: str) -> list[dict]:
    """Exact API dicts, in order. `reasoning_content` is replayed on every
    assistant message (DeepSeek's rule for requests that carry `tools`)."""
    with _Tx() as conn:
        rows = conn.execute("SELECT * FROM agent_messages WHERE conversation_id=? ORDER BY seq", (cid,)).fetchall()
    out = []
    for r in rows:
        m: dict = {"role": r["role"]}
        if r["role"] == "assistant":
            m["content"] = r["content"] or ""
            if r["reasoning_content"]:
                m["reasoning_content"] = r["reasoning_content"]
            calls = _unj(r["tool_calls"])
            if calls:
                m["tool_calls"] = calls
        elif r["role"] == "tool":
            m["tool_call_id"] = r["tool_call_id"]
            m["content"] = r["content"] or ""
        else:
            m["content"] = r["content"] or ""
        out.append(m)
    return out


def ui_messages(cid: str) -> dict:
    """Conversation for the UI: user / assistant turns with their tool calls
    folded in, tool results taken from the audit log (full preview)."""
    with _Tx() as conn:
        rows = conn.execute("SELECT * FROM agent_messages WHERE conversation_id=? ORDER BY seq", (cid,)).fetchall()
        calls = conn.execute("SELECT * FROM agent_tool_calls WHERE conversation_id=? ORDER BY id", (cid,)).fetchall()
        runs = conn.execute("SELECT * FROM agent_runs WHERE conversation_id=? ORDER BY started_at", (cid,)).fetchall()
    by_call = {c["tool_call_id"]: c for c in calls}
    out: list[dict] = []
    for r in rows:
        display = _unj(r["display"], {}) or {}
        if r["role"] == "user":
            out.append({"role": "user", "content": display.get("text", r["content"] or ""), "seq": r["seq"],
                        "at": r["created_at"], "run_id": r["run_id"]})
        elif r["role"] == "assistant":
            tcs = []
            for tc in _unj(r["tool_calls"], []) or []:
                log = by_call.get(tc.get("id"))
                tcs.append({"id": tc.get("id"), "name": tc.get("function", {}).get("name"),
                            "args": tc.get("function", {}).get("arguments"),
                            "kind": log["kind"] if log else None, "status": log["status"] if log else "pending",
                            "result": log["result_preview"] if log else None,
                            "chars": log["result_chars"] if log else None,
                            "ms": log["duration_ms"] if log else None})
            out.append({"role": "assistant", "content": r["content"] or "", "reasoning": r["reasoning_content"] or "",
                        "tool_calls": tcs, "seq": r["seq"], "at": r["created_at"], "run_id": r["run_id"]})
    return {"messages": out, "runs": [dict(r) for r in runs]}


# ------------------------------------------------------------- runs & logs ----

def start_run(cid: str, trigger: str, model: str) -> str:
    rid = uuid.uuid4().hex[:16]
    with _Tx() as conn:
        conn.execute("INSERT INTO agent_runs(id, conversation_id, trigger, model, started_at) VALUES(?,?,?,?,?)",
                     (rid, cid, trigger, model, now_iso()))
        conn.commit()
    return rid


def finish_run(rid: str, status: str, error: str | None = None, iterations: int = 0) -> dict:
    with _Tx() as conn:
        conn.execute("UPDATE agent_runs SET ended_at=?, status=?, error=?, iterations=? WHERE id=?",
                     (now_iso(), status, error, iterations, rid))
        conn.commit()
        r = conn.execute("SELECT * FROM agent_runs WHERE id=?", (rid,)).fetchone()
    return dict(r) if r else {}


def record_request(rid: str, cid: str, model: str, usage: dict, cost: float) -> None:
    hit, miss = usage.get("hit", 0), usage.get("miss", 0)
    comp, reas = usage.get("completion", 0), usage.get("reasoning", 0)
    with _Tx() as conn:
        conn.execute("INSERT INTO agent_requests(run_id, conversation_id, ts, model, hit, miss, completion, reasoning,"
                     " cost_usd) VALUES(?,?,?,?,?,?,?,?,?)", (rid, cid, now_iso(), model, hit, miss, comp, reas, cost))
        conn.execute("UPDATE agent_runs SET hit_tokens=hit_tokens+?, miss_tokens=miss_tokens+?, "
                     "completion_tokens=completion_tokens+?, reasoning_tokens=reasoning_tokens+?, "
                     "cost_usd=cost_usd+? WHERE id=?", (hit, miss, comp, reas, cost, rid))
        conn.commit()


def log_tool_call(rid: str, cid: str, tool_call_id: str, name: str, kind: str | None, args: str | None,
                  status: str, preview: str | None, chars: int | None, ms: int | None) -> None:
    with _Tx() as conn:
        conn.execute("INSERT INTO agent_tool_calls(run_id, conversation_id, tool_call_id, name, kind, args, status,"
                     " result_preview, result_chars, duration_ms, started_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (rid, cid, tool_call_id, name, kind, args, status, preview, chars, ms, now_iso()))
        conn.commit()


def conversation_usage(cid: str) -> dict:
    with _Tx() as conn:
        r = conn.execute("SELECT COALESCE(SUM(hit),0) hit, COALESCE(SUM(miss),0) miss, COALESCE(SUM(completion),0) "
                         "completion, COALESCE(SUM(cost_usd),0) cost, COUNT(*) n FROM agent_requests "
                         "WHERE conversation_id=?", (cid,)).fetchone()
    return {"hit": r["hit"], "miss": r["miss"], "completion": r["completion"],
            "cost_usd": round(r["cost"], 6), "requests": r["n"]}


_RANGE_DAYS = {"today": 0, "7d": 7, "30d": 30, "90d": 90, "all": None}


def usage_summary(range_key: str = "30d") -> dict:
    """The assistant's own DeepSeek spend (estimated), by day and model."""
    days = _RANGE_DAYS.get(range_key, 30)
    where, params = "", []
    if days is not None:
        local_now = datetime.now().astimezone()
        start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
        where = "WHERE ts >= ?"
        params.append(start_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    with _Tx() as conn:
        tot = conn.execute(f"SELECT COALESCE(SUM(hit),0) hit, COALESCE(SUM(miss),0) miss, "
                           f"COALESCE(SUM(completion),0) completion, COALESCE(SUM(reasoning),0) reasoning, "
                           f"COALESCE(SUM(cost_usd),0) cost, COUNT(*) n FROM agent_requests {where}", params).fetchone()
        by_model = conn.execute(f"SELECT model, COALESCE(SUM(cost_usd),0) cost, COUNT(*) n, "
                                f"COALESCE(SUM(hit+miss+completion),0) tokens FROM agent_requests {where} "
                                f"GROUP BY model ORDER BY cost DESC", params).fetchall()
        rows = conn.execute(f"SELECT ts, cost_usd FROM agent_requests {where}", params).fetchall()
    daily: dict[str, float] = {}
    for r in rows:
        try:
            d = datetime.strptime(r["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone()
        except ValueError:
            continue
        key = d.strftime("%Y-%m-%d")
        daily[key] = daily.get(key, 0.0) + (r["cost_usd"] or 0)
    prompt = tot["hit"] + tot["miss"]
    return {
        "range": range_key, "estimated": True, "requests": tot["n"],
        "tokens": {"input_cache_hit": tot["hit"], "input_cache_miss": tot["miss"],
                   "output": tot["completion"], "reasoning": tot["reasoning"]},
        "cache_hit_rate": round(tot["hit"] / prompt, 4) if prompt else None,
        "cost_usd": round(tot["cost"], 4),
        "by_model": [{"model": r["model"], "cost_usd": round(r["cost"], 4), "requests": r["n"], "tokens": r["tokens"]}
                     for r in by_model],
        "daily": [{"date": k, "cost_usd": round(v, 4)} for k, v in sorted(daily.items())],
    }
