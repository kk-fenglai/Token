"""F26 — dev-project tracker endpoints. Git probes run off the event loop."""
from __future__ import annotations

import asyncio
import os
import sys

from fastapi import APIRouter, HTTPException

from .. import dev_projects, notify
from ..config import load_config, save_config

router = APIRouter()

_LIST_KEYS = ("extra", "ignored", "pinned")
_INT_KEYS = ("active_days", "unpushed_danger_hours", "dirty_warn_hours")


@router.get("/dev-projects")
async def list_dev_projects():
    return await asyncio.to_thread(dev_projects.snapshot)


@router.post("/dev-projects/refresh")
async def refresh_dev_projects():
    return await asyncio.to_thread(dev_projects.snapshot, True)


@router.get("/dev-projects/config")
def get_dev_config():
    return dev_projects.dev_cfg()


def _validate(body: dict) -> list[str]:
    errors = []
    for k in _LIST_KEYS:
        if k in body and not (isinstance(body[k], list) and all(isinstance(x, str) for x in body[k])):
            errors.append(f"{k} must be a list of strings")
    for k in _INT_KEYS:
        if k in body and not (isinstance(body[k], int) and not isinstance(body[k], bool) and body[k] >= 1):
            errors.append(f"{k} must be an integer >= 1")
    if "desktop_notify" in body and not isinstance(body["desktop_notify"], bool):
        errors.append("desktop_notify must be a boolean")
    unknown = set(body) - set(_LIST_KEYS) - set(_INT_KEYS) - {"desktop_notify"}
    if unknown:
        errors.append(f"unknown keys: {', '.join(sorted(unknown))}")
    return errors


@router.put("/dev-projects/config")
async def put_dev_config(body: dict):
    """Partial update: only the keys present are changed. A path may be in
    at most one of extra / ignored / pinned's conflicting roles (ignoring a
    path also unpins it)."""
    errors = _validate(body)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    cfg = load_config()
    current = dev_projects.dev_cfg(cfg)
    merged = {**current, **body}
    merged = dev_projects.dev_cfg({**cfg, "dev_projects": merged})
    ignored = set(merged["ignored"])
    merged["pinned"] = [p for p in merged["pinned"] if p not in ignored]
    cfg["dev_projects"] = merged
    save_config(cfg)
    dev_projects.invalidate()
    return await asyncio.to_thread(dev_projects.snapshot, True)


@router.post("/dev-projects/notify-test")
async def notify_test():
    cfg = load_config()
    url = f"http://127.0.0.1:{cfg.get('port', 8787)}/#/dev-projects"
    sent = await asyncio.to_thread(notify.toast, "TokenScope", "测试通知 · test notification", url)
    return {"sent": sent, "platform": sys.platform}


@router.post("/dev-projects/notify-now")
async def notify_now():
    """Run the scheduler's reminder pass immediately (respects the daily dedupe)."""
    return await asyncio.to_thread(dev_projects.check_and_notify)


@router.post("/dev-projects/open")
async def open_folder(body: dict):
    """Open a tracked project in the file manager. Only paths in the current
    snapshot are accepted, so the endpoint cannot be pointed at arbitrary dirs."""
    path = body.get("path") if isinstance(body, dict) else None
    snap = await asyncio.to_thread(dev_projects.snapshot)
    match = next((x for x in snap["items"] if x["path"] == path), None)
    if not match:
        raise HTTPException(status_code=404, detail="project not tracked")
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="open is Windows-only")
    os.startfile(os.path.normpath(match["path"]))  # noqa: S606
    return {"ok": True}
