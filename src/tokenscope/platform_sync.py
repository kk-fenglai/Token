"""AIPM 平台模式上报（agent 侧，PRD project_mange/docs/aipm-platform-prd-v0.2.md §6.4）。

本地模式完全不受影响：仅当 config.json 配置了 ``server_url`` + ``api_token`` 时启用。
流程：sync_once()（本地解析，零改动复用）→ 从本地 SQLite 读取新事件 →
按 ``project_mappings`` 最长目录前缀映射到平台项目 key → 批量 POST
``/api/ingest/events``（幂等键 message_id+request_id，断网重试安全）→
游标（本地 events.id）记录在 meta 表 ``platform_last_event_id``。

config.json 新增键::

    "server_url": "http://localhost:4000",
    "api_token": "aipm_xxx",
    "machine_id": "my-laptop",              # 可选
    "project_mappings": [                    # 可选；为空时启动自动从服务端拉取
      {"local_path_prefix": "C:/Users/me/code/acme-web", "project_key": "ACME-WEB"}
    ]
"""
from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config
from .db import locked_conn, set_meta
from .sync import service

BATCH_MAX = 2000
_KEY_META = "platform_last_event_id"


def platform_enabled(cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()
    return bool(cfg.get("server_url") and cfg.get("api_token"))


def _request(cfg: dict, method: str, path: str, body: dict | None = None) -> dict:
    url = cfg["server_url"].rstrip("/") + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json",
        "X-Api-Token": cfg["api_token"],
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _normalize_prefix(p: str) -> str:
    p = (p or "").replace("\\", "/").rstrip("/")
    if len(p) >= 2 and p[1] == ":":
        p = p[0].lower() + p[1:]
    return p


def _mappings(cfg: dict) -> list[tuple[str, str]]:
    """[(normalized_prefix, project_key)]，本地配置优先；否则从服务端拉取。"""
    raw = cfg.get("project_mappings") or []
    out = [(_normalize_prefix(m.get("local_path_prefix", "")), m.get("project_key", "")) for m in raw]
    out = [(p, k) for p, k in out if p and k]
    if not out:
        try:
            remote = _request(cfg, "GET", "/api/ingest/config")
            out = [(_normalize_prefix(m["localPathPrefix"]), m["projectKey"]) for m in remote.get("mappings", [])]
        except Exception:
            out = []
    return sorted(out, key=lambda x: -len(x[0]))  # 最长前缀优先


def _project_key_for(path: str, mappings: list[tuple[str, str]]) -> str | None:
    norm = _normalize_prefix(path)
    for prefix, key in mappings:
        if norm == prefix or norm.startswith(prefix + "/"):
            return key
    return None


def _git_branch(path: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True, timeout=3)
        b = r.stdout.strip()
        return b if r.returncode == 0 and b and b != "HEAD" else None
    except Exception:
        return None


def push_once(sync_first: bool = True) -> dict:
    """本地增量解析 + 上报到平台。返回状态 dict；网络失败不推进游标。"""
    cfg = load_config()
    if not platform_enabled(cfg):
        return {"enabled": False, "hint": "set server_url + api_token in config.json"}
    if sync_first:
        service.sync_once()

    mappings = _mappings(cfg)
    machine_id = cfg.get("machine_id") or ""

    with locked_conn() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (_KEY_META,)).fetchone()
        last_id = int(row["value"]) if row else 0
        rows = conn.execute(
            "SELECT id, message_id, request_id, ts, model, project_path, project_name, session_id, "
            "input_tokens, output_tokens, cache_write_tokens, cache_read_tokens "
            "FROM events WHERE id > ? ORDER BY id ASC", (last_id,)).fetchall()

    total = len(rows)
    unmapped: dict[str, int] = {}
    sent = created = updated = 0
    rejected: dict[str, list[str]] = {}
    branch_cache: dict[str, str | None] = {}
    max_id = last_id

    batch: list[dict] = []

    def flush() -> None:
        nonlocal sent, created, updated, rejected
        if not batch:
            return
        res = _request(cfg, "POST", "/api/ingest/events",
                       {"protocol": 1, "machineId": machine_id, "events": batch})
        sent += res.get("accepted", 0)
        created += res.get("created", 0)
        updated += res.get("updated", 0)
        for k, v in (res.get("rejected") or {}).items():
            if v:
                rejected.setdefault(k, []).extend(x for x in v if x not in rejected.get(k, []))
        batch.clear()

    try:
        for r in rows:
            key = _project_key_for(r["project_path"], mappings)
            if key is None:
                unmapped[r["project_path"]] = unmapped.get(r["project_path"], 0) + 1
                max_id = max(max_id, r["id"])   # 未映射：跳过但推进游标（配置映射后可 reset 重推）
                continue
            path = r["project_path"]
            if path not in branch_cache:
                branch_cache[path] = _git_branch(path) if Path(path).exists() else None
            batch.append({
                "projectKey": key,
                "messageId": r["message_id"],
                "requestId": r["request_id"] or "",
                "ts": r["ts"],
                "model": r["model"],
                "projectPath": r["project_path"],
                "projectName": r["project_name"],
                "sessionId": r["session_id"],
                "inputTokens": r["input_tokens"],
                "outputTokens": r["output_tokens"],
                "cacheWriteTokens": r["cache_write_tokens"],
                "cacheReadTokens": r["cache_read_tokens"],
                "gitBranch": branch_cache[path],
            })
            max_id = max(max_id, r["id"])
            if len(batch) >= BATCH_MAX:
                flush()
        flush()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        # 网络失败：不推进游标，下次重推（服务端幂等）
        return {"enabled": True, "ok": False, "error": str(e), "pending": total,
                "pushed_before_error": sent}

    set_meta(_KEY_META, str(max_id))

    # 套餐信息（best-effort）
    try:
        from .subscription import detect  # type: ignore
        prof = detect()
        if prof and prof.get("plan"):
            _request(cfg, "POST", "/api/ingest/subscription", {"plan": prof["plan"]})
    except Exception:
        pass

    return {
        "enabled": True, "ok": True,
        "scanned": total, "sent": sent, "created": created, "updated": updated,
        "unmapped_paths": unmapped, "rejected": rejected,
        "cursor": max_id,
        "pushed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def reset_cursor() -> dict:
    """重置上报游标（配置好映射后全量重推；服务端幂等，安全）。"""
    set_meta(_KEY_META, "0")
    return {"ok": True, "cursor": 0}


def bind_session(requirement_key: str, session_id: str) -> dict:
    """把会话绑定到平台需求（PF-10 显式标注）。"""
    cfg = load_config()
    if not platform_enabled(cfg):
        return {"enabled": False}
    # 先解析需求 key → id
    data = _request(cfg, "GET", f"/api/requirements?q={urllib.parse.quote(requirement_key)}&pageSize=5")
    match = next((i for i in data.get("items", []) if i["key"].upper() == requirement_key.upper()), None)
    if not match:
        return {"ok": False, "error": f"requirement {requirement_key} not found or not visible"}
    return _request(cfg, "POST", f"/api/requirements/{match['id']}/bind", {"sessionId": session_id})


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="tokenscope-push", description="Push local usage to the AIPM platform")
    ap.add_argument("--no-sync", action="store_true", help="skip local JSONL scan before pushing")
    ap.add_argument("--reset-cursor", action="store_true", help="re-push all local events (idempotent server-side)")
    args = ap.parse_args()
    if args.reset_cursor:
        print(json.dumps(reset_cursor()))
    print(json.dumps(push_once(sync_first=not args.no_sync), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
