"""Second-order analytics: sessions, tool attribution, heatmap, alerts, weekly report.

`queries` answers "how much"; this module answers "where inside a session and
why". Everything is still derived from the `events` table at query time, so
pricing edits and project folding apply here retroactively too.

Vocabulary used throughout:
- context size of a turn = input + cache_write + cache_read (the prompt that was
  sent). It grows with the conversation; watching it per session shows where a
  chat should have been /clear'ed.
- a tool's cost = the cost of the assistant messages that *called* it, split
  evenly when one message called several tools. The tokens the tool's result
  adds land in the next turn's input, so this is the "decision cost", not the
  full downstream cost.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

from . import queries, subscription
from .db import get_meta, locked_conn
from .pricing import cost_of_model, load_pricing, rates_for_model
from .projects import Folder

CTX_EXPR = "(input_tokens + cache_write_tokens + cache_read_tokens)"
TOKEN_SUM = ("SUM(input_tokens) i, SUM(output_tokens) o, "
             "SUM(cache_write_tokens) w, SUM(cache_read_tokens) r")
SESSION_LIMIT = 5000

# Alert thresholds. Deliberately blunt: they exist to point at something worth a
# look, not to be a monitoring system.
SPIKE_WARN, SPIKE_DANGER = 2.0, 4.0
WEEK_DELTA_INFO = 0.30
RUNAWAY_SHARE, RUNAWAY_MIN_COST = 0.40, 5.0
CONTEXT_BLOAT_TOKENS = 150_000
CACHE_HIT_WARN = 0.70
SUBAGENT_SHARE_INFO = 0.30
PRICING_STALE_DAYS = 90
DEFAULT_CLEANUP_DAYS = 30


# ---------------------------------------------------------------- helpers ----

def _local_tz():
    return datetime.now().astimezone().tzinfo


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _where(start: str | None, end: str | None, project: str | None,
           extra: list[str] | None = None) -> tuple[str, list]:
    clauses, params = list(extra or []), []
    if start:
        clauses.append("ts >= ?"); params.append(start)
    if end:
        clauses.append("ts < ?"); params.append(end)
    pc, pp = queries.project_clause(project)
    if pc:
        clauses.append(pc); params += pp
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def _cost(row, pricing) -> float:
    return cost_of_model(row["model"], row["f"], row["i"] or 0, row["o"] or 0,
                         row["w"] or 0, row["r"] or 0, pricing)


def _blank_tokens() -> dict:
    return {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}


def _add_tokens(dst: dict, row) -> None:
    dst["input"] += row["i"] or 0
    dst["output"] += row["o"] or 0
    dst["cache_write"] += row["w"] or 0
    dst["cache_read"] += row["r"] or 0


def _tokens_total(t: dict) -> int:
    return t["input"] + t["output"] + t["cache_write"] + t["cache_read"]


# --------------------------------------------------------------- sessions ----

def _session_rows(where: str, params: list):
    with locked_conn() as conn:
        return conn.execute(
            f"SELECT session_id s, model, model_family f, is_sidechain side, "
            f"MAX(project_path) p, MAX(project_name) name, "
            f"MIN(ts) first_ts, MAX(ts) last_ts, COUNT(*) n, {TOKEN_SUM}, "
            f"MAX({CTX_EXPR}) ctx_max, COALESCE(SUM(tool_count), 0) tools "
            f"FROM events {where} GROUP BY session_id, model, model_family, is_sidechain",
            params,
        ).fetchall()


def _merge_sessions(rows, pricing, folder: Folder) -> list[dict]:
    out: dict[str, dict] = {}
    for row in rows:
        s = out.setdefault(row["s"], {
            "session_id": row["s"], "project_path": row["p"], "first_ts": row["first_ts"],
            "last_ts": row["last_ts"], "messages": 0, "tokens": _blank_tokens(), "cost": 0.0,
            "models": set(), "tool_calls": 0, "subagent_events": 0, "subagent_cost": 0.0,
            "ctx_max": 0,
        })
        cost = _cost(row, pricing)
        s["cost"] += cost
        s["messages"] += row["n"]
        _add_tokens(s["tokens"], row)
        s["first_ts"] = min(s["first_ts"], row["first_ts"])
        s["last_ts"] = max(s["last_ts"], row["last_ts"])
        s["ctx_max"] = max(s["ctx_max"], row["ctx_max"] or 0)
        s["tool_calls"] += row["tools"] or 0
        s["models"].add(row["model"])
        if row["side"]:
            s["subagent_events"] += row["n"]
            s["subagent_cost"] += cost
        elif s["project_path"] != row["p"]:
            s["project_path"] = row["p"]  # prefer the main transcript's cwd
    tz = _local_tz()
    items = []
    for s in out.values():
        first, last = _parse_ts(s["first_ts"]), _parse_ts(s["last_ts"])
        key = folder.fold(s["project_path"])
        s["project"] = key
        s["name"] = folder.name(key)
        s["day"] = first.astimezone(tz).strftime("%Y-%m-%d")
        s["duration_s"] = int((last - first).total_seconds())
        s["tokens_total"] = _tokens_total(s["tokens"])
        s["cost"] = round(s["cost"], 4)
        s["subagent_cost"] = round(s["subagent_cost"], 4)
        s["models"] = sorted(s["models"])
        items.append(s)
    return items


def sessions(range_key: str | None = "7d", from_: str | None = None, to_: str | None = None,
             project: str | None = None, q: str | None = None, sort: str = "start",
             page: int = 1, page_size: int = 50) -> dict:
    """Sessions active in the range (partial sessions are cut at the boundary).

    sort: "start" (newest first) or "cost" (most expensive first).
    """
    pricing = load_pricing()
    folder = Folder()
    start, end = queries.resolve_range(range_key, from_, to_)
    where, params = _where(start, end, project, ["session_id IS NOT NULL"])
    if q:
        like = f"%{q}%"
        where += " AND (project_name LIKE ? OR session_id LIKE ?)"
        params += [like, like]
    items = _merge_sessions(_session_rows(where, params), pricing, folder)
    if sort == "cost":
        items.sort(key=lambda x: (-x["cost"], x["first_ts"]))
    else:
        items.sort(key=lambda x: x["first_ts"], reverse=True)
    total = len(items)
    lo = (max(page, 1) - 1) * page_size
    return {
        "total": total, "page": page, "page_size": page_size,
        "items": items[lo:lo + page_size],
        "totals": {
            "sessions": total,
            "cost": round(sum(x["cost"] for x in items), 4),
            "messages": sum(x["messages"] for x in items),
            "tokens": sum(x["tokens_total"] for x in items),
        },
    }


def session_detail(session_id: str) -> dict | None:
    """One session as a timeline: per-message context size, cost and tools."""
    pricing = load_pricing()
    folder = Folder()
    with locked_conn() as conn:
        rows = conn.execute(
            "SELECT ts, model, model_family f, project_path, input_tokens i, output_tokens o, "
            "cache_write_tokens w, cache_read_tokens r, tool_names, tool_count, "
            "is_sidechain side, agent_name FROM events WHERE session_id = ? "
            f"ORDER BY ts, id LIMIT {SESSION_LIMIT}",
            (session_id,),
        ).fetchall()
    if not rows:
        return None
    summary = _merge_sessions(_session_rows("WHERE session_id = ?", [session_id]), pricing, folder)[0]

    messages, cumulative = [], 0.0
    for idx, r in enumerate(rows):
        cost = _cost(r, pricing)
        cumulative += cost
        messages.append({
            "i": idx,
            "ts": r["ts"],
            "model": r["model"],
            "input": r["i"], "output": r["o"], "cache_write": r["w"], "cache_read": r["r"],
            "context": (r["i"] or 0) + (r["w"] or 0) + (r["r"] or 0),
            "cost": round(cost, 6),
            "cumulative_cost": round(cumulative, 4),
            "tools": json.loads(r["tool_names"]) if r["tool_names"] else [],
            "sidechain": bool(r["side"]),
            "agent": r["agent_name"],
        })
    peak = max(messages, key=lambda m: m["context"]) if messages else None
    return {
        "session": summary,
        "messages": messages,
        "tools": _tools_from_rows(rows, pricing),
        "peak_context": {"i": peak["i"], "context": peak["context"], "ts": peak["ts"]} if peak else None,
        "truncated": len(rows) >= SESSION_LIMIT,
    }


# ------------------------------------------------------------------ tools ----

def _tools_from_rows(rows, pricing) -> dict:
    """Aggregate per-event rows (with tool_names / side / agent_name) by tool."""
    tools: dict[str, dict] = {}
    text_only = {"messages": 0, "cost": 0.0, "output_tokens": 0}
    side = {"events": 0, "cost": 0.0, "tokens": 0, "by_agent": {}}
    total_cost, total_events = 0.0, 0
    for r in rows:
        cost = _cost(r, pricing)
        total_cost += cost
        total_events += 1
        names = json.loads(r["tool_names"]) if r["tool_names"] else []
        if r["side"]:
            side["events"] += 1
            side["cost"] += cost
            side["tokens"] += (r["i"] or 0) + (r["o"] or 0) + (r["w"] or 0) + (r["r"] or 0)
            agent = side["by_agent"].setdefault(r["agent_name"] or "unknown", {"events": 0, "cost": 0.0})
            agent["events"] += 1
            agent["cost"] += cost
        if not names:
            text_only["messages"] += 1
            text_only["cost"] += cost
            text_only["output_tokens"] += r["o"] or 0
            continue
        share = 1.0 / len(names)
        seen = set()
        for name in names:
            t = tools.setdefault(name, {"name": name, "calls": 0, "messages": 0,
                                        "output_tokens": 0.0, "cost": 0.0})
            t["calls"] += 1
            t["output_tokens"] += (r["o"] or 0) * share
            t["cost"] += cost * share
            if name not in seen:
                t["messages"] += 1
                seen.add(name)
    items = sorted(tools.values(), key=lambda x: -x["cost"])
    for t in items:
        t["output_tokens"] = int(round(t["output_tokens"]))
        t["cost"] = round(t["cost"], 4)
        t["cost_share"] = round(t["cost"] / total_cost, 4) if total_cost else 0.0
    text_only["cost"] = round(text_only["cost"], 4)
    side["cost"] = round(side["cost"], 4)
    side["cost_share"] = round(side["cost"] / total_cost, 4) if total_cost else 0.0
    side["by_agent"] = sorted(
        ({"agent": k, "events": v["events"], "cost": round(v["cost"], 4)} for k, v in side["by_agent"].items()),
        key=lambda x: -x["cost"])
    return {
        "tools": items,
        "text_only": text_only,
        "subagents": side,
        "totals": {"cost": round(total_cost, 4), "events": total_events,
                   "tool_calls": sum(t["calls"] for t in items)},
    }


def _event_rows(start, end, project):
    where, params = _where(start, end, project)
    with locked_conn() as conn:
        return conn.execute(
            "SELECT model, model_family f, input_tokens i, output_tokens o, cache_write_tokens w, "
            "cache_read_tokens r, tool_names, tool_count, is_sidechain side, agent_name "
            f"FROM events {where}", params,
        ).fetchall()


def tools_breakdown(range_key: str | None = "30d", project: str | None = None,
                    from_: str | None = None, to_: str | None = None) -> dict:
    """Which tools the model spent its turns on, plus the subagent share."""
    pricing = load_pricing()
    start, end = queries.resolve_range(range_key, from_, to_)
    out = _tools_from_rows(_event_rows(start, end, project), pricing)
    out["range"] = range_key
    return out


# ---------------------------------------------------------------- heatmap ----

def heatmap(range_key: str | None = "30d", project: str | None = None,
            from_: str | None = None, to_: str | None = None) -> dict:
    """7×24 matrix (local time) of tokens, cost and calls. dow: 0 = Sunday."""
    pricing = load_pricing()
    start, end = queries.resolve_range(range_key, from_, to_)
    where, params = _where(start, end, project)
    with locked_conn() as conn:
        rows = conn.execute(
            "SELECT CAST(strftime('%w', ts, 'localtime') AS INTEGER) dow, "
            "CAST(strftime('%H', ts, 'localtime') AS INTEGER) hour, "
            f"model, model_family f, {TOKEN_SUM}, COUNT(*) n "
            f"FROM events {where} GROUP BY dow, hour, model, model_family", params,
        ).fetchall()
    cells = {(d, h): {"dow": d, "hour": h, "tokens": 0, "cost": 0.0, "events": 0}
             for d in range(7) for h in range(24)}
    for r in rows:
        c = cells[(r["dow"], r["hour"])]
        c["tokens"] += (r["i"] or 0) + (r["o"] or 0) + (r["w"] or 0) + (r["r"] or 0)
        c["cost"] += _cost(r, pricing)
        c["events"] += r["n"]
    items = list(cells.values())
    for c in items:
        c["cost"] = round(c["cost"], 4)
    by_hour = [round(sum(c["cost"] for c in items if c["hour"] == h), 4) for h in range(24)]
    by_dow = [round(sum(c["cost"] for c in items if c["dow"] == d), 4) for d in range(7)]
    peak = max(items, key=lambda c: c["cost"]) if any(c["cost"] for c in items) else None
    return {
        "range": range_key, "cells": items,
        "max_tokens": max(c["tokens"] for c in items), "max_cost": max(c["cost"] for c in items),
        "by_hour": by_hour, "by_dow": by_dow,
        "peak": {"dow": peak["dow"], "hour": peak["hour"], "cost": peak["cost"]} if peak else None,
        "total_cost": round(sum(by_hour), 4),
    }


# ------------------------------------------------------- pricing / retention ----

def pricing_status() -> dict:
    """How old the rate table is. Anthropic changes prices; a stale table
    quietly skews every cost on every page."""
    doc = load_pricing()
    raw = doc.get("last_verified")
    days = None
    try:
        verified = datetime.strptime(str(raw), "%Y-%m-%d").date()
        days = (datetime.now().astimezone().date() - verified).days
    except (TypeError, ValueError):
        verified = None
    return {
        "last_verified": str(raw) if raw else None,
        "age_days": days,
        "stale": days is None or days > PRICING_STALE_DAYS,
        "stale_after_days": PRICING_STALE_DAYS,
        "unit": doc.get("unit"),
    }


def retention_info() -> dict:
    """Claude Code's transcript retention vs. how recently we captured them."""
    path = Path.home() / ".claude" / "settings.json"
    days, configured = DEFAULT_CLEANUP_DAYS, False
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        v = doc.get("cleanupPeriodDays") if isinstance(doc, dict) else None
        if isinstance(v, (int, float)) and v > 0:
            days, configured = int(v), True
    except (OSError, ValueError):
        pass
    last_sync = get_meta("last_sync_at")
    since_sync = None
    if last_sync:
        since_sync = round((datetime.now().astimezone() - _parse_ts(last_sync)).total_seconds() / 86400, 2)
    return {
        "cleanup_days": days,
        "configured": configured,
        "settings_path": str(path),
        "last_sync_at": last_sync,
        "days_since_sync": since_sync,
        # Anything shorter than a few weeks risks losing history if the
        # dashboard is not opened for a while; a year is generous and cheap.
        "recommended_days": 365,
    }


