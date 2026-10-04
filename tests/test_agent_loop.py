"""F29 agent loop: reasoning_content replay, tool dispatch and limits,
cancellation invariants, confirm mode, errors, usage accounting, patrol."""
import asyncio
import json
import threading
import time
from datetime import datetime

import httpx
import openai
import pytest
from agent_fakes import FakeClient, text, tool_calls

from tokenscope import db
from tokenscope.agent import llm, loop, patrol, store, tools
from tokenscope.agent.settings import agent_cfg


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENSCOPE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key-0000")
    db.reset_conn()

    calls = []

    def echo(x: int = 1) -> dict:
        """Echo."""
        calls.append(("echo", x))
        return {"x": x, "rows": list(range(x))}

    def write_it(note: str) -> dict:
        """Write something local."""
        calls.append(("write_it", note))
        return {"ok": True}

    def push_it() -> dict:
        """Leave the machine."""
        calls.append(("push_it",))
        return {"ok": True}

    def slow() -> dict:
        """Sleep."""
        time.sleep(0.5)
        return {"ok": True}

    reg = {
        "echo": tools._spec("echo", echo, "read"),
        "write_it": tools._spec("write_it", write_it, "write"),
        "push_it": tools._spec("push_it", push_it, "external"),
        "slow": tools._spec("slow", slow, "read"),
    }
    reg["slow"].timeout = 0.1
    monkeypatch.setattr(tools, "_REGISTRY", reg)
    yield calls
    db.reset_conn()


def _client(monkeypatch, script):
    fake = FakeClient(script)
    monkeypatch.setattr(llm, "make_client", lambda key, cfg: fake)
    return fake


def collect(gen_factory, on_event=None):
    async def go():
        out = []
        async for ev in gen_factory():
            out.append(ev)
            if on_event:
                on_event(ev)
        return out
    return asyncio.run(go())


def _answered(cid):
    msgs = store.load_api_messages(cid)
    wanted = [tc["id"] for m in msgs if m["role"] == "assistant" for tc in m.get("tool_calls") or []]
    got = [m["tool_call_id"] for m in msgs if m["role"] == "tool"]
    return wanted, got


# ------------------------------------------------------------------- core ----

def test_reasoning_content_is_replayed_with_tool_calls(env, monkeypatch):
    fake = _client(monkeypatch, [
        tool_calls([("c1", "echo", '{"x": 3}')], reasoning="I should call echo."),
        text("Done: 3 rows.", reasoning="Now answer."),
    ])
    cid = store.create_conversation()
    events = collect(lambda: loop.run_turn(cid, "how many?", {"route": "/", "query": {}}))
    names = [e["event"] for e in events]
    assert names[0] == "run_start" and names[-1] == "done"
    assert names.index("tool_call") < names.index("tool_result") < names.index("done")
    assert events[-1]["data"]["status"] == "ok"
    assert env == [("echo", 3)]

    second = fake.requests[1]["messages"]
    assert second[0]["role"] == "system"
    assert second[1]["role"] == "user" and "<页面上下文>" in second[1]["content"] and "how many?" in second[1]["content"]
    asst = second[2]
    assert asst["role"] == "assistant" and asst["reasoning_content"] == "I should call echo."
    assert asst["tool_calls"][0]["id"] == "c1"
    assert json.loads(asst["tool_calls"][0]["function"]["arguments"]) == {"x": 3}
    assert second[3] == {"role": "tool", "tool_call_id": "c1", "content": '{"x":3,"rows":[0,1,2]}'}
    # tools and thinking go out on every request
    assert fake.requests[0]["tools"] and fake.requests[0]["extra_body"] == {"thinking": {"type": "enabled"}}

    # a follow-up turn replays the final answer's reasoning too, prefix unchanged
    _client(monkeypatch, [text("ok")])
    fake2 = llm.make_client(None, None)
    collect(lambda: loop.run_turn(cid, "thanks", None))
    third = fake2.requests[0]["messages"]
    assert third[:4] == second[:4]  # byte-identical prefix → DeepSeek cache hit
    assert third[4] == {"role": "assistant", "content": "Done: 3 rows.", "reasoning_content": "Now answer."}
    assert third[5]["role"] == "user" and "thanks" in third[5]["content"]

    ui = store.ui_messages(cid)["messages"]
    assert [m["role"] for m in ui] == ["user", "assistant", "assistant", "user", "assistant"]
    assert ui[0]["content"] == "how many?"  # page-context preamble is not shown
    assert ui[1]["tool_calls"][0]["status"] == "ok"


