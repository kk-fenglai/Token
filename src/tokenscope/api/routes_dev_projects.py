"""F26 — dev-project tracker endpoints. Git probes run off the event loop."""
from __future__ import annotations

import asyncio
import os
import sys

from fastapi import APIRouter, HTTPException, Request

from .. import dev_project_detail, dev_projects, git_publish, notify
from ..config import load_config, save_config
from .guard import require_local

router = APIRouter()

_LIST_KEYS = ("extra", "ignored", "pinned")
_INT_KEYS = ("active_days", "unpushed_danger_hours", "dirty_warn_hours")


def _with_meta(snap: dict) -> dict:
    """Attach the F28 user notes to each row. Done per request rather than in
    the cached snapshot, so an edit shows up without waiting for the TTL."""
    metas = dev_project_detail.all_meta()
    empty = dev_project_detail.EMPTY_META
    return {**snap, "items": [{**x, "meta": metas.get(x["path"], empty)} for x in snap["items"]]}


def _snapshot_with_meta(force: bool = False) -> dict:
    return _with_meta(dev_projects.snapshot(force))


@router.get("/dev-projects")
async def list_dev_projects():
    return await asyncio.to_thread(_snapshot_with_meta)


@router.post("/dev-projects/refresh")
async def refresh_dev_projects():
    return await asyncio.to_thread(_snapshot_with_meta, True)


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
    return await asyncio.to_thread(_snapshot_with_meta, True)


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


# ----------------------------------------------------------- F27 publish ----

# Shared with the agent routes; kept under the old name for existing callers.
_require_local = require_local


def _publish_error(e: git_publish.PublishError) -> HTTPException:
    status = 404 if e.code == "not_tracked" else 409 if e.code == "busy" else 422
    return HTTPException(status_code=status, detail={"code": e.code, "detail": e.detail})


@router.get("/dev-projects/publish-plan")
async def publish_plan(path: str, request: Request):
    _require_local(request)
    try:
        return await asyncio.to_thread(git_publish.plan, path)
    except git_publish.PublishError as e:
        raise _publish_error(e) from None


@router.post("/dev-projects/publish")
async def publish(body: dict, request: Request):
    """Body: {path, commit?: bool, message?: str, repo_name?: str, private?: bool}."""
    _require_local(request)
    path = body.get("path")
    if not isinstance(path, str):
        raise HTTPException(status_code=422, detail={"code": "bad_request", "detail": "path required"})
    commit = body.get("commit", True)
    message = body.get("message", "")
    repo_name = body.get("repo_name")
    private = body.get("private", True)
    if not (isinstance(commit, bool) and isinstance(private, bool) and isinstance(message, str)
            and (repo_name is None or isinstance(repo_name, str))):
        raise HTTPException(status_code=422, detail={"code": "bad_request", "detail": "bad field types"})
    try:
        return await asyncio.to_thread(git_publish.publish, path, commit=commit, message=message,
                                       repo_name=repo_name, private=private)
    except git_publish.PublishError as e:
        raise _publish_error(e) from None


# ------------------------------------------------------------ F28 detail ----

def _path_of(body) -> str:
    path = body.get("path") if isinstance(body, dict) else None
    if not isinstance(path, str):
        raise HTTPException(status_code=422, detail={"code": "bad_request", "detail": "path required"})
    return path


@router.get("/dev-projects/detail")
async def project_detail(path: str, request: Request):
    _require_local(request)  # returns README / notes; keep it off rebinding hosts too
    try:
        return await asyncio.to_thread(dev_project_detail.detail, path)
    except dev_project_detail.NotTracked:
        raise HTTPException(status_code=404, detail={"code": "not_tracked", "detail": path}) from None


@router.put("/dev-projects/meta")
async def put_meta(body: dict, request: Request):
    """Partial update of alias / description / tags / stage / notes."""
    _require_local(request)
    path = _path_of(body)
    fields, errors = dev_project_detail.clean_meta(body)
    if errors:
        raise HTTPException(status_code=422, detail={"code": "bad_request", "detail": errors})
    try:
        await asyncio.to_thread(dev_project_detail.tracked_item, path)
    except dev_project_detail.NotTracked:
        raise HTTPException(status_code=404, detail={"code": "not_tracked", "detail": path}) from None
    return await asyncio.to_thread(dev_project_detail.save_meta, path, fields)


@router.post("/dev-projects/open-editor")
async def open_editor(body: dict, request: Request):
    _require_local(request)
    path = _path_of(body)
    try:
        item = await asyncio.to_thread(dev_project_detail.tracked_item, path)
    except dev_project_detail.NotTracked:
        raise HTTPException(status_code=404, detail={"code": "not_tracked", "detail": path}) from None
    if not await asyncio.to_thread(dev_project_detail.open_in_editor, item["path"]):
        raise HTTPException(status_code=501, detail={"code": "editor_missing", "detail": "VS Code not found"})
    return {"ok": True}


@router.post("/dev-projects/github-description")
async def github_description(body: dict, request: Request):
    """Push the saved description (or `description` from the body) to the
    GitHub repo's About box via `gh repo edit`."""
    _require_local(request)
    path = _path_of(body)
    desc = body.get("description")
    if desc is not None and not isinstance(desc, str):
        raise HTTPException(status_code=422, detail={"code": "bad_request", "detail": "description must be a string"})
    try:
        if desc is None:
            desc = (await asyncio.to_thread(dev_project_detail.get_meta, path))["description"]
        return await asyncio.to_thread(dev_project_detail.push_github_description, path, desc)
    except dev_project_detail.NotTracked:
        raise HTTPException(status_code=404, detail={"code": "not_tracked", "detail": path}) from None