# ----------------------------------------------------------------- alerts ----

def _daily_costs(days: int, project: str | None) -> dict[str, float]:
    pricing = load_pricing()
    start, _ = queries.resolve_range(None, (datetime.now().astimezone() - timedelta(days=days)).strftime("%Y-%m-%d"), None)
    where, params = _where(start, None, project)
    with locked_conn() as conn:
        rows = conn.execute(
            f"SELECT date(ts,'localtime') d, model, model_family f, {TOKEN_SUM} "
            f"FROM events {where} GROUP BY d, model, model_family", params,
        ).fetchall()
    out: dict[str, float] = {}
    for r in rows:
        out[r["d"]] = out.get(r["d"], 0.0) + _cost(r, pricing)
    return out


def _month_efficiency(project: str | None) -> dict:
    pricing = load_pricing()
    m_start, _ = queries.resolve_range("month")
    where, params = _where(m_start, None, project)
    with locked_conn() as conn:
        rows = conn.execute(
            f"SELECT model, model_family f, is_sidechain side, {TOKEN_SUM}, COUNT(*) n "
            f"FROM events {where} GROUP BY model, model_family, is_sidechain", params,
        ).fetchall()
    tokens = _blank_tokens()
    cost = side_cost = 0.0
    for r in rows:
        _add_tokens(tokens, r)
        c = _cost(r, pricing)
        cost += c
        if r["side"]:
            side_cost += c
    prompt = tokens["input"] + tokens["cache_write"] + tokens["cache_read"]
    return {
        "cache_hit_rate": (tokens["cache_read"] / prompt) if prompt else None,
        "cost": cost,
        "subagent_share": (side_cost / cost) if cost else 0.0,
        "prompt_tokens": prompt,
    }


