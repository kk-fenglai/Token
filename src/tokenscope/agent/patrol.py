"""Scheduled patrol: once per day (or week) after the configured local time,
collect the facts, have the assistant write a report with READ-ONLY tools,
store it as a `patrol` conversation and toast when something new is wrong.

Scheduling rides on the web scheduler loop (every sync interval), so timing
is accurate to within `sync_interval_seconds`; a missed slot (machine off)
runs on the next tick. `agent:patrol:last` in the meta table dedupes.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from .. import insights, notify
from ..config import load_config
from ..db import get_meta, set_meta
from . import secrets, store
from .loop import run_turn
from .prompt import PATROL_INSTRUCTION
from .settings import agent_cfg

META_LAST = "agent:patrol:last"
META_FP = "agent:patrol:fp"
PATROL_MAX_ITER = 6

_running = False
status: dict = {"last_run": None, "last_conversation": None, "last_error": None, "running": False}


def period_key(now: datetime, pc: dict) -> str | None:
    """The slot `now` falls in, or None before today's configured time (or
    before this week's weekday+time for weekly)."""
    hh, mm = (int(x) for x in pc.get("time", "09:00").split(":"))
    at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if pc.get("schedule") == "weekly":
        iso = now.isocalendar()
        wd = int(pc.get("weekday", 1))
        if iso[2] < wd or (iso[2] == wd and now < at):
            return None
        return f"{iso[0]}-W{iso[1]:02d}"
    if now < at:
        return None
    return now.strftime("%Y-%m-%d")


def due(now: datetime | None = None, cfg: dict | None = None) -> str | None:
    pc = agent_cfg(cfg)["patrol"]
    if not pc.get("enabled"):
        return None
    key = period_key(now or datetime.now().astimezone(), pc)
    if key is None or get_meta(META_LAST) == key:
        return None
    return key


def fingerprints(items: list[dict]) -> set[str]:
    out = set()
    for a in items:
        if a.get("level") not in ("warn", "danger"):
            continue
        p = a.get("params") or {}
        out.add("|".join(str(x) for x in (a.get("kind"), p.get("path") or p.get("name") or "", p.get("session_id") or "")))
    return out


def collect_facts() -> dict:
    """Deterministic facts, no LLM. Each section fails soft."""
    facts: dict = {"generated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")}

    def section(name, fn):
        try:
            facts[name] = fn()
        except Exception as e:  # noqa: BLE001
            facts[name] = {"error": f"{type(e).__name__}: {e}"[:200]}

    section("alerts", lambda: insights.alerts())
    section("dev_projects", _dev_summary)
    section("week", _week_summary)
    section("retention", insights.retention_info)
    section("assistant_spend_7d", lambda: {k: v for k, v in store.usage_summary("7d").items()
                                           if k in ("cost_usd", "requests", "estimated")})
    return facts


def _dev_summary() -> dict:
    from .. import dev_projects
    snap = dev_projects.snapshot()
    return {"summary": snap["summary"],
            "attention": [{k: x.get(k) for k in ("name", "path", "level", "reasons", "ahead", "changes",
                                                   "unpushed_age_hours", "dirty_age_hours")}
                          for x in snap["items"] if x["level"] in ("warn", "danger")][:10]}


def _week_summary() -> dict:
    r = insights.weekly_report(0)
    keep = ("week", "totals", "previous", "delta_pct", "busiest_day", "top_projects", "top_models", "subagents")
    return {k: r[k] for k in keep if k in r}


