"""Claude Code JSONL parsing.

Only `type == "assistant"` lines with a `message.usage` object count. The same
message.id can appear on several lines (streaming updates emit cumulative
usage), so within a file we keep the LAST occurrence per (message_id,
request_id), and the DB upsert is also last-wins — re-parsing is idempotent.

Besides the four token counters, each event keeps what the message *did*: the
tool calls it made (`tool_names`, JSON list) and whether it ran inside a
subagent (`is_sidechain`, `agent_name`). Subagent transcripts live under
`<session>/subagents/agent-*.jsonl` and carry the parent's sessionId, so their
cost rolls up into the parent session automatically.

Bump PARSER_VERSION whenever the tuple shape or the extraction rules change;
`sync` then re-parses every file still on disk.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PARSER_VERSION = 2


@dataclass
class ParseResult:
    events: list[tuple]
    line_count: int = 0
    skipped_count: int = 0
    error_count: int = 0


def model_family(model: str) -> str:
    m = (model or "").lower()
    for fam in ("fable", "opus", "sonnet", "haiku"):
        if fam in m:
            return fam
    return "other"


def normalize_cwd(cwd: str) -> str:
    p = (cwd or "").replace("\\", "/").rstrip("/")
    if len(p) >= 2 and p[1] == ":":
        p = p[0].lower() + p[1:]
    return p or "(unknown)"


def project_name(norm_path: str) -> str:
    base = norm_path.rstrip("/").rsplit("/", 1)[-1]
    return base or norm_path


def normalize_ts(raw: str) -> str | None:
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tool_names(msg: dict) -> list[str]:
    """Names of the tool_use blocks in an assistant message, in order."""
    content = msg.get("content")
    if not isinstance(content, list):
        return []
    return [str(b.get("name") or "unknown")
            for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]


def parse_file(path: Path) -> ParseResult:
    res = ParseResult(events=[])
    # last-wins within the file: dict keyed by (message_id, request_id)
    by_key: dict[tuple[str, str], tuple] = {}
    src = str(path)
    in_subagent_dir = "/subagents/" in src.replace("\\", "/")
    try:
        f = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        res.error_count += 1
        return res
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            res.line_count += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                res.error_count += 1
                continue
            if not isinstance(obj, dict) or obj.get("type") != "assistant":
                res.skipped_count += 1
                continue
            msg = obj.get("message") or {}
            usage = msg.get("usage")
            msg_id = msg.get("id")
            ts = normalize_ts(obj.get("timestamp") or "")
            if not isinstance(usage, dict) or not msg_id or not ts:
                res.skipped_count += 1
                continue
            norm = normalize_cwd(obj.get("cwd") or "")
            key = (msg_id, obj.get("requestId") or "")
            tools = tool_names(msg)
            sidechain = bool(obj.get("isSidechain")) or in_subagent_dir
            agent = obj.get("attributionAgent") or obj.get("agentType")
            by_key[key] = (
                msg_id,
                obj.get("requestId") or "",
                ts,
                msg.get("model") or "unknown",
                model_family(msg.get("model") or ""),
                norm,
                project_name(norm),
                obj.get("session_id") or obj.get("sessionId"),
                int(usage.get("input_tokens") or 0),
                int(usage.get("output_tokens") or 0),
                int(usage.get("cache_creation_input_tokens") or 0),
                int(usage.get("cache_read_input_tokens") or 0),
                src,
                json.dumps(tools) if tools else None,
                len(tools),
                1 if sidechain else 0,
                str(agent) if agent else None,
            )
    res.events = list(by_key.values())
    return res


UPSERT_SQL = """
INSERT INTO events (message_id, request_id, ts, model, model_family,
                    project_path, project_name, session_id,
                    input_tokens, output_tokens, cache_write_tokens, cache_read_tokens,
                    src_file, tool_names, tool_count, is_sidechain, agent_name)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(message_id, request_id) DO UPDATE SET
  ts=excluded.ts, model=excluded.model, model_family=excluded.model_family,
  project_path=excluded.project_path, project_name=excluded.project_name,
  session_id=excluded.session_id,
  input_tokens=excluded.input_tokens, output_tokens=excluded.output_tokens,
  cache_write_tokens=excluded.cache_write_tokens, cache_read_tokens=excluded.cache_read_tokens,
  src_file=excluded.src_file, tool_names=excluded.tool_names, tool_count=excluded.tool_count,
  is_sidechain=excluded.is_sidechain, agent_name=excluded.agent_name
"""