def alerts(project: str | None = None) -> dict:
    """Things worth a look right now. Each item: kind, level (info|warn|danger),
    params for the UI's message template. Ordered most urgent first."""
    tz = _local_tz()
    now = datetime.now(tz)
    today = now.strftime("%Y-%m-%d")
    items: list[dict] = []

    daily = _daily_costs(31, project)
    today_cost = daily.get(today, 0.0)
    history = [v for d, v in daily.items() if d != today and v > 0]
    if today_cost >= 1.0 and len(history) >= 5:
        med = median(history)
        ratio = today_cost / med if med else 0.0
        if ratio >= SPIKE_WARN:
            items.append({"kind": "daily_spike",
                          "level": "danger" if ratio >= SPIKE_DANGER else "warn",
                          "params": {"today": round(today_cost, 2), "median": round(med, 2),
                                     "ratio": round(ratio, 1)}})

    def _sum_days(lo: int, hi: int) -> float:
        return sum(daily.get((now - timedelta(days=k)).strftime("%Y-%m-%d"), 0.0) for k in range(lo, hi))
    this_week, prev_week = _sum_days(0, 7), _sum_days(7, 14)
    if prev_week > 0 and this_week > 0:
        delta = (this_week - prev_week) / prev_week
        if abs(delta) >= WEEK_DELTA_INFO:
            items.append({"kind": "week_pace", "level": "warn" if delta > 0 else "info",
                          "params": {"this": round(this_week, 2), "prev": round(prev_week, 2),
                                     "delta_pct": round(delta * 100, 0)}})

    day_sessions = sessions("today", project=project, sort="cost", page_size=1)
    if day_sessions["items"] and today_cost >= RUNAWAY_MIN_COST:
        top = day_sessions["items"][0]
        share = top["cost"] / today_cost if today_cost else 0.0
        if share >= RUNAWAY_SHARE and day_sessions["total"] > 1:
            items.append({"kind": "runaway_session", "level": "warn",
                          "params": {"name": top["name"], "cost": top["cost"],
                                     "pct": round(share * 100, 0), "session_id": top["session_id"],
                                     "messages": top["messages"]}})

    recent = sessions(None, from_=(now - timedelta(days=1)).strftime("%Y-%m-%d"), project=project,
                      sort="cost", page_size=200)
    bloated = [s for s in recent["items"] if s["ctx_max"] >= CONTEXT_BLOAT_TOKENS]
    if bloated:
        worst = max(bloated, key=lambda s: s["ctx_max"])
        items.append({"kind": "context_bloat", "level": "warn",
                      "params": {"name": worst["name"], "ctx_max": worst["ctx_max"],
                                 "session_id": worst["session_id"], "n": len(bloated)}})

    eff = _month_efficiency(project)
    if eff["cache_hit_rate"] is not None and eff["prompt_tokens"] >= 1_000_000 \
            and eff["cache_hit_rate"] < CACHE_HIT_WARN:
        items.append({"kind": "cache_efficiency", "level": "warn",
                      "params": {"rate": round(eff["cache_hit_rate"] * 100, 1)}})
    if eff["subagent_share"] >= SUBAGENT_SHARE_INFO and eff["cost"] >= RUNAWAY_MIN_COST:
        items.append({"kind": "subagent_share", "level": "info",
                      "params": {"pct": round(eff["subagent_share"] * 100, 0)}})

    ps = pricing_status()
    if ps["stale"]:
        items.append({"kind": "pricing_stale", "level": "warn",
                      "params": {"date": ps["last_verified"] or "?", "days": ps["age_days"] or 0}})

    ret = retention_info()
    missing = queries.savings_report()["timeline"]["months_missing_data"] if not project else 0
    if missing or ret["cleanup_days"] <= DEFAULT_CLEANUP_DAYS:
        items.append({"kind": "retention", "level": "warn" if missing else "info",
                      "params": {"missing": missing, "cleanup_days": ret["cleanup_days"],
                                 "recommended": ret["recommended_days"]}})

    # F26: git push reminders. A git hiccup must never take the strip down.
    try:
        from . import dev_projects
        items.extend(dev_projects.alert_items(project))
    except Exception:
        pass

    order = {"danger": 0, "warn": 1, "info": 2}
    items.sort(key=lambda a: order[a["level"]])
    return {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%S%z"), "items": items,
            "today_cost": round(today_cost, 2), "scope": queries.scope_info(project)}