def test_usage_and_cost_are_recorded(env, monkeypatch):
    _client(monkeypatch, [text("hi", usage={"hit": 900_000, "miss": 100_000, "completion": 10_000})])
    cfg = {**agent_cfg(), "offpeak": {"enabled": False}}
    cid = store.create_conversation()
    events = collect(lambda: loop.run_turn(cid, "hello", None, cfg=cfg))
    usage = next(e for e in events if e["event"] == "usage")["data"]
    # flash peak: 0.9 * 0.006 + 0.1 * 0.30 + 0.01 * 1.20
    assert usage["cost_usd"] == pytest.approx(0.0054 + 0.03 + 0.012)
    summary = store.usage_summary("30d")
    assert summary["requests"] == 1 and summary["cost_usd"] == pytest.approx(0.0474, abs=1e-4)
    assert summary["cache_hit_rate"] == 0.9
    assert events[-1]["data"]["totals"]["cost_usd"] == pytest.approx(0.0474)


def test_invalid_json_and_unknown_tool_go_back_to_the_model(env, monkeypatch):
    fake = _client(monkeypatch, [
        tool_calls([("c1", "echo", '{"x": '), ("c2", "rm_rf", "{}"), ("c3", "echo", '{"x": "nope"}')]),
        text("sorry"),
    ])
    cid = store.create_conversation()
    events = collect(lambda: loop.run_turn(cid, "go", None))
    results = [e["data"] for e in events if e["event"] == "tool_result"]
    assert [r["status"] for r in results] == ["error", "error", "error"]
    assert "invalid_json" in results[0]["preview"] and "unknown_tool" in results[1]["preview"]
    assert "invalid_arguments" in results[2]["preview"]
    # the broken arguments are stored as "{}" so the replayed history stays valid JSON
    asst = fake.requests[1]["messages"][2]
    assert asst["tool_calls"][0]["function"]["arguments"] == "{}"
    wanted, got = _answered(cid)
    assert wanted == got == ["c1", "c2", "c3"]


def test_max_iterations_stops_the_loop(env, monkeypatch):
    _client(monkeypatch, [tool_calls([(f"c{i}", "echo", "{}")]) for i in range(3)])
    cid = store.create_conversation()
    events = collect(lambda: loop.run_turn(cid, "loop forever", None, max_iterations=2))
    assert events[-1]["data"]["status"] == "max_iter"
    assert store.load_api_messages(cid)[-1]["role"] == "assistant"
    wanted, got = _answered(cid)
    assert wanted == got


def test_tool_timeout_is_a_tool_error(env, monkeypatch):
    _client(monkeypatch, [tool_calls([("c1", "slow", "{}")]), text("slow tool timed out")])
    cid = store.create_conversation()
    events = collect(lambda: loop.run_turn(cid, "go", None))
    result = next(e for e in events if e["event"] == "tool_result")["data"]
    assert result["status"] == "error" and "timeout" in result["preview"]


def test_external_calls_are_capped_per_run(env, monkeypatch):
    _client(monkeypatch, [tool_calls([("a", "push_it", "{}"), ("b", "push_it", "{}")]), text("done")])
    cfg = {**agent_cfg(), "max_external_calls": 1}
    cid = store.create_conversation()
    events = collect(lambda: loop.run_turn(cid, "push twice", None, cfg=cfg))
    statuses = [e["data"]["status"] for e in events if e["event"] == "tool_result"]
    assert statuses == ["ok", "blocked"] and env == [("push_it",)]


def test_read_only_toolset_hides_side_effect_tools(env, monkeypatch):
    fake = _client(monkeypatch, [tool_calls([("a", "push_it", "{}")]), text("can't")])
    cid = store.create_conversation()
    events = collect(lambda: loop.run_turn(cid, "patrol", None, kinds={"read"}))
    names = {t["function"]["name"] for t in fake.requests[0]["tools"]}
    assert names == {"echo", "slow"}
    assert next(e for e in events if e["event"] == "tool_result")["data"]["status"] == "error"
    assert env == []


