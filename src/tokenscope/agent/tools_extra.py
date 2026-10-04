"""Tools that exist only for the assistant (the MCP server does not expose
them). Docstrings are the descriptions the model sees — keep them precise.

Every path argument is normalized and must belong to a tracked dev project
(dev_projects snapshot); anything else is refused by the underlying modules.
"""
from __future__ import annotations

import os

from .. import dev_project_detail, git_publish, insights, queries
from ..db import locked_conn
from ..parser import normalize_cwd
from ..pricing import load_pricing


def _norm(path: str) -> str:
    return normalize_cwd(path.strip().strip('"'))


# ---------------------------------------------------------------- analysis ----

def get_efficiency_snapshot(range: str = "30d") -> dict:
    """Everything the cost advisor needs in one call, for "today", "7d", "30d",
    "month" or "all": prompt-cache hit rate (cache_read / all prompt tokens),
    cost share per model, subagent (sidechain) cost share, and the sessions
    whose peak context exceeded 150K tokens (the usual /clear candidates),
    plus the most expensive sessions. Costs are virtual API-equivalent USD."""
    start, end = queries.resolve_range(range)
    where, params = insights._where(start, end, None)
    pricing = load_pricing()
    with locked_conn() as conn:
        rows = conn.execute(
            f"SELECT model, model_family f, is_sidechain side, {insights.TOKEN_SUM}, COUNT(*) n "
            f"FROM events {where} GROUP BY model, model_family, is_sidechain", params).fetchall()
    tokens = insights._blank_tokens()
    total = side = 0.0
    by_model: dict[str, dict] = {}
    for r in rows:
        insights._add_tokens(tokens, r)
        c = insights._cost(r, pricing)
        total += c
        if r["side"]:
            side += c
        m = by_model.setdefault(r["model"], {"model": r["model"], "family": r["f"], "cost": 0.0, "calls": 0})
        m["cost"] += c
        m["calls"] += r["n"]
    prompt = tokens["input"] + tokens["cache_write"] + tokens["cache_read"]
    models = sorted(by_model.values(), key=lambda m: -m["cost"])
    for m in models:
        m["cost"] = round(m["cost"], 2)
        m["cost_share"] = round(m["cost"] / total, 3) if total else 0.0
    sess = insights.sessions(range, sort="cost", page_size=200)["items"]
    bloated = sorted((s for s in sess if s["ctx_max"] >= insights.CONTEXT_BLOAT_TOKENS), key=lambda s: -s["ctx_max"])
    slim = lambda s: {k: s.get(k) for k in ("session_id", "name", "cost", "messages", "ctx_max", "subagent_cost",  # noqa: E731
                                            "first_ts", "models")}
    return {
        "range": range, "cost_usd": round(total, 2), "tokens": tokens,
        "cache_hit_rate": round(tokens["cache_read"] / prompt, 4) if prompt else None,
        "subagent_cost_share": round(side / total, 3) if total else 0.0,
        "models": models[:10],
        "context_bloat_threshold": insights.CONTEXT_BLOAT_TOKENS,
        "bloated_sessions": [slim(s) for s in bloated[:8]],
        "bloated_session_count": len(bloated),
        "top_sessions": [slim(s) for s in sess[:8]],
    }


def get_agent_usage(range: str = "30d") -> dict:
    """The assistant's OWN DeepSeek API spend (estimated from DeepSeek list
    prices): requests, cache-hit / cache-miss / output tokens, USD by model
    and by day. range: "today", "7d", "30d", "90d" or "all". This is separate
    from the Claude Code usage every other tool reports."""
    from . import store
    return store.usage_summary(range)


# ------------------------------------------------------------ dev projects ----

def get_dev_project_detail(path: str) -> dict:
    """One tracked dev project: git state, README excerpt, languages, detected
    stack, recent commits, branches, contributors, its Claude Code token usage,
    and the user's own notes (alias / description / tags / stage / notes).
    `path` is the project path from get_dev_projects."""
    d = dev_project_detail.detail(_norm(path))
    readme = d.get("readme")
    if readme:
        readme = {**readme, "content": readme["content"][:4000], "truncated": readme["truncated"] or len(readme["content"]) > 4000}
    git = dict(d["git"])
    git["recent_commits"] = git["recent_commits"][:10]
    item = {k: v for k, v in d["item"].items() if k not in ("sources",)}
    return {**d, "item": item, "readme": readme, "git": git}


def get_publish_plan(path: str) -> dict:
    """What a GitHub upload of this project would do, without doing it: the
    files `git add -A` would commit (with `sensitive` secrets-looking files and
    `large` >50 MB files flagged), the commits that would be pushed, and the
    action — push | push_upstream | create_repo | nothing | blocked (with
    blocked_reason)."""
    p = git_publish.plan(_norm(path))
    return {**p, "files": p["files"][:80]}