# ---------------------------------------------------------- weekly report ----

def _week_bounds(weeks_ago: int) -> tuple[datetime, datetime]:
    tz = _local_tz()
    today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    monday = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks_ago)
    return monday, monday + timedelta(days=7)


def _pct(cur: float, prev: float) -> float | None:
    return round((cur - prev) / prev * 100, 1) if prev else None


def weekly_report(weeks_ago: int = 0, project: str | None = None) -> dict:
    """Monday-to-Sunday digest with week-over-week deltas, ready to paste."""
    pricing = load_pricing()
    folder = Folder()
    w_start, w_end = _week_bounds(weeks_ago)
    p_start = w_start - timedelta(days=7)
    clause, cparams = queries.project_clause(project)
    s_iso, e_iso, ps_iso = queries._utc(w_start), queries._utc(w_end), queries._utc(p_start)

    cur = queries._block(queries._model_agg(s_iso, e_iso, clause, cparams), pricing)
    prev = queries._block(queries._model_agg(ps_iso, s_iso, clause, cparams), pricing)
    from_, to_ = w_start.strftime("%Y-%m-%d"), (w_end - timedelta(days=1)).strftime("%Y-%m-%d")
    p_from, p_to = p_start.strftime("%Y-%m-%d"), (w_start - timedelta(days=1)).strftime("%Y-%m-%d")
    cur_sessions = sessions(None, from_, to_, project, sort="cost", page_size=5)
    prev_sessions = sessions(None, p_from, p_to, project, sort="cost", page_size=1)

    projects = queries._merge_projects(queries._project_rows(s_iso, e_iso), pricing, folder)
    if project:
        key = folder.fold(project)
        projects = [p for p in projects if p["path"] == key]
    tools = tools_breakdown(None, project, from_, to_)
    heat = heatmap(None, project, from_, to_)

    daily = {}
    where, params = _where(s_iso, e_iso, project)
    with locked_conn() as conn:
        rows = conn.execute(
            f"SELECT date(ts,'localtime') d, model, model_family f, {TOKEN_SUM} "
            f"FROM events {where} GROUP BY d, model, model_family", params).fetchall()
    for r in rows:
        daily[r["d"]] = daily.get(r["d"], 0.0) + _cost(r, pricing)
    days = [{"day": (w_start + timedelta(days=i)).strftime("%Y-%m-%d"),
             "cost": round(daily.get((w_start + timedelta(days=i)).strftime("%Y-%m-%d"), 0.0), 2)}
            for i in range(7)]
    busiest = max(days, key=lambda d: d["cost"]) if any(d["cost"] for d in days) else None

    info = subscription.plan_info()
    savings = queries.savings_report()["current"] if (info["comparable"] and not project) else None

    return {
        "week": {"from": from_, "to": to_, "weeks_ago": weeks_ago,
                 "is_current": weeks_ago == 0, "generated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")},
        "scope": queries.scope_info(project),
        "totals": {
            "cost": cur["cost"]["total"], "tokens": cur["tokens"], "events": cur["events"],
            "sessions": cur_sessions["total"], "efficiency": cur.get("efficiency"),
        },
        "previous": {
            "cost": prev["cost"]["total"], "tokens": prev["tokens"]["total"], "events": prev["events"],
            "sessions": prev_sessions["total"],
        },
        "delta_pct": {
            "cost": _pct(cur["cost"]["total"], prev["cost"]["total"]),
            "tokens": _pct(cur["tokens"]["total"], prev["tokens"]["total"]),
            "events": _pct(cur["events"], prev["events"]),
            "sessions": _pct(cur_sessions["total"], prev_sessions["total"]),
        },
        "days": days,
        "busiest_day": busiest,
        "top_projects": [{k: p[k] for k in ("path", "name", "tokens", "cost", "events")} for p in projects[:5]],
        "top_models": cur["by_model"][:5],
        "top_sessions": cur_sessions["items"],
        "tools": tools["tools"][:5],
        "subagents": tools["subagents"],
        "peak_slot": heat["peak"],
        "savings": savings,
    }


