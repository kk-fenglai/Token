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

from . import queries
from .config import ensure_pricing_file, load_config
from .db import get_conn
from .pricing import load_pricing, save_pricing, validate_pricing
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
def get_summary() -> dict:
    """Token usage summary cards: today and current-month totals.

    Returns tokens by type (input/output/cache_write/cache_read), virtual cost
    total and by model family, and event counts. Costs are virtual USD costs
    computed from the editable pricing file (equivalent API price —
    subscription plans have no real per-token bill). The first tool call after
    server start may be slow (initial transcript sync).
    """
    _ensure_ready()
    return {**queries.summary_cards(), "sync": service.status()}


@mcp.tool()
def get_trend(granularity: str = "day", days: int = 30, months: int = 12) -> dict:
    """Token/cost time series. granularity: "day" (last `days`, 1-366) or "month" (last `months`, 1-36).

    Each point has bucket, input/output/cache_write/cache_read tokens, and virtual cost USD.
    """
    _ensure_ready()
    return queries.trend(granularity, days, months)


@mcp.tool()
def get_models_distribution(range: str = "30d") -> dict:
    """Token & cost breakdown by model family (fable/opus/sonnet/haiku/other).

    Valid ranges: "today", "7d", "30d", "month" (calendar month to date), "all".
    Includes token_share vs cost_share — they often differ sharply because
    output tokens cost ~5x input and cache reads are cheap.
    """
    _ensure_ready()
    return queries.models_distribution(range)


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
def get_pricing() -> dict:
    """Current pricing document: USD per million tokens for each model family
    (fable/opus/sonnet/haiku/other) x rate (input/output/cache_write/cache_read).
    Costs everywhere are virtual USD computed from this editable file."""
    _ensure_ready()
    return load_pricing()


@mcp.tool()
def update_pricing(pricing: dict) -> dict:
    """Replace the pricing document. Must contain `families` with ALL five
    families (fable/opus/sonnet/haiku/other), each with all four numeric rates
    (input/output/cache_write/cache_read, USD per million tokens, >= 0).
    Edits apply retroactively to all history at query time.
    Returns {ok: true} or {ok: false, errors: [...]} without saving."""
    _ensure_ready()
    errors = validate_pricing(pricing)
    if errors:
        return {"ok": False, "errors": errors}
    save_pricing(pricing)
    return {"ok": True, "pricing": load_pricing()}


def _spawn_web(port: int) -> None:
    """Start the dashboard so it outlives this MCP server.

    MCP hosts kill the server's whole process tree on shutdown — on Windows via
    a kill-on-close Job Object, and with nested jobs CREATE_BREAKAWAY_FROM_JOB
    silently leaves the child inside any job that forbids breakaway, so Popen
    cannot escape. Instead ask WMI to create the process: it is spawned by the
    WMI provider service, outside our job tree. pythonw keeps it windowless
    (web.main() guards against its None std streams). If pythonw is missing,
    fall back to a plain detached child (dashboard then lives only as long as
    this server — better than a stray console window).
    """
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL}
    cmd = [sys.executable, "-m", "tokenscope.web", "--port", str(port)]
    if sys.platform != "win32":
        subprocess.Popen(cmd, start_new_session=True, **kwargs)
        return

    from pathlib import Path
    pyw = Path(sys.executable).with_name("pythonw.exe")
    if pyw.exists():
        cmdline = f'"{pyw}" -m tokenscope.web --port {port}'
        ps = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
             f"-Arguments @{{CommandLine='{cmdline}'}} | Out-Null"],
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=30, **kwargs)
        if ps.returncode == 0:
            return
    subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                     | subprocess.DETACHED_PROCESS, **kwargs)


def _health_ok(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as resp:
            return b'"ok"' in resp.read() or resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


@mcp.tool()
def launch_dashboard(port: int | None = None) -> dict:
    """Start the TokenScope web dashboard (charts UI, Chinese labels) in the
    background and return its URL. If it is already running on the port, just
    returns the URL. Default port comes from config (8787)."""
    _ensure_ready()
    if port is None:
        port = int(load_config().get("port", 8787))
    url = f"http://127.0.0.1:{port}"
    if _health_ok(port):
        return {"url": url, "already_running": True}

    _spawn_web(port)

    import time
    for _ in range(20):
        time.sleep(0.5)
        if _health_ok(port):
            return {"url": url, "already_running": False}
    return {"url": url, "already_running": False,
            "warning": "server did not report healthy within 10s; it may still be starting"}


def main() -> None:
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
