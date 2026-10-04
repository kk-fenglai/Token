"""The agent loop: one user turn → model ↔ tools until the model answers.

`run_turn()` is an async generator of UI events ({"event", "data"}), which
the route turns into SSE. Invariants worth protecting:

- Every assistant message is persisted in full (content + reasoning_content
  + tool_calls) before its tools run, and every tool_call_id gets exactly one
  tool message — also when the run is cancelled, times out or errors. A
  dangling tool_call_id makes the next request fail validation.
- One run per conversation at a time (`is_busy`).
- Hard limits live here, not in the prompt: the toolset passed in decides
  what exists at all, external calls are capped per run, and in confirm mode
  write/external tools wait for the user.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import AsyncIterator

from . import llm, pricing, secrets, store
from .prompt import SYSTEM_PROMPT, context_block
from .settings import agent_cfg
from .tools import ToolResult, ToolSet

CONFIRM_TIMEOUT = 300.0
KEEP_RECENT_TOOL_RESULTS = 6
CHARS_PER_TOKEN = 3.0  # rough; JSON + CJK mix


@dataclass
class Run:
    id: str
    conv_id: str
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    pending: dict[str, asyncio.Future] = field(default_factory=dict)


RUNS: dict[str, Run] = {}
_BUSY: set[str] = set()


def is_busy(conv_id: str) -> bool:
    return conv_id in _BUSY


def cancel_run(run_id: str) -> bool:
    run = RUNS.get(run_id)
    if not run:
        return False
    run.cancel.set()
    for fut in run.pending.values():
        if not fut.done():
            fut.set_result(False)
    return True


def confirm(run_id: str, tool_call_id: str, approve: bool) -> bool:
    run = RUNS.get(run_id)
    fut = run.pending.get(tool_call_id) if run else None
    if fut is None or fut.done():
        return False
    fut.set_result(bool(approve))
    return True


def _ev(event: str, **data) -> dict:
    return {"event": event, "data": data}


# ------------------------------------------------------------- compaction ----

def compact(messages: list[dict], max_tokens: int) -> list[dict]:
    """Elide old tool results once the history is estimated to exceed
    `max_tokens`. Deterministic for a given history, so repeated requests
    share a prefix until the boundary moves."""
    size = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages) / CHARS_PER_TOKEN
    if size <= max_tokens:
        return messages
    tool_idx = [i for i, m in enumerate(messages) if m["role"] == "tool"]
    out = [dict(m) for m in messages]
    for i in tool_idx[:-KEEP_RECENT_TOOL_RESULTS]:
        content = out[i].get("content") or ""
        if len(content) > 200:
            out[i]["content"] = f'{{"elided":true,"chars":{len(content)},"note":"旧的工具结果已省略,需要时重新调用"}}'
            size -= (len(content) - 90) / CHARS_PER_TOKEN
            if size <= max_tokens:
                break
    return out


def _dangling(conv_id: str) -> list[dict]:
    """tool_calls of the last assistant message that have no tool message."""
    msgs = store.load_api_messages(conv_id)
    for idx in range(len(msgs) - 1, -1, -1):
        m = msgs[idx]
        if m["role"] == "assistant":
            answered = {x.get("tool_call_id") for x in msgs[idx + 1:] if x["role"] == "tool"}
            return [tc for tc in m.get("tool_calls") or [] if tc.get("id") not in answered]
        if m["role"] == "user":
            return []
    return []


def close_dangling(conv_id: str, run_id: str | None, reason: str = "cancelled") -> int:
    missing = _dangling(conv_id)
    for tc in missing:
        payload = json.dumps({"error": reason}, ensure_ascii=False)
        store.append_message(conv_id, {"role": "tool", "tool_call_id": tc["id"], "content": payload}, run_id)
        if run_id:
            store.log_tool_call(run_id, conv_id, tc["id"], tc.get("function", {}).get("name", "?"), None,
                                tc.get("function", {}).get("arguments"), "error", payload, len(payload), 0)
    return len(missing)


def _valid_args(raw: str) -> bool:
    try:
        return isinstance(json.loads(raw or "{}"), dict)
    except ValueError:
        return False


# ------------------------------------------------------------------- loop ----

async def run_turn(conv_id: str, user_text: str, page_ctx: dict | None = None, *,
                   trigger: str = "chat", kinds: set[str] | None = None, cfg: dict | None = None,
                   max_iterations: int | None = None, thinking: bool | None = None,
                   display_text: str | None = None) -> AsyncIterator[dict]:
    cfg = cfg or agent_cfg()
    kinds = kinds or {"read", "write", "external"}
    max_iterations = max_iterations or cfg["max_iterations"]
    thinking = cfg["thinking"] if thinking is None else thinking
    model = cfg["model"]

    if conv_id in _BUSY:
        yield _ev("error", code="busy", message="这个对话正在运行中")
        return
    key, _ = secrets.get_api_key()
    if not key:
        yield _ev("error", code="no_key", message="还没有配置 DeepSeek API Key")
        return

    _BUSY.add(conv_id)
    run_id = store.start_run(conv_id, trigger, model)
    run = Run(run_id, conv_id)
    RUNS[run_id] = run
    status, error_msg, iterations = "ok", None, 0
    finished: dict = {}
    totals = {"hit": 0, "miss": 0, "completion": 0, "cost_usd": 0.0}
    try:
        yield _ev("run_start", run_id=run_id, conversation_id=conv_id, model=model)
        close_dangling(conv_id, run_id, "interrupted")  # a previous crash must not poison this turn
        store.append_message(conv_id, {"role": "user", "content": f"{context_block(page_ctx)}\n\n{user_text}"},
                             run_id, display={"text": display_text if display_text is not None else user_text})
        conv = store.get_conversation(conv_id)
        if conv and not conv["title"]:
            store.update_conversation(conv_id, title=(display_text or user_text).strip().replace("\n", " ")[:40])

        client = llm.make_client(key, cfg)
        toolset = ToolSet(kinds)
        schemas = toolset.schemas()
        external_calls = 0

        while True:
            if iterations >= max_iterations:
                status = "max_iter"
                note = f"(已达到本轮最多 {max_iterations} 步的上限,先停在这里。可以让我继续。)"
                store.append_message(conv_id, {"role": "assistant", "content": note}, run_id)
                yield _ev("text_delta", text=("\n\n" + note))
                break
            if run.cancel.is_set():
                status = "cancelled"
                break
            iterations += 1
            history = compact(store.load_api_messages(conv_id), cfg["max_context_tokens"])
            messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
            yield _ev("step", n=iterations)

            comp: llm.Completion | None = None
            partial_text, partial_reasoning = "", ""
            gen = llm.stream_completion(client, model=model, messages=messages, tools=schemas, thinking=thinking)
            try:
                async for kind, val in gen:
                    if kind == "reasoning":
                        partial_reasoning += val
                        yield _ev("reasoning_delta", text=val)
                    elif kind == "text":
                        partial_text += val
                        yield _ev("text_delta", text=val)
                    elif kind == "done":
                        comp = val
                    if run.cancel.is_set():
                        break
            finally:
                await gen.aclose()

            if comp is None:  # cancelled mid-stream: keep what the user already saw, drop partial tool calls
                status = "cancelled"
                if partial_text or partial_reasoning:
                    store.append_message(conv_id, {"role": "assistant", "content": partial_text,
                                                   "reasoning_content": partial_reasoning or None}, run_id)
                break

            if comp.usage:
                cost = pricing.cost_usd(model, comp.usage.get("hit", 0), comp.usage.get("miss", 0),
                                        comp.usage.get("completion", 0), cfg)
                store.record_request(run_id, conv_id, model, comp.usage, cost)
                for k in ("hit", "miss", "completion"):
                    totals[k] += comp.usage.get(k, 0)
                totals["cost_usd"] = round(totals["cost_usd"] + cost, 6)
                yield _ev("usage", **comp.usage, cost_usd=cost)

            calls = []
            for tc in comp.tool_calls:
                args = tc["function"]["arguments"]
                calls.append({**tc, "function": {**tc["function"],
                                                 "arguments": args if _valid_args(args) else "{}"},
                              "_raw_args": args})
            store.append_message(conv_id, {
                "role": "assistant", "content": comp.content,
                "reasoning_content": comp.reasoning or None,
                "tool_calls": [{k: v for k, v in c.items() if k != "_raw_args"} for c in calls] or None,
            }, run_id)

            if not calls:
                if comp.finish_reason == "length":
                    status = "length"
                    yield _ev("notice", code="length", message="回答达到长度上限被截断")
                break

            for tc in calls:
                name, raw = tc["function"]["name"], tc["_raw_args"]
                kind = toolset.kind(name)
                yield _ev("tool_call", id=tc["id"], name=name, args=raw, kind=kind)
                result: ToolResult | None = None

                if run.cancel.is_set():
                    result = ToolResult(False, '{"error":"cancelled"}', '{"error":"cancelled"}', False, 0, "error")
                elif kind == "external" and external_calls >= cfg["max_external_calls"]:
                    payload = json.dumps({"error": "external_limit",
                                          "detail": f"本轮最多执行 {cfg['max_external_calls']} 次外部操作"},
                                         ensure_ascii=False)
                    result = ToolResult(False, payload, payload, False, 0, "blocked")
                elif cfg["confirm_side_effects"] and kind in ("write", "external"):
                    fut = asyncio.get_running_loop().create_future()
                    run.pending[tc["id"]] = fut
                    yield _ev("confirm_required", id=tc["id"], name=name, args=raw, kind=kind, run_id=run_id)
                    try:
                        approved = await asyncio.wait_for(fut, CONFIRM_TIMEOUT)
                    except asyncio.TimeoutError:
                        approved = False
                    finally:
                        run.pending.pop(tc["id"], None)
                    if not approved:
                        payload = json.dumps({"denied": True, "detail": "用户没有批准这次操作"}, ensure_ascii=False)
                        result = ToolResult(False, payload, payload, False, 0, "denied")

                if result is None:
                    spec = toolset.specs.get(name)
                    try:
                        result = await asyncio.wait_for(asyncio.to_thread(toolset.call, name, raw),
                                                        spec.timeout if spec else 60)
                    except asyncio.TimeoutError:
                        payload = json.dumps({"error": "timeout"})
                        result = ToolResult(False, payload, payload, False, int((spec.timeout if spec else 60) * 1000),
                                            "error")
                    if kind == "external":
                        external_calls += 1

                store.append_message(conv_id, {"role": "tool", "tool_call_id": tc["id"], "content": result.content},
                                     run_id)
                store.log_tool_call(run_id, conv_id, tc["id"], name, kind, raw, result.status, result.full,
                                    len(result.full), result.ms)
                yield _ev("tool_result", id=tc["id"], name=name, ok=result.ok, status=result.status,
                          preview=result.full[:4000], chars=len(result.full), truncated=result.truncated,
                          ms=result.ms)
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except Exception as e:  # noqa: BLE001 — surfaced to the UI, never a 500 mid-stream
        code, msg = llm.map_error(e)
        status, error_msg = "error", f"{code}: {msg}"
        yield _ev("error", code=code, message=msg)
    finally:
        try:
            close_dangling(conv_id, run_id, status if status != "ok" else "interrupted")
            finished = store.finish_run(run_id, status, error_msg, iterations)
            store.update_conversation(conv_id, touch=True)
        finally:
            RUNS.pop(run_id, None)
            _BUSY.discard(conv_id)
    yield _ev("done", status=status, run_id=run_id, iterations=iterations,
              totals={**totals, "cost_usd": finished.get("cost_usd", totals["cost_usd"])})