_MD = {
    "zh": {
        "title": "TokenScope 周报 · {from} ~ {to}",
        "scope": "范围:{name}",
        "headline": "本周虚拟成本 **{cost}**(上周 {prev},{delta}),{events} 次调用 · {sessions} 个会话 · {tokens} tokens。",
        "days": "### 逐日", "day_row": "| {day} | {cost} |", "day_head": "| 日期 | 虚拟成本 |\n|---|---|",
        "busiest": "最忙的一天:{day}({cost})。高峰时段:{dow} {hour}:00。",
        "projects": "### 项目 Top 5", "proj_head": "| 项目 | 成本 | 调用 | tokens |\n|---|---|---|---|",
        "models": "### 模型 Top 5", "model_head": "| 模型 | 调用 | 成本 | 占比 |\n|---|---|---|---|",
        "sessions": "### 最贵的 5 个会话", "sess_head": "| 项目 | 开始 | 消息 | 峰值上下文 | 成本 |\n|---|---|---|---|---|",
        "tools": "### 工具调用", "tool_head": "| 工具 | 次数 | 成本 |\n|---|---|---|",
        "subagents": "子代理占本周成本 {pct}%({cost})。",
        "eff": "缓存命中率 {rate}%,缓存省下约 {saved};每千 output token 成本 {per1k}。",
        "savings": "本月订阅:{plan} 月费 ${fee},月初至今按 API 价 ${api},净省 ${saved}。",
        "footer": "_金额为按 API 牌价折算的虚拟成本(美元);订阅制下实际为固定月费。由 TokenScope 生成于 {at}。_",
        "dows": ["周日", "周一", "周二", "周三", "周四", "周五", "周六"],
        "none": "(本周没有记录)",
    },
    "en": {
        "title": "TokenScope weekly · {from} – {to}",
        "scope": "Scope: {name}",
        "headline": "Virtual cost this week **{cost}** (last week {prev}, {delta}), {events} calls · {sessions} sessions · {tokens} tokens.",
        "days": "### By day", "day_row": "| {day} | {cost} |", "day_head": "| Day | Virtual cost |\n|---|---|",
        "busiest": "Busiest day: {day} ({cost}). Peak slot: {dow} {hour}:00.",
        "projects": "### Top 5 projects", "proj_head": "| Project | Cost | Calls | Tokens |\n|---|---|---|---|",
        "models": "### Top 5 models", "model_head": "| Model | Calls | Cost | Share |\n|---|---|---|---|",
        "sessions": "### 5 most expensive sessions", "sess_head": "| Project | Started | Msgs | Peak context | Cost |\n|---|---|---|---|---|",
        "tools": "### Tool calls", "tool_head": "| Tool | Calls | Cost |\n|---|---|---|",
        "subagents": "Subagents were {pct}% of this week's cost ({cost}).",
        "eff": "Cache hit rate {rate}%, caching saved about {saved}; cost per 1K output tokens {per1k}.",
        "savings": "Subscription this month: {plan} at ${fee}/mo, ${api} at API price month-to-date, net saving ${saved}.",
        "footer": "_Amounts are virtual costs at API list price (USD); a subscription bills a flat fee. Generated by TokenScope at {at}._",
        "dows": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "none": "(no records this week)",
    },
}