def get_repo_changes(path: str, max_chars: int = 12000) -> dict:
    """The uncommitted changes of a tracked project, for writing a commit
    message: `git diff --stat` plus the diff text (truncated to max_chars,
    1000-30000), and the names of untracked files. Diff bodies of files that
    look like secrets are never included."""
    root = _norm(path)
    dev_project_detail.tracked_item(root)
    fs = os.path.normpath(root)
    max_chars = max(1000, min(30000, int(max_chars)))
    rc, out, _ = git_publish._git(fs, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    files = git_publish.parse_porcelain_v1(out) if rc == 0 else []
    untracked = [f["path"] for f in files if f["status"] == "??"]
    tracked = [f["path"] for f in files if f["status"] != "??"]
    safe = [f for f in tracked if not git_publish.is_sensitive(f)]
    has_head = git_publish._git(fs, "rev-parse", "--verify", "-q", "HEAD")[0] == 0
    base = ["diff", "HEAD"] if has_head else ["diff", "--cached"]
    _, stat, _ = git_publish._git(fs, *base, "--stat", "--", *safe) if safe else (0, "", "")
    diff = ""
    if safe:
        _, diff, _ = git_publish._git(fs, *base, "--no-color", "--", *safe, timeout=30)
    truncated = len(diff) > max_chars
    return {
        "path": root, "changed_files": len(files), "stat": stat.strip()[-4000:],
        "diff": diff[:max_chars], "diff_truncated": truncated,
        "untracked": untracked[:200], "untracked_count": len(untracked),
        "sensitive_skipped": [f for f in tracked + untracked if git_publish.is_sensitive(f)][:50],
    }


def publish_project(path: str, commit_message: str, repo_name: str | None = None) -> dict:
    """Upload a tracked project to GitHub in one go: `git add -A` + commit with
    `commit_message` (when there are changes), then push — setting the upstream
    on a first push, or creating a NEW PRIVATE GitHub repo named `repo_name`
    (default: folder name) via `gh` when there is no remote. Never force-pushes.
    REFUSES (blocked=true) when the commit would include secret-looking or
    >50 MB files: tell the user which files, and suggest .gitignore or the
    dashboard's upload dialog. Always call get_publish_plan first."""
    root = _norm(path)
    msg = (commit_message or "").strip()
    if not msg or len(msg) > 5000:
        return {"ok": False, "error": "bad_message", "detail": "commit_message must be 1-5000 characters"}
    try:
        p = git_publish.plan(root)
    except git_publish.PublishError as e:
        return {"ok": False, "error": e.code}
    if p["action"] == "blocked":
        return {"ok": False, "error": p["blocked_reason"] or "blocked"}
    if p["action"] == "nothing":
        return {"ok": False, "error": "nothing_to_push"}
    if p["sensitive"] or p["large"]:
        return {"ok": False, "blocked": True, "error": "unsafe_files",
                "sensitive": p["sensitive"], "large": p["large"],
                "detail": "Refusing to auto-commit secret-looking or >50 MB files. Add them to .gitignore, "
                          "or let the user review them in the dashboard's upload dialog."}
    try:
        r = git_publish.publish(root, commit=True, message=msg, repo_name=repo_name, private=True)
    except git_publish.PublishError as e:
        return {"ok": False, "error": e.code}
    return {**r, "action": p["action"], "path": root}


def save_project_meta(path: str, alias: str | None = None, description: str | None = None,
                      tags: list[str] | None = None, stage: str | None = None, notes: str | None = None) -> dict:
    """Update the user's notes for a tracked dev project — a partial update:
    only the fields you pass change. alias = display name (<=80 chars),
    description = one-paragraph summary (<=2000), tags = up to 12 short
    labels (REPLACES the list: include existing tags you want to keep), stage =
    idea | active | maintenance | paused | archived | "" (clear), notes =
    free-form notes / to-do (<=20000, REPLACES the notes)."""
    root = _norm(path)
    body = {k: v for k, v in {"alias": alias, "description": description, "tags": tags,
                              "stage": stage, "notes": notes}.items() if v is not None}
    if not body:
        return {"ok": False, "error": "nothing_to_update"}
    fields, errors = dev_project_detail.clean_meta(body)
    if errors:
        return {"ok": False, "error": "invalid", "detail": errors}
    dev_project_detail.tracked_item(root)
    return {"ok": True, "meta": dev_project_detail.save_meta(root, fields)}


def push_github_description(path: str, description: str | None = None) -> dict:
    """Write a description into the GitHub repo's About box (`gh repo edit
    --description`, max 350 chars). Omit `description` to use the project's
    saved description. Only for projects whose remote is on GitHub."""
    root = _norm(path)
    desc = description if description is not None else dev_project_detail.get_meta(root)["description"]
    if not desc or not desc.strip():
        return {"ok": False, "error": "empty_description"}
    return dev_project_detail.push_github_description(root, desc)
