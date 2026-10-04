"""F29 — AI assistant endpoints. Every route is loopback-only: conversations
contain READMEs and diffs, and the assistant can push code."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..agent import loop, patrol, secrets, store
from ..agent.llm import make_client, map_error
from ..agent.settings import agent_cfg, clean_settings, merge_settings
from ..config import load_config, save_config
from .guard import require_local

router = APIRouter(prefix="/agent")

PING_SECONDS = 15.0


def _settings_payload() -> dict:
    cfg = agent_cfg()
    return {**cfg, "key": secrets.key_status(), "patrol_status": dict(patrol.status)}


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n".encode("utf-8")


# ------------------------------------------------------------------- chat ----

@router.post("/chat")
async def chat(body: dict, request: Request):
    """Body: {message, conversation_id?, page_context?}. Streams SSE events
    (run_start, step, reasoning_delta, text_delta, tool_call,
    confirm_required, tool_result, usage, notice, error, done)."""
    require_local(request)
    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(message, str) or not message.strip() or len(message) > 20_000:
        raise HTTPException(status_code=422, detail={"code": "bad_request", "detail": "message must be 1-20000 chars"})
    page_ctx = body.get("page_context")
    if page_ctx is not None and not isinstance(page_ctx, dict):
        raise HTTPException(status_code=422, detail={"code": "bad_request", "detail": "page_context must be an object"})
    if page_ctx is not None and len(json.dumps(page_ctx)) > 4000:
        page_ctx = {"route": str(page_ctx.get("route", ""))[:200]}
    cid = body.get("conversation_id")
    if cid is not None:
        if not isinstance(cid, str) or store.get_conversation(cid) is None:
            raise HTTPException(status_code=404, detail={"code": "not_found", "detail": "conversation"})
        if loop.is_busy(cid):
            raise HTTPException(status_code=409, detail={"code": "busy", "detail": "conversation is running"})
    if not secrets.key_status()["configured"]:
        raise HTTPException(status_code=412, detail={"code": "no_key", "detail": "DeepSeek API key not configured"})
    if cid is None:
        cid = store.create_conversation("chat", "", page_ctx, agent_cfg()["model"])

    async def events():
        queue: asyncio.Queue = asyncio.Queue()

        async def pump():
            try:
                async for ev in loop.run_turn(cid, message.strip(), page_ctx):
                    await queue.put(ev)
            finally:
                await queue.put(None)

        task = asyncio.create_task(pump())
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), PING_SECONDS)
                except asyncio.TimeoutError:
                    yield b": ping\n\n"
                    continue
                if ev is None:
                    break
                yield _sse(ev["event"], ev["data"])
        finally:
            if not task.done():
                # Client went away: let the loop stop at its next checkpoint
                # and close its dangling tool calls, instead of killing it
                # mid-write.
                for run in list(loop.RUNS.values()):
                    if run.conv_id == cid:
                        loop.cancel_run(run.id)
                try:
                    await asyncio.wait_for(asyncio.shield(task), 30)
                except (asyncio.TimeoutError, Exception):
                    task.cancel()

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/runs/{run_id}/cancel")
async def cancel(run_id: str, request: Request):
    require_local(request)
    return {"ok": loop.cancel_run(run_id)}


@router.post("/runs/{run_id}/confirm")
async def confirm(run_id: str, body: dict, request: Request):
    require_local(request)
    tcid = body.get("tool_call_id") if isinstance(body, dict) else None
    approve = body.get("approve") if isinstance(body, dict) else None
    if not isinstance(tcid, str) or not isinstance(approve, bool):
        raise HTTPException(status_code=422, detail={"code": "bad_request", "detail": "tool_call_id, approve"})
    if not loop.confirm(run_id, tcid, approve):
        raise HTTPException(status_code=404, detail={"code": "not_pending", "detail": tcid})
    return {"ok": True}


# ---------------------------------------------------------- conversations ----

@router.get("/conversations")
async def conversations(request: Request, kind: str | None = None):
    require_local(request)
    if kind not in (None, "chat", "patrol"):
        raise HTTPException(status_code=422, detail={"code": "bad_request", "detail": "kind"})
    items = await asyncio.to_thread(store.list_conversations, kind)
    return {"items": [{**c, "running": loop.is_busy(c["id"])} for c in items]}


@router.get("/conversations/{cid}")
async def conversation(cid: str, request: Request):
    require_local(request)
    conv = await asyncio.to_thread(store.get_conversation, cid)
    if conv is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "detail": cid})
    body = await asyncio.to_thread(store.ui_messages, cid)
    usage = await asyncio.to_thread(store.conversation_usage, cid)
    return {**conv, **body, "usage": usage, "running": loop.is_busy(cid)}


@router.patch("/conversations/{cid}")
async def patch_conversation(cid: str, body: dict, request: Request):
    require_local(request)
    if store.get_conversation(cid) is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "detail": cid})
    title = body.get("title")
    archived = body.get("archived")
    if (title is not None and (not isinstance(title, str) or len(title) > 120)) or \
            (archived is not None and not isinstance(archived, bool)):
        raise HTTPException(status_code=422, detail={"code": "bad_request", "detail": "title / archived"})
    store.update_conversation(cid, title=title.strip() if isinstance(title, str) else None, archived=archived)
    return store.get_conversation(cid)


@router.delete("/conversations/{cid}")
async def delete_conversation(cid: str, request: Request):
    require_local(request)
    if loop.is_busy(cid):
        raise HTTPException(status_code=409, detail={"code": "busy", "detail": cid})
    store.delete_conversation(cid)
    return {"ok": True}


# --------------------------------------------------------------- settings ----

@router.get("/settings")
async def get_settings(request: Request):
    require_local(request)
    return _settings_payload()


@router.put("/settings")
async def put_settings(body: dict, request: Request):
    require_local(request)
    fields, errors = clean_settings(body if isinstance(body, dict) else {})
    if errors:
        raise HTTPException(status_code=422, detail={"code": "bad_request", "detail": errors})
    cfg = load_config()
    raw = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
    cfg["agent"] = merge_settings(raw, fields)
    save_config(cfg)
    return _settings_payload()


@router.put("/key")
async def put_key(body: dict, request: Request):
    require_local(request)
    key = body.get("api_key") if isinstance(body, dict) else None
    if not isinstance(key, str):
        raise HTTPException(status_code=422, detail={"code": "bad_request", "detail": "api_key"})
    try:
        secrets.set_api_key(key)
    except ValueError:
        raise HTTPException(status_code=422, detail={"code": "bad_key", "detail": "invalid key format"}) from None
    return secrets.key_status()


@router.delete("/key")
async def delete_key(request: Request):
    require_local(request)
    secrets.clear_api_key()
    return secrets.key_status()


@router.post("/test")
async def test_connection(request: Request):
    """List the account's models: proves the key works and shows whether the
    configured model ids exist."""
    require_local(request)
    key, _ = secrets.get_api_key()
    if not key:
        return {"ok": False, "code": "no_key", "message": "还没有配置 API Key"}
    cfg = agent_cfg()
    try:
        client = make_client(key, cfg)
        page = await client.models.list()
        ids = [m.id for m in page.data]
    except Exception as e:  # noqa: BLE001
        code, msg = map_error(e)
        return {"ok": False, "code": code, "message": msg}
    return {"ok": True, "models": ids, "configured": cfg["model"], "configured_available": cfg["model"] in ids}


# ------------------------------------------------------------ usage/patrol ----

@router.get("/usage")
async def usage(request: Request, range: str = "30d"):
    require_local(request)
    if range not in ("today", "7d", "30d", "90d", "all"):
        raise HTTPException(status_code=422, detail={"code": "bad_request", "detail": "range"})
    return await asyncio.to_thread(store.usage_summary, range)


@router.get("/patrol")
async def patrol_status(request: Request):
    require_local(request)
    cfg = agent_cfg()
    reports = await asyncio.to_thread(store.list_conversations, "patrol", 10)
    return {"config": cfg["patrol"], "status": dict(patrol.status), "next_due": patrol.due(), "reports": reports}


@router.post("/patrol/run")
async def patrol_run(request: Request):
    """Run a patrol now (does not consume the scheduled slot)."""
    require_local(request)
    if patrol.status.get("running"):
        raise HTTPException(status_code=409, detail={"code": "busy", "detail": "patrol running"})
    return await patrol.run_patrol("manual")