def _fmt_tokens(n: int) -> str:
    if n >= 1e9:
        return f"{n / 1e9:.1f}B"
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.1f}K"
    return str(n)


def _usd(n: float) -> str:
    return f"${n:,.2f}"


def render_weekly_markdown(report: dict, lang: str = "zh") -> str:
    s = _MD.get(lang, _MD["en"])
    t, d = report["totals"], report["delta_pct"]
    delta = f"{d['cost']:+.0f}%" if d["cost"] is not None else "—"
    lines = [f"# {s['title'].format(**report['week'])}", ""]
    if report["scope"]:
        lines += [s["scope"].format(name=report["scope"]["name"]), ""]
    if t["events"] == 0:
        lines += [s["none"], "", s["footer"].format(at=report["week"]["generated_at"])]
        return "\n".join(lines)
    lines += [s["headline"].format(cost=_usd(t["cost"]), prev=_usd(report["previous"]["cost"]), delta=delta,
                                   events=f"{t['events']:,}", sessions=t["sessions"],
                                   tokens=_fmt_tokens(t["tokens"]["total"])), ""]
    lines += [s["days"], s["day_head"]]
    lines += [s["day_row"].format(day=x["day"], cost=_usd(x["cost"])) for x in report["days"]]
    if report["busiest_day"]:
        peak = report["peak_slot"]
        lines += ["", s["busiest"].format(day=report["busiest_day"]["day"], cost=_usd(report["busiest_day"]["cost"]),
                                          dow=s["dows"][peak["dow"]] if peak else "—",
                                          hour=f"{peak['hour']:02d}" if peak else "—")]
    lines += ["", s["projects"], s["proj_head"]]
    lines += [f"| {p['name']} | {_usd(p['cost'])} | {p['events']:,} | {_fmt_tokens(p['tokens'])} |"
              for p in report["top_projects"]]
    lines += ["", s["models"], s["model_head"]]
    lines += [f"| {m['model']} | {m['events']:,} | {_usd(m['cost'])} | {m['cost_share'] * 100:.1f}% |"
              for m in report["top_models"]]
    lines += ["", s["sessions"], s["sess_head"]]
    lines += [f"| {x['name']} | {x['first_ts'][:16].replace('T', ' ')} | {x['messages']} | "
              f"{_fmt_tokens(x['ctx_max'])} | {_usd(x['cost'])} |" for x in report["top_sessions"]]
    if report["tools"]:
        lines += ["", s["tools"], s["tool_head"]]
        lines += [f"| {x['name']} | {x['calls']:,} | {_usd(x['cost'])} |" for x in report["tools"]]
    sub = report["subagents"]
    if sub["events"]:
        lines += ["", s["subagents"].format(pct=f"{sub['cost_share'] * 100:.0f}", cost=_usd(sub["cost"]))]
    eff = t.get("efficiency") or {}
    if eff.get("cache_hit_rate") is not None:
        lines += ["", s["eff"].format(rate=f"{eff['cache_hit_rate'] * 100:.1f}", saved=_usd(eff["cache_saved"]),
                                      per1k=_usd(eff["cost_per_1k_output"] or 0))]
    if report["savings"]:
        sv = report["savings"]
        lines += ["", s["savings"].format(plan=sv["plan_label"], fee=f"{sv['monthly_fee']:,.0f}",
                                          api=f"{sv['api_cost_mtd']:,.2f}", saved=f"{sv['saved']:,.2f}")]
    lines += ["", s["footer"].format(at=report["week"]["generated_at"])]
    return "\n".join(lines)