# ------------------------------------------------------------ cancellation ----

def test_cancel_before_tools_run_leaves_no_dangling_calls(env, monkeypatch):
    _client(monkeypatch, [tool_calls([("a", "echo", "{}"), ("b", "echo", "{}")])])
    cid = store.create_conversation()

    def on(ev):
        if ev["event"] == "tool_call" and ev["data"]["id"] == "a":
            loop.cancel_run(next(iter(loop.RUNS)))
    events = collect(lambda: loop.run_turn(cid, "go", None), on)
    assert events[-1]["data"]["status"] == "cancelled"
    assert env == []
    wanted, got = _answered(cid)
    assert wanted == got == ["a", "b"]
    assert not loop.is_busy(cid) and not loop.RUNS


def test_consumer_disconnect_closes_dangling_calls(env, monkeypatch):
    _client(monkeypatch, [tool_calls([("a", "echo", "{}"), ("b", "echo", "{}")])])
    cid = store.create_conversation()

    async def go():
        gen = loop.run_turn(cid, "go", None)
        async for ev in gen:
            if ev["event"] == "tool_call":
                break
        await gen.aclose()
    asyncio.run(go())
    wanted, got = _answered(cid)
    assert wanted == ["a", "b"] and sorted(got) == ["a", "b"]
    assert not loop.is_busy(cid)

    # and the next turn works
    fake = _client(monkeypatch, [text("fine")])
    events = collect(lambda: loop.run_turn(cid, "again", None))
    assert events[-1]["data"]["status"] == "ok" and len(fake.requests) == 1


def test_busy_conversation_is_refused(env, monkeypatch):
    _client(monkeypatch, [text("x")])
    cid = store.create_conversation()
    loop._BUSY.add(cid)
    try:
        events = collect(lambda: loop.run_turn(cid, "go", None))
    finally:
        loop._BUSY.discard(cid)
    assert [e["event"] for e in events] == ["error"] and events[0]["data"]["code"] == "busy"


# ------------------------------------------------------------ confirm mode ----

def test_confirm_mode_waits_and_respects_denial(env, monkeypatch):
    _client(monkeypatch, [tool_calls([("w", "write_it", '{"note": "hi"}'), ("r", "echo", "{}")]), text("ok")])
    cfg = {**agent_cfg(), "confirm_side_effects": True}
    cid = store.create_conversation()

    def on(ev):
        if ev["event"] == "confirm_required":
            run_id = ev["data"]["run_id"]
            # answer from another thread, like the HTTP endpoint would
            threading.Timer(0.05, lambda: None).start()
            assert loop.confirm(run_id, ev["data"]["id"], False)
    events = collect(lambda: loop.run_turn(cid, "write", None, cfg=cfg), on)
    results = {e["data"]["id"]: e["data"]["status"] for e in events if e["event"] == "tool_result"}
    assert results == {"w": "denied", "r": "ok"}  # reads never ask
    assert env == [("echo", 1)]


# ------------------------------------------------------------------ errors ----

def _status_error(cls, code):
    req = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    return cls("boom", response=httpx.Response(code, request=req), body=None)


@pytest.mark.parametrize("exc, code", [
    (lambda: _status_error(openai.AuthenticationError, 401), "auth"),
    (lambda: _status_error(openai.APIStatusError, 402), "balance"),
    (lambda: _status_error(openai.RateLimitError, 429), "rate_limit"),
    (lambda: _status_error(openai.InternalServerError, 503), "server_busy"),
    (lambda: _status_error(openai.BadRequestError, 400), "bad_request"),
    (lambda: openai.APIConnectionError(request=httpx.Request("POST", "https://x")), "network"),
])
def test_error_mapping(exc, code):
    assert llm.map_error(exc())[0] == code


def test_api_error_surfaces_as_event(env, monkeypatch):
    _client(monkeypatch, [_status_error(openai.APIStatusError, 402)])
    cid = store.create_conversation()
    events = collect(lambda: loop.run_turn(cid, "hi", None))
    assert [e["event"] for e in events][-2:] == ["error", "done"]
    assert events[-2]["data"]["code"] == "balance" and events[-1]["data"]["status"] == "error"
    assert not loop.is_busy(cid)


