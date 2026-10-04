"""TokenScope web dashboard — FastAPI app on localhost:8787.

Lifespan: init DB, ensure pricing file, run a full sync at startup, then an
incremental sync every `sync_interval_seconds`. The built frontend (bundled
as package data under `static/`) is served as an SPA from the same process.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import dev_projects
from .api import (routes_agent, routes_dev_projects, routes_insights, routes_logs, routes_pricing,
                  routes_projects, routes_scope, routes_stats, routes_subscription, routes_sync)
from .config import db_path, ensure_pricing_file, load_config
from .db import get_conn
from .sync import service

DIST = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_conn()
    ensure_pricing_file()
    # The assistant calls MCP tool functions in-process; this process syncs on
    # its own schedule, so skip their lazy first-call sync.
    from . import mcp_server
    mcp_server._initialized = True
    interval = load_config().get("sync_interval_seconds", 300)

    async def scheduler():
        while True:
            await asyncio.to_thread(service.sync_once)
            # F26: git reminders ride on the same cadence; a git or PowerShell
            # hiccup must never stop the sync loop.
            try:
                await asyncio.to_thread(dev_projects.check_and_notify)
            except Exception:
                pass
            # F29: the patrol runs as its own task so a slow LLM call never
            # delays the next sync.
            try:
                from .agent import patrol
                patrol.maybe_start()
            except Exception:
                pass
            await asyncio.sleep(interval)

    task = asyncio.create_task(scheduler())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="TokenScope", lifespan=lifespan)

for r in (routes_stats, routes_logs, routes_projects, routes_sync, routes_pricing,
          routes_subscription, routes_scope, routes_insights, routes_dev_projects, routes_agent):
    app.include_router(r.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True, "db": str(db_path()), "version": "1.3"}


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        candidate = DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
else:
    @app.get("/")
    def no_frontend():
        return JSONResponse({"message": "frontend not built — run `npm run build` in frontend/, or use vite dev"})


def main() -> None:
    import argparse
    import os
    import sys

    import uvicorn

    # Under pythonw.exe (no console) std streams are None; uvicorn's loggers
    # need real file objects.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    cfg = load_config()
    ap = argparse.ArgumentParser(prog="tokenscope-web", description="TokenScope web dashboard")
    ap.add_argument("--port", type=int, default=cfg.get("port", 8787))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--project", nargs="?", const=".", default=None,
                    help="scope the dashboard to one project directory "
                         "(bare --project means the current directory)")
    args = ap.parse_args()
    if args.project:
        # Passed via env so the reload/worker process inherits it too.
        os.environ["TOKENSCOPE_PROJECT"] = os.path.abspath(args.project)
    uvicorn.run("tokenscope.web:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
