"""TokenScope MCP server (stdio).

Exposes the same aggregate queries the web dashboard uses as MCP tools, so
Claude can answer questions like "how many tokens did I use this month?".

stdout belongs to the MCP protocol — never print to it. Diagnostics go to
stderr; the dashboard subprocess gets DEVNULL stdio for the same reason.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import urllib.error
import urllib.request

try:  # MCP SDK v2
    from mcp.server import MCPServer as FastMCP
except ImportError:  # MCP SDK v1
    from mcp.server.fastmcp import FastMCP

from . import insights, queries, subscription
from .config import config_path, ensure_pricing_file, load_config, save_config
from .db import get_conn, locked_conn
from .parser import normalize_cwd
from .pricing import load_pricing, save_pricing, validate_pricing
from .projects import Folder
from .sync import service

mcp = FastMCP("tokenscope")

_init_lock = threading.Lock()
_initialized = False


def _ensure_ready() -> None:
    """Lazy init on first tool call: open DB, seed pricing, run one sync.

    Never runs at server startup — the initial sync parses every historical
    transcript and can take tens of seconds for heavy users.
    """
    global _initialized
    with _init_lock:
        if _initialized:
            return
        get_conn()
        ensure_pricing_file()
        service.sync_once()
        _initialized = True


@mcp.tool()
def get_summary(project: str | None = None) -> dict:
    """Token usage summary cards: today and current-month totals.

    Returns tokens by type (input/output/cache_write/cache_read), virtual cost
    total and by model family, and event counts. Costs are virtual USD costs
    computed from the editable pricing file (equivalent API price —
    subscription plans have no real per-token bill). The first tool call after
    server start may be slow (initial transcript sync).

    Pass `project` (a project path or any session directory under it) to narrow
    the cards to one project. The `savings` block stays account-wide either way
    — one fee covers the whole account — so do not present it as this project's
    saving; use get_project_share for the per-project framing.
    """
    _ensure_ready()
    return {**queries.summary_cards(project), "sync": service.status()}


@mcp.tool()
def get_trend(granularity: str = "day", days: int = 30, months: int = 12,
              project: str | None = None) -> dict:
    """Token/cost time series. granularity: "day" (last `days`, 1-366) or "month" (last `months`, 1-36).

    Each point has bucket, input/output/cache_write/cache_read tokens, and
    virtual cost USD. Pass `project` to restrict the series to one project.
    """
    _ensure_ready()
    return queries.trend(granularity, days, months, project)


@mcp.tool()
def get_models_distribution(range: str = "30d", project: str | None = None) -> dict:
    """Token & cost breakdown by model, two ways.

    `items` rolls up to family (fable/opus/sonnet/haiku/other); `models` is the
    exact model id (claude-opus-5, claude-opus-4-8, ...) with call count,
    token split, unit rates applied, cost, and average cost per call.

    Valid ranges: "today", "7d", "30d", "month" (calendar month to date), "all".
    Includes token_share vs cost_share — they often differ sharply because
    output tokens cost ~5x input and cache reads are cheap.

    Pass `project` to restrict the breakdown to one project.
    """
    _ensure_ready()
    return queries.models_distribution(range, project)


@mcp.tool()
def get_projects_top(range: str = "30d", limit: int = 10) -> dict:
    """Top projects by virtual cost. Valid ranges: "today", "7d", "30d",
    "month" (calendar month to date), "all". limit: 1-50."""
    _ensure_ready()
    return queries.projects_top(range, limit)


@mcp.tool()
def get_projects(range: str = "30d") -> dict:
    """All projects with tokens, cost, events, sessions, last_active, and a
    30-day daily sparkline. Valid ranges: "today", "7d", "30d", "month", "all"."""
    _ensure_ready()
    return queries.projects_list(range)


@mcp.tool()
def get_project_detail(path: str) -> dict:
    """Detail for one project by its normalized path (as returned in `path`
    fields of get_projects / get_projects_top): month-over-month token delta,
    average cost per event, token breakdown."""
    _ensure_ready()
    detail = queries.project_detail(path)
    if detail is None:
        return {"error": f"unknown project path: {path}",
                "hint": "use a `path` value from get_projects"}
    return detail


@mcp.tool()
def query_logs(from_date: str | None = None, to_date: str | None = None,
               model_family: str | None = None, project: str | None = None,
               search: str | None = None, page: int = 1, page_size: int = 50) -> dict:
    """Paginated per-request usage log, newest first.

    from_date/to_date: YYYY-MM-DD (local time, inclusive). model_family:
    fable|opus|sonnet|haiku|other. project: normalized project path. search:
    substring match on project name / session id / message id. page_size: 1-500.
    """
    _ensure_ready()
    page = max(1, page)
    page_size = min(500, max(1, page_size))
    return queries.logs(from_date, to_date, model_family, project, search, page, page_size)


@mcp.tool()
def sync_now() -> dict:
    """Rescan Claude Code transcript files (~/.claude/projects/**/*.jsonl) now
    and return sync status. Incremental — only changed files are re-parsed."""
    _ensure_ready()
    return service.sync_once()


@mcp.tool()
def get_sync_status() -> dict:
    """Sync status: last_sync_at, files seen/parsed, total events, parse errors,
    missing scan roots."""
    _ensure_ready()
    return service.status()


@mcp.tool()
def platform_push() -> dict:
    """AIPM platform mode: parse local Claude Code transcripts and push usage
    events to the team platform (requires server_url + api_token in config.json).
    Idempotent server-side; safe to call repeatedly."""
    _ensure_ready()
    from .platform_sync import push_once
    return push_once()


@mcp.tool()
def platform_status() -> dict:
    """Whether AIPM platform mode is configured, plus current push cursor."""
    from .config import load_config as _lc
    from .db import locked_conn as _lk
    from .platform_sync import platform_enabled
    cfg = _lc()
    with _lk() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key='platform_last_event_id'").fetchone()
    return {"enabled": platform_enabled(cfg), "server_url": cfg.get("server_url"),
            "cursor": int(row["value"]) if row else 0}


@mcp.tool()
def set_session_requirement(requirement_key: str, session_id: str) -> dict:
    """Bind a Claude Code session to a platform requirement (e.g. ACME-WEB-042)
    so its usage is attributed to that requirement. Platform mode only."""
    from .platform_sync import bind_session
    return bind_session(requirement_key, session_id)


@mcp.tool()
def get_pricing() -> dict:
    """Current pricing document: USD per million tokens for each model family
    (fable/opus/sonnet/haiku/other) x rate (input/output/cache_write/cache_read).
    Costs everywhere are virtual USD computed from this editable file."""
    _ensure_ready()
    return load_pricing()


@mcp.tool()
def update_pricing(pricing: dict) -> dict:
    """Replace the pricing document — this is a FULL REPLACE, not a merge.

    Must contain `families` with ALL five families (fable/opus/sonnet/haiku/
    other), each with all four numeric rates (input/output/cache_write/
    cache_read, USD per million tokens, >= 0).

    An optional `models` map overrides individual model ids (partial overrides
    are allowed; unset rates fall back to the family). ALWAYS call get_pricing
    first and carry over the existing `models` section unchanged unless the
    user asked to change it — omitting it silently deletes their per-model
    rates.

    Edits apply retroactively to all history at query time.
    Returns {ok: true} or {ok: false, errors: [...]} without saving."""
    _ensure_ready()
    errors = validate_pricing(pricing)
    if errors:
        return {"ok": False, "errors": errors}
    save_pricing(pricing)
    return {"ok": True, "pricing": load_pricing()}


@mcp.tool()
def get_subscription_savings() -> dict:
    """How much the subscription saved versus paying API list price.

    The plan is auto-detected from ~/.claude.json (`oauthAccount`: org type +
    rate limit tier), so no setup is needed; `subscription.source` says whether
    it was detected or pinned manually. Returns the detected plan and fee,
    this month's savings (with an end-of-month projection), and a month-by-month
    cumulative timeline.

    Months with no transcripts left on disk are charged their fee against $0 of
    recorded usage (Claude Code prunes logs after ~30 days), so `total_saved` is
    a floor — check `months_missing_data`. Meaningless on pay-as-you-go API
    billing: `comparable` is false there.
    """
    _ensure_ready()
    return queries.savings_report()


@mcp.tool()
def set_subscription(mode: str = "auto", plan: str | None = None,
                     monthly_usd: float | None = None) -> dict:
    """Pin the subscription plan, or hand control back to auto-detection.

    mode="auto" clears the pin and re-detects from ~/.claude.json.
    mode="manual" requires `plan`: one of pro, max5, max20, team, api
    ("api" = pay-as-you-go, disables the savings comparison). `monthly_usd`
    optionally overrides the list price — use it for annual billing, multiple
    seats, or a plan this tool does not know about.
    """
    _ensure_ready()
    try:
        subscription.set_subscription(mode, plan, monthly_usd)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, **queries.savings_report()}


@mcp.tool()
def get_project_share(project: str) -> dict:
    """What one project cost THIS MONTH, against the account and the plan fee.

    `project` is a project path or any session directory under it — both fold
    to the same project. Pass the current working directory to answer "how much
    has this project cost me".

    Returns the project's month-to-date tokens/cost/calls, its share of the
    whole account's month, a per-model breakdown, and `pct_of_fee` — how much of
    the monthly subscription fee this project alone consumed at API-equivalent
    price (over 100% means this one project already paid the plan back).

    Do NOT describe this as the project "saving" money: one fee covers the whole
    account, so per-project savings are meaningless. On pay-as-you-go API
    billing `comparable` is false and `pct_of_fee` is null — there the cost IS
    the real bill for that project.

    Differs from get_project_detail, which is all-time totals with no account
    or fee comparison.
    """
    _ensure_ready()
    return queries.project_share(project)


def _spawn_web(port: int, project: str | None = None) -> None:
    """Start the dashboard so it outlives this MCP server.

    MCP hosts kill the server's whole process tree on shutdown — on Windows via
    a kill-on-close Job Object, and with nested jobs CREATE_BREAKAWAY_FROM_JOB
    silently leaves the child inside any job that forbids breakaway, so Popen
    cannot escape. Instead ask WMI to create the process: it is spawned by the
    WMI provider service, outside our job tree. pythonw keeps it windowless
    (web.main() guards against its None std streams). If pythonw is missing,
    fall back to a plain detached child (dashboard then lives only as long as
    this server — better than a stray console window).

    `project` is passed as an argument rather than an env var on purpose: the
    WMI-spawned process does not inherit this process's environment.
    """
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL}
    cmd = [sys.executable, "-m", "tokenscope.web", "--port", str(port)]
    if project:
        cmd += ["--project", project]
    if sys.platform != "win32":
        subprocess.Popen(cmd, start_new_session=True, **kwargs)
        return

    from pathlib import Path
    pyw = Path(sys.executable).with_name("pythonw.exe")
    if pyw.exists():
        cmdline = f'"{pyw}" -m tokenscope.web --port {port}'
        if project:
            cmdline += f' --project "{project}"'
        # The whole line sits inside a PowerShell single-quoted string, where a
        # literal apostrophe must be doubled — project paths can contain one.
        ps = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
             f"-Arguments @{{CommandLine='{cmdline.replace(chr(39), chr(39) * 2)}'}} | Out-Null"],
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=30, **kwargs)
        if ps.returncode == 0:
            return
    subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                     | subprocess.DETACHED_PROCESS, **kwargs)


@mcp.tool()
def get_project_grouping() -> dict:
    """Show how session directories are folded into projects, and why.

    Claude Code records the exact directory each session started in, so one
    project can arrive as many cwds (`<proj>`, `<proj>/backend`, ...). Each cwd
    is folded to the first directory under a matching `workspace_roots` entry,
    then rewritten by `project_aliases` (for folders that were renamed, whose
    old and new paths share no prefix).

    Returns the current workspace_roots and project_aliases, plus every project
    with the raw cwds folded into it — use this to spot projects that should be
    merged with set_project_alias.
    """
    _ensure_ready()
    cfg = load_config()
    folder = Folder(cfg)
    with locked_conn() as conn:
        rows = conn.execute(
            "SELECT project_path p, "
            "SUM(input_tokens+output_tokens+cache_write_tokens+cache_read_tokens) t "
            "FROM events GROUP BY project_path").fetchall()
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(folder.fold(r["p"]), {"tokens": 0, "cwds": []})
        g["tokens"] += r["t"] or 0
        g["cwds"].append(r["p"])
    return {
        "workspace_roots": cfg.get("workspace_roots", []),
        "project_aliases": cfg.get("project_aliases", {}),
        "config_file": str(config_path()),
        "projects": [
            {"path": k, "tokens": v["tokens"], "cwds": sorted(v["cwds"])}
            for k, v in sorted(groups.items(), key=lambda x: -x[1]["tokens"])
        ],
    }


@mcp.tool()
def set_project_alias(source: str, target: str) -> dict:
    """Merge one project into another, for folders that were renamed or moved.

    `source` is the path to redirect (a project path or a raw cwd from
    get_project_grouping), `target` is the project path it should count as.
    Pass an empty `target` to remove an existing alias. Applies retroactively
    to all history — nothing is re-parsed.
    """
    _ensure_ready()
    cfg = load_config()
    aliases = dict(cfg.get("project_aliases") or {})
    src = normalize_cwd(source)
    if not target.strip():
        removed = aliases.pop(src, None)
        if removed is None:
            return {"ok": False, "error": f"no alias for {src}",
                    "project_aliases": aliases}
    else:
        dst = normalize_cwd(target)
        if dst == src:
            return {"ok": False, "error": "source and target are the same path"}
        aliases[src] = dst
    cfg["project_aliases"] = aliases
    save_config(cfg)
    return {"ok": True, "project_aliases": aliases}


@mcp.tool()
def set_workspace_roots(roots: list[str]) -> dict:
    """Replace the list of workspace roots — directories whose immediate
    children are projects (e.g. ~/Desktop, ~/code). A cwd under one of these is
    folded to its first directory, so `<proj>/backend` counts as `<proj>`.
    A cwd matching no root keeps its own full path. Applies retroactively."""
    _ensure_ready()
    cleaned = [normalize_cwd(r) for r in roots if isinstance(r, str) and r.strip()]
    if not cleaned:
        return {"ok": False, "error": "roots must contain at least one path"}
    cfg = load_config()
    cfg["workspace_roots"] = cleaned
    save_config(cfg)
    return {"ok": True, "workspace_roots": cleaned}


@mcp.tool()
def get_sessions(range: str = "7d", project: str | None = None, sort: str = "cost",
                 limit: int = 20, search: str | None = None) -> dict:
    """Sessions in a range, each with cost, message count, models, tool calls,
    subagent share and peak context size (input + cache tokens of the largest
    turn). sort: "cost" (most expensive first) or "start" (newest first).
    Valid ranges: "today", "7d", "30d", "month", "all". limit: 1-200.

    Use this to find the runaway session behind a spike, then
    get_session_detail for the turn-by-turn picture.
    """
    _ensure_ready()
    return insights.sessions(range, project=project, q=search, sort=sort,
                             page=1, page_size=min(200, max(1, limit)))


@mcp.tool()
def get_session_detail(session_id: str) -> dict:
    """One session turn by turn: context size per message (how much of the
    conversation was re-sent), cost per turn, cumulative cost, the tools each
    turn called, and which turns ran inside a subagent. `peak_context` says
    where the context was largest — usually where a /clear would have paid off.
    """
    _ensure_ready()
    detail = insights.session_detail(session_id)
    if detail is None:
        return {"error": f"unknown session: {session_id}",
                "hint": "use a session_id from get_sessions or query_logs"}
    # Keep the MCP payload manageable: the timeline can run to thousands of turns.
    msgs = detail["messages"]
    if len(msgs) > 300:
        step = len(msgs) // 300 + 1
        detail["messages"] = msgs[::step]
        detail["sampled_every"] = step
    return detail


@mcp.tool()
def get_tools_breakdown(range: str = "30d", project: str | None = None) -> dict:
    """Which tools the model spent its turns on (Read, Bash, Edit, Agent, ...).

    A tool's cost is the cost of the assistant messages that called it, split
    evenly when one message called several tools — the cost of deciding to use
    the tool and writing its arguments, not the downstream cost of its result.
    Also returns `text_only` (turns with no tool call) and `subagents` (cost
    share of subagent transcripts, by agent type).
    """
    _ensure_ready()
    return insights.tools_breakdown(range, project)


@mcp.tool()
def get_heatmap(range: str = "30d", project: str | None = None) -> dict:
    """7x24 usage matrix in local time (dow 0 = Sunday): tokens, cost and
    calls per cell, plus per-hour and per-weekday totals and the peak slot."""
    _ensure_ready()
    return insights.heatmap(range, project)


@mcp.tool()
def get_alerts(project: str | None = None) -> dict:
    """Things worth a look right now, most urgent first. Kinds: daily_spike
    (today vs 30-day median), week_pace (7-day vs previous 7), runaway_session,
    context_bloat (a session whose context exceeded 150K tokens), cache_efficiency,
    subagent_share, pricing_stale (rate table unverified for >90 days), retention
    (months with pruned logs / cleanupPeriodDays too low), git_unpushed (local
    commits not pushed to GitHub), git_dirty (uncommitted changes idle >24h),
    git_no_remote (repo has no GitHub remote / upstream). Each item carries
    `level` (info|warn|danger) and `params` with the numbers."""
    _ensure_ready()
    return insights.alerts(project)


@mcp.tool()
def get_dev_projects(refresh: bool = False) -> dict:
    """Local projects under development and their git state: repos seen in
    recent Claude Code sessions or under workspace_roots, with branch,
    ahead/behind upstream, uncommitted change counts, GitHub remote, and a
    tiered `level` (ok|info|warn|danger) plus `reasons` such as unpushed,
    unpushed_stale, dirty_stale, no_remote. Use it to remind the user what
    still needs `git push`. refresh=True bypasses the 60 s cache."""
    _ensure_ready()
    from . import dev_projects
    return dev_projects.snapshot(force=refresh)


@mcp.tool()
def get_weekly_report(weeks_ago: int = 0, project: str | None = None,
                      lang: str = "zh") -> dict:
    """Monday-to-Sunday digest: totals with week-over-week deltas, cost per
    day, top projects / models / sessions, tool calls, cache efficiency and
    subscription savings. Returns the structured report plus `markdown`
    (lang "zh" or "en") ready to paste into a channel or a note.
    weeks_ago: 0 = current week, 1 = last week, ..."""
    _ensure_ready()
    report = insights.weekly_report(max(0, weeks_ago), project)
    report["markdown"] = insights.render_weekly_markdown(report, "zh" if lang == "zh" else "en")
    return report


@mcp.tool()
def get_retention_status() -> dict:
    """Claude Code's transcript retention (cleanupPeriodDays) versus the last
    TokenScope sync, plus the pricing table's age. Explains why months can be
    missing and how to prevent it (scheduled sync, longer retention)."""
    _ensure_ready()
    return {**insights.retention_info(), "pricing": insights.pricing_status()}


def _health_ok(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as resp:
            return b'"ok"' in resp.read() or resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


@mcp.tool()
def launch_dashboard(port: int | None = None, project: str | None = None) -> dict:
    """Start the TokenScope web dashboard in the background and return its URL.

    The UI is available in Chinese, English and French (switcher in the top
    right; it picks the browser language on first open). Default port comes
    from config (8787).

    Pass `project` — a project path or any session directory under it — to open
    the dashboard scoped to that one project: every panel then shows only that
    project's usage, and the subscription savings panel is replaced by "what
    share of the monthly fee this project used up". Use the current working
    directory when the user asks about "this project". Omit it for the
    account-wide view.

    Scoping only applies when the dashboard actually starts: if it is already
    running on that port, `already_running` is true and the existing scope is
    untouched — say so rather than claiming the scope was applied.
    """
    _ensure_ready()
    if port is None:
        port = int(load_config().get("port", 8787))
    url = f"http://127.0.0.1:{port}"
    scope = queries.scope_info(project) if project else None
    if _health_ok(port):
        return {"url": url, "already_running": True, "scope": scope,
                "note": "dashboard was already running; its existing scope was kept"}

    _spawn_web(port, project)

    import time
    for _ in range(20):
        time.sleep(0.5)
        if _health_ok(port):
            return {"url": url, "already_running": False, "scope": scope}
    return {"url": url, "already_running": False, "scope": scope,
            "warning": "server did not report healthy within 10s; it may still be starting"}


def main() -> None:
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
