"""Aggregate queries. Timestamps are stored as UTC ISO ("...Z").

Range boundaries ("today", "this month") are computed in the server's local
timezone and converted to UTC; per-day bucketing uses SQLite's
date(ts,'localtime') so both mechanisms agree.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .db import locked_conn
from .pricing import cost_of, load_pricing

TOKEN_SUM = ("SUM(input_tokens) i, SUM(output_tokens) o, "
             "SUM(cache_write_tokens) w, SUM(cache_read_tokens) r")


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_range(range_key: str | None, from_: str | None = None, to_: str | None = None):
    """Return (start_iso, end_iso) UTC bounds, either possibly None."""
    local_tz = datetime.now().astimezone().tzinfo
    today = datetime.now(local_tz).replace(hour=0, minute=0, second=0, microsecond=0)
    if from_ or to_:
        start = datetime.strptime(from_, "%Y-%m-%d").replace(tzinfo=local_tz) if from_ else None
        end = (datetime.strptime(to_, "%Y-%m-%d").replace(tzinfo=local_tz) + timedelta(days=1)) if to_ else None
        return (_utc(start) if start else None, _utc(end) if end else None)
    match range_key:
        case "today":
            return _utc(today), None
        case "7d":
            return _utc(today - timedelta(days=6)), None
        case "30d":
            return _utc(today - timedelta(days=29)), None
        case "month":
            return _utc(today.replace(day=1)), None
        case _:  # "all" or None
            return None, None


def _where(start: str | None, end: str | None, extra: str = "") -> tuple[str, list]:
    clauses, params = [], []
    if start:
        clauses.append("ts >= ?")
        params.append(start)
    if end:
        clauses.append("ts < ?")
        params.append(end)
    if extra:
        clauses.append(extra)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def _family_agg(start, end, extra="", extra_params=()):
    where, params = _where(start, end, extra)
    params = [*params, *extra_params]
    with locked_conn() as conn:
        rows = conn.execute(
            f"SELECT model_family f, {TOKEN_SUM}, COUNT(*) n FROM events {where} GROUP BY model_family",
            params,
        ).fetchall()
    return rows


def _block(rows, pricing) -> dict:
    tokens = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
    cost_by_family, events = {}, 0
    for row in rows:
        tokens["input"] += row["i"] or 0
        tokens["output"] += row["o"] or 0
        tokens["cache_write"] += row["w"] or 0
        tokens["cache_read"] += row["r"] or 0
        events += row["n"]
        cost_by_family[row["f"]] = cost_of(row["f"], row["i"] or 0, row["o"] or 0,
                                           row["w"] or 0, row["r"] or 0, pricing)
    tokens["total"] = sum(v for k, v in tokens.items() if k != "total")
    return {"tokens": tokens,
            "cost": {"total": round(sum(cost_by_family.values()), 4),
                     "by_family": {k: round(v, 4) for k, v in cost_by_family.items()}},
            "events": events}


def summary_cards() -> dict:
    pricing = load_pricing()
    t_start, _ = resolve_range("today")
    m_start, _ = resolve_range("month")
    return {"today": _block(_family_agg(t_start, None), pricing),
            "month": _block(_family_agg(m_start, None), pricing)}


def trend(granularity: str = "day", days: int = 30, months: int = 12) -> dict:
    pricing = load_pricing()
    local_tz = datetime.now().astimezone().tzinfo
    now_local = datetime.now(local_tz)
    if granularity == "month":
        bucket_expr = "strftime('%Y-%m', ts, 'localtime')"
        first = (now_local.replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)
        start = _utc(first.replace(hour=0, minute=0, second=0, microsecond=0))
        buckets = []
        y, m = first.year, first.month
        for _ in range(months):
            buckets.append(f"{y:04d}-{m:02d}")
            m += 1
            if m > 12:
                y, m = y + 1, 1
    else:
        bucket_expr = "date(ts, 'localtime')"
        first = now_local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
        start = _utc(first)
        buckets = [(first + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]

    with locked_conn() as conn:
        rows = conn.execute(
            f"SELECT {bucket_expr} b, model_family f, {TOKEN_SUM} "
            f"FROM events WHERE ts >= ? GROUP BY b, f", (start,),
        ).fetchall()

    by_bucket: dict[str, dict] = {
        b: {"bucket": b, "input": 0, "output": 0, "cache_write": 0, "cache_read": 0, "cost": 0.0}
        for b in buckets
    }
    for row in rows:
        p = by_bucket.get(row["b"])
        if not p:
            continue
        p["input"] += row["i"] or 0
        p["output"] += row["o"] or 0
        p["cache_write"] += row["w"] or 0
        p["cache_read"] += row["r"] or 0
        p["cost"] += cost_of(row["f"], row["i"] or 0, row["o"] or 0, row["w"] or 0, row["r"] or 0, pricing)
    for p in by_bucket.values():
        p["cost"] = round(p["cost"], 4)
    return {"points": list(by_bucket.values())}


def models_distribution(range_key: str | None) -> dict:
    pricing = load_pricing()
    start, end = resolve_range(range_key)
    rows = _family_agg(start, end)
    items = []
    for row in rows:
        tokens = (row["i"] or 0) + (row["o"] or 0) + (row["w"] or 0) + (row["r"] or 0)
        items.append({"family": row["f"], "tokens": tokens, "events": row["n"],
                      "cost": round(cost_of(row["f"], row["i"] or 0, row["o"] or 0,
                                            row["w"] or 0, row["r"] or 0, pricing), 4)})
    total_tokens = sum(x["tokens"] for x in items) or 1
    total_cost = sum(x["cost"] for x in items) or 1
    for x in items:
        x["token_share"] = round(x["tokens"] / total_tokens, 4)
        x["cost_share"] = round(x["cost"] / total_cost, 4)
    items.sort(key=lambda x: -x["tokens"])
    return {"items": items,
            "totals": {"tokens": sum(x["tokens"] for x in items),
                       "cost": round(sum(x["cost"] for x in items), 4)}}


def _project_rows(start, end):
    where, params = _where(start, end)
    with locked_conn() as conn:
        return conn.execute(
            f"SELECT project_path p, MAX(project_name) name, model_family f, {TOKEN_SUM}, "
            f"COUNT(*) n, COUNT(DISTINCT session_id) s, MAX(ts) last_ts, MIN(ts) first_ts "
            f"FROM events {where} GROUP BY project_path, model_family",
            params,
        ).fetchall()


def _merge_projects(rows, pricing):
    projects: dict[str, dict] = {}
    for row in rows:
        pr = projects.setdefault(row["p"], {
            "path": row["p"], "name": row["name"], "tokens": 0, "cost": 0.0,
            "events": 0, "sessions": 0, "last_active": row["last_ts"], "first_seen": row["first_ts"],
            "tokens_detail": {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0},
        })
        pr["tokens"] += (row["i"] or 0) + (row["o"] or 0) + (row["w"] or 0) + (row["r"] or 0)
        pr["tokens_detail"]["input"] += row["i"] or 0
        pr["tokens_detail"]["output"] += row["o"] or 0
        pr["tokens_detail"]["cache_write"] += row["w"] or 0
        pr["tokens_detail"]["cache_read"] += row["r"] or 0
        pr["cost"] += cost_of(row["f"], row["i"] or 0, row["o"] or 0, row["w"] or 0, row["r"] or 0, pricing)
        pr["events"] += row["n"]
        pr["sessions"] += row["s"]
        pr["last_active"] = max(pr["last_active"], row["last_ts"])
        pr["first_seen"] = min(pr["first_seen"], row["first_ts"])
    # Disambiguate duplicate display names with parent/basename.
    by_name: dict[str, list] = {}
    for pr in projects.values():
        by_name.setdefault(pr["name"], []).append(pr)
    for group in by_name.values():
        if len(group) > 1:
            for pr in group:
                parts = pr["path"].rstrip("/").split("/")
                pr["name"] = "/".join(parts[-2:]) if len(parts) >= 2 else pr["name"]
    for pr in projects.values():
        pr["cost"] = round(pr["cost"], 4)
    return sorted(projects.values(), key=lambda x: -x["cost"])


def projects_top(range_key: str | None, limit: int = 10) -> dict:
    pricing = load_pricing()
    start, end = resolve_range(range_key)
    items = _merge_projects(_project_rows(start, end), pricing)
    return {"items": [{k: pr[k] for k in ("path", "name", "tokens", "cost")} for pr in items[:limit]]}


def projects_list(range_key: str | None) -> dict:
    pricing = load_pricing()
    start, end = resolve_range(range_key)
    items = _merge_projects(_project_rows(start, end), pricing)
    # 30-day daily token sparkline per project, one query for all.
    spark_start, _ = resolve_range("30d")
    with locked_conn() as conn:
        rows = conn.execute(
            "SELECT project_path p, date(ts,'localtime') d, "
            "SUM(input_tokens + output_tokens + cache_write_tokens + cache_read_tokens) t "
            "FROM events WHERE ts >= ? GROUP BY p, d", (spark_start,),
        ).fetchall()
    spark: dict[str, dict[str, int]] = {}
    for row in rows:
        spark.setdefault(row["p"], {})[row["d"]] = row["t"] or 0
    local_tz = datetime.now().astimezone().tzinfo
    today = datetime.now(local_tz)
    day_keys = [(today - timedelta(days=29 - i)).strftime("%Y-%m-%d") for i in range(30)]
    for pr in items:
        days_map = spark.get(pr["path"], {})
        pr["spark"] = [{"day": d[5:], "tokens": days_map.get(d, 0)} for d in day_keys]
    return {"items": items}


def project_detail(path: str) -> dict | None:
    pricing = load_pricing()
    rows = [r for r in _project_rows(None, None) if r["p"] == path]
    if not rows:
        return None
    pr = _merge_projects(rows, pricing)[0]
    # this month vs previous month token delta
    local_tz = datetime.now().astimezone().tzinfo
    today = datetime.now(local_tz).replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today.replace(day=1)
    prev_start = (month_start - timedelta(days=1)).replace(day=1)

    def _tokens_between(a, b):
        with locked_conn() as conn:
            row = conn.execute(
                "SELECT SUM(input_tokens + output_tokens + cache_write_tokens + cache_read_tokens) t "
                "FROM events WHERE project_path = ? AND ts >= ? AND ts < ?",
                (path, _utc(a), _utc(b)),
            ).fetchone()
        return row["t"] or 0

    cur = _tokens_between(month_start, today + timedelta(days=1))
    prev = _tokens_between(prev_start, month_start)
    delta_pct = round((cur - prev) / prev * 100, 1) if prev else None
    pr["month_tokens"] = cur
    pr["prev_month_tokens"] = prev
    pr["tokens_delta_pct"] = delta_pct
    pr["avg_cost_per_event"] = round(pr["cost"] / pr["events"], 4) if pr["events"] else 0.0
    return pr


def logs(from_: str | None, to_: str | None, model_family: str | None,
         project: str | None, q: str | None, page: int, page_size: int):
    pricing = load_pricing()
    start, end = resolve_range(None, from_, to_)
    clauses, params = [], []
    if start:
        clauses.append("ts >= ?"); params.append(start)
    if end:
        clauses.append("ts < ?"); params.append(end)
    if model_family:
        clauses.append("model_family = ?"); params.append(model_family)
    if project:
        clauses.append("project_path = ?"); params.append(project)
    if q:
        clauses.append("(project_name LIKE ? OR session_id LIKE ? OR message_id LIKE ?)")
        like = f"%{q}%"
        params += [like, like, like]
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with locked_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) c FROM events {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT ts, model, model_family, project_name, project_path, session_id, "
            f"input_tokens, output_tokens, cache_write_tokens, cache_read_tokens "
            f"FROM events {where} ORDER BY ts DESC LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    items = [_log_item(r, pricing) for r in rows]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def _log_item(r, pricing) -> dict:
    return {
        "ts": r["ts"], "model": r["model"], "model_family": r["model_family"],
        "project_name": r["project_name"], "project_path": r["project_path"],
        "session_id": r["session_id"],
        "input": r["input_tokens"], "output": r["output_tokens"],
        "cache_write": r["cache_write_tokens"], "cache_read": r["cache_read_tokens"],
        "cost": round(cost_of(r["model_family"], r["input_tokens"], r["output_tokens"],
                              r["cache_write_tokens"], r["cache_read_tokens"], pricing), 6),
    }


def logs_iter(from_: str | None, to_: str | None, model_family: str | None,
              project: str | None, q: str | None):
    """Yield all matching log rows (for CSV export)."""
    page, page_size = 1, 2000
    while True:
        chunk = logs(from_, to_, model_family, project, q, page, page_size)
        yield from chunk["items"]
        if page * page_size >= chunk["total"]:
            break
        page += 1