def fallback_report(facts: dict) -> str:
    """Report without an LLM (no key, or the call failed)."""
    lines = [f"# 巡检报告 · {facts['generated_at']}", ""]
    alerts = (facts.get("alerts") or {}).get("items") or []
    serious = [a for a in alerts if a.get("level") in ("warn", "danger")]
    lines.append("**结论:** " + (f"有 {len(serious)} 项需要关注。" if serious else "目前没有异常。"))
    if serious:
        lines += ["", "## 需要关注", ""]
        for a in serious:
            lines.append(f"- `{a['kind']}`({a['level']}):{json.dumps(a.get('params') or {}, ensure_ascii=False)}")
    dev = (facts.get("dev_projects") or {}).get("attention") or []
    lines += ["", "## 开发项目", ""]
    if dev:
        for x in dev:
            bits = []
            if x.get("ahead"):
                bits.append(f"{x['ahead']} 个提交未推送")
            if x.get("changes"):
                bits.append(f"{x['changes']} 处改动未提交")
            lines.append(f"- **{x['name']}**:{' · '.join(bits) or ', '.join(x.get('reasons') or [])}")
    else:
        lines.append("无")
    lines += ["", "_未配置 DeepSeek Key 或调用失败,这是系统自动生成的简版报告。_"]
    return "\n".join(lines)


async def run_patrol(trigger: str = "schedule", period: str | None = None) -> dict:
    global _running
    if _running:
        return {"ok": False, "error": "running"}
    _running = True
    status["running"] = True
    now = datetime.now().astimezone()
    try:
        cfg = agent_cfg()
        pc = cfg["patrol"]
        facts = await asyncio.to_thread(collect_facts)
        title = f"巡检 · {now.strftime('%m-%d %H:%M')}"
        cid = store.create_conversation("patrol", title, {"route": "/agent", "trigger": trigger}, cfg["model"])
        key, _ = secrets.get_api_key()
        report_ok = False
        if key and pc.get("use_llm", True):
            text = PATROL_INSTRUCTION + json.dumps(facts, ensure_ascii=False, default=str)
            final = ""
            async for ev in run_turn(cid, text, None, trigger="patrol", kinds={"read"}, cfg=cfg,
                                     max_iterations=PATROL_MAX_ITER, thinking=bool(pc.get("thinking")),
                                     display_text=f"例行巡检({'手动' if trigger == 'manual' else '定时'})"):
                if ev["event"] == "text_delta":
                    final += ev["data"]["text"]
                elif ev["event"] == "done":
                    report_ok = ev["data"]["status"] in ("ok", "length", "max_iter") and bool(final.strip())
        if not report_ok:
            store.append_message(cid, {"role": "user", "content": "例行巡检"}, None, display={"text": "例行巡检"})
            store.append_message(cid, {"role": "assistant", "content": fallback_report(facts)}, None)

        alerts = (facts.get("alerts") or {}).get("items") or []
        dev_cfg = load_config().get("dev_projects") or {}
        if dev_cfg.get("desktop_notify", True):
            alerts = [a for a in alerts if not str(a.get("kind", "")).startswith("git_")]  # F26 already toasts these
        fps = fingerprints(alerts)
        seen = set(json.loads(get_meta(META_FP) or "[]"))
        new = fps - seen
        sent = False
        if new and pc.get("notify", True):
            port = load_config().get("port", 8787)
            sent = await asyncio.to_thread(
                notify.toast, f"TokenScope 巡检 · {len(new)} 项新问题",
                "打开看板查看巡检报告与建议", f"http://127.0.0.1:{port}/#/agent?c={cid}")
        set_meta(META_FP, json.dumps(sorted(fps)))
        if period:
            set_meta(META_LAST, period)
        status.update(last_run=now.strftime("%Y-%m-%dT%H:%M:%S%z"), last_conversation=cid, last_error=None)
        return {"ok": True, "conversation_id": cid, "used_llm": report_ok, "new_issues": len(new), "notified": sent}
    except Exception as e:  # noqa: BLE001 — must never take the scheduler down
        status["last_error"] = f"{type(e).__name__}: {e}"[:300]
        if period:
            set_meta(META_LAST, period)  # don't retry a broken run every tick
        return {"ok": False, "error": status["last_error"]}
    finally:
        _running = False
        status["running"] = False


def maybe_start() -> asyncio.Task | None:
    """Called from the web scheduler each tick; never blocks it."""
    if _running:
        return None
    try:
        period = due()
    except Exception:  # noqa: BLE001
        return None
    if not period:
        return None
    return asyncio.create_task(run_patrol("schedule", period))