def test_no_key(env, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    cid = store.create_conversation()
    events = collect(lambda: loop.run_turn(cid, "hi", None))
    assert events == [{"event": "error", "data": {"code": "no_key", "message": "还没有配置 DeepSeek API Key"}}]


def test_compaction_elides_old_tool_results_only():
    msgs = [{"role": "user", "content": "q"}]
    for i in range(10):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}"}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": "x" * 3000})
    out = loop.compact(msgs, max_tokens=4000)
    elided = [m for m in out if m["role"] == "tool" and "elided" in m["content"]]
    assert elided and all(m["content"] == "x" * 3000 for m in out[-12:] if m["role"] == "tool")
    assert loop.compact(msgs, max_tokens=10**7) is msgs


# ------------------------------------------------------------------ patrol ----

def test_period_key():
    daily = {"schedule": "daily", "time": "09:00"}
    assert patrol.period_key(datetime(2026, 9, 28, 8, 59), daily) is None
    assert patrol.period_key(datetime(2026, 9, 28, 9, 0), daily) == "2026-09-28"
    weekly = {"schedule": "weekly", "time": "09:00", "weekday": 3}  # Wednesday
    assert patrol.period_key(datetime(2026, 9, 29, 12, 0), weekly) is None     # Tuesday
    assert patrol.period_key(datetime(2026, 9, 30, 8, 0), weekly) is None      # Wed, too early
    assert patrol.period_key(datetime(2026, 9, 30, 9, 30), weekly) == "2026-W40"
    assert patrol.period_key(datetime(2026, 10, 3, 9, 30), weekly) == "2026-W40"  # catch-up later that week


def _facts(items):
    return {"generated_at": "2026-09-28 09:00", "alerts": {"items": items},
            "dev_projects": {"attention": [{"name": "app", "ahead": 2, "changes": 0, "reasons": ["unpushed"]}]}}


def test_patrol_without_key_writes_fallback_and_toasts_new_issues_once(env, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    items = [{"kind": "daily_spike", "level": "danger", "params": {"today": 9}},
             {"kind": "git_unpushed", "level": "warn", "params": {"path": "c:/a"}},
             {"kind": "retention", "level": "info", "params": {}}]
    monkeypatch.setattr(patrol, "collect_facts", lambda: _facts(items))
    toasts = []
    monkeypatch.setattr(patrol.notify, "toast", lambda *a, **k: toasts.append(a) or True)

    r = asyncio.run(patrol.run_patrol("manual"))
    assert r["ok"] and not r["used_llm"] and r["new_issues"] == 1 and r["notified"]
    ui = store.ui_messages(r["conversation_id"])["messages"]
    assert "巡检报告" in ui[-1]["content"] and "daily_spike" in ui[-1]["content"]
    assert "#/agent?c=" in toasts[0][2]
    assert store.get_conversation(r["conversation_id"])["kind"] == "patrol"

    r2 = asyncio.run(patrol.run_patrol("manual"))
    assert r2["new_issues"] == 0 and len(toasts) == 1


def test_patrol_with_llm_uses_read_only_tools(env, monkeypatch):
    monkeypatch.setattr(patrol, "collect_facts", lambda: _facts([]))
    monkeypatch.setattr(patrol.notify, "toast", lambda *a, **k: True)
    fake = _client(monkeypatch, [text("# 巡检\n目前没有异常。")])
    r = asyncio.run(patrol.run_patrol("manual"))
    assert r["ok"] and r["used_llm"]
    names = {t["function"]["name"] for t in fake.requests[0]["tools"]}
    assert names == {"echo", "slow"}
    assert fake.requests[0]["extra_body"] == {"thinking": {"type": "disabled"}}


def test_due_respects_enabled_and_dedupe(env, monkeypatch):
    base = agent_cfg({})
    on = {"agent": {"patrol": {**base["patrol"], "enabled": True, "time": "00:00"}}}
    assert patrol.due(datetime(2026, 9, 28, 10, 0).astimezone(), {}) is None
    key = patrol.due(datetime(2026, 9, 28, 10, 0).astimezone(), on)
    assert key == "2026-09-28"
    db.set_meta(patrol.META_LAST, key)
    assert patrol.due(datetime(2026, 9, 28, 11, 0).astimezone(), on) is None
