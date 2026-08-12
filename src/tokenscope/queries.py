"""Aggregate queries. Timestamps are stored as UTC ISO ("...Z").

Range boundaries ("today", "this month") are computed in the server's local
timezone and converted to UTC; per-day bucketing uses SQLite's
date(ts,'localtime') so both mechanisms agree.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import subscription
from .db import locked_conn
from .pricing import cost_of_model, has_model_override, load_pricing, rates_for_model
from .projects import Folder

TOKEN_SUM = ("SUM(input_tokens) i, SUM(output_tokens) o, "
             "SUM(cache_write_tokens) w, SUM(cache_read_tokens) r")

# Every aggregate groups by exact model (not just family) so per-model pricing
# overrides are honoured and the UI can show which model actually ran.
GROUP_COLS = "model, model_family f"


def _row_cost(row, pricing) -> float:
    return cost_of_model(row["model"], row["f"], row["i"] or 0, row["o"] or 0,
                         row["w"] or 0, row["r"] or 0, pricing)


def _row_tokens(row) -> int:
    return (row["i"] or 0) + (row["o"] or 0) + (row["w"] or 0) + (row["r"] or 0)


def _blank_detail() -> dict:
    return {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}


def _add_detail(dst: dict, row) -> None:
    dst["input"] += row["i"] or 0
    dst["output"] += row["o"] or 0
    dst["cache_write"] += row["w"] or 0
    dst["cache_read"] += row["r"] or 0


def _model_bucket(store: dict, row, pricing) -> dict:
    """Accumulate one grouped row into `store` keyed by exact model id."""
    entry = store.setdefault(row["model"], {
        "model": row["model"], "family": row["f"], "tokens": 0, "cost": 0.0,
        "events": 0, "tokens_detail": _blank_detail(),
    })
    entry["tokens"] += _row_tokens(row)
    entry["cost"] += _row_cost(row, pricing)
    entry["events"] += row["n"] if "n" in row.keys() else 0
    _add_detail(entry["tokens_detail"], row)
    return entry


def _finalize_models(store: dict, pricing) -> list[dict]:
    """Round, attach unit rates, and compute shares. Sorted by cost desc."""
    items = list(store.values())
    total_tokens = sum(x["tokens"] for x in items) or 1
    total_cost = sum(x["cost"] for x in items) or 1
    for x in items:
        rates = rates_for_model(x["model"], x["family"], pricing)
        x["rates"] = {k: round(v, 4) for k, v in rates.items()}
        x["priced_by"] = "model" if has_model_override(x["model"], pricing) else "family"
        x["token_share"] = round(x["tokens"] / total_tokens, 4)
        x["cost_share"] = round(x["cost"] / total_cost, 4)
        x["avg_cost_per_call"] = round(x["cost"] / x["events"], 6) if x["events"] else 0.0
        x["cost"] = round(x["cost"], 4)
    items.sort(key=lambda x: (-x["cost"], -x["tokens"]))
    return items


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


def project_clause(project: str | None) -> tuple[str, list]:
    """SQL fragment restricting a query to one folded project.

    `project` may be the folded key or any raw cwd under it — both resolve to
    the same set of cwds, so a link built from a session directory works.
    An unknown project falls through to `_cwds_for`'s [project] fallback and
    therefore matches nothing: a typo must return zero, never the whole
    account silently.
    """
    if not project:
        return "", []
    cwds = _cwds_for(project)
    return f"project_path IN ({','.join('?' * len(cwds))})", list(cwds)


def _model_agg(start, end, extra="", extra_params=()):
    where, params = _where(start, end, extra)
    params = [*params, *extra_params]
    with locked_conn() as conn:
        rows = conn.execute(
            f"SELECT {GROUP_COLS}, {TOKEN_SUM}, COUNT(*) n FROM events {where} "
            f"GROUP BY model, model_family",
            params,
        ).fetchall()
    return rows


def _block(rows, pricing) -> dict:
    tokens = _blank_detail()
    cost_by_family: dict[str, float] = {}
    by_model: dict[str, dict] = {}
    events = 0
    for row in rows:
        _add_detail(tokens, row)
        events += row["n"]
        cost_by_family[row["f"]] = cost_by_family.get(row["f"], 0.0) + _row_cost(row, pricing)
        _model_bucket(by_model, row, pricing)
    tokens["total"] = sum(v for k, v in tokens.items() if k != "total")
    return {"tokens": tokens,
            "cost": {"total": round(sum(cost_by_family.values()), 4),
                     "by_family": {k: round(v, 4) for k, v in cost_by_family.items()}},
            "events": events,
            "by_model": _finalize_models(by_model, pricing)}


def summary_cards(project: str | None = None) -> dict:
    """Today/month totals, optionally narrowed to one project.

    `savings` stays account-wide even when scoped — one monthly fee covers the
    whole account, so "this project saved you $X" would be meaningless. The
    per-project framing lives in `project_share()` instead.
    """
    pricing = load_pricing()
    clause, cparams = project_clause(project)
    t_start, _ = resolve_range("today")
    m_start, _ = resolve_range("month")
    info = subscription.plan_info()
    account_month = _block(_model_agg(m_start, None), pricing)
    return {"today": _block(_model_agg(t_start, None, clause, cparams), pricing),
            "month": _block(_model_agg(m_start, None, clause, cparams), pricing),
            "subscription": info,
            "savings": subscription.savings(account_month["cost"]["total"], info),
            "scope": scope_info(project)}


def trend(granularity: str = "day", days: int = 30, months: int = 12,
          project: str | None = None) -> dict:
    pricing = load_pricing()
    clause, cparams = project_clause(project)
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
            f"SELECT {bucket_expr} b, {GROUP_COLS}, {TOKEN_SUM} "
            f"FROM events WHERE ts >= ?{' AND ' + clause if clause else ''} "
            f"GROUP BY b, model, model_family", (start, *cparams),
        ).fetchall()

    by_bucket: dict[str, dict] = {
        b: {"bucket": b, "input": 0, "output": 0, "cache_write": 0, "cache_read": 0,
            "cost": 0.0, "cost_by_model": {}}
        for b in buckets
    }
    for row in rows:
        p = by_bucket.get(row["b"])
        if not p:
            continue
        _add_detail(p, row)
        cost = _row_cost(row, pricing)
        p["cost"] += cost
        p["cost_by_model"][row["model"]] = round(
            p["cost_by_model"].get(row["model"], 0.0) + cost, 4)
    for p in by_bucket.values():
        p["cost"] = round(p["cost"], 4)
    return {"points": list(by_bucket.values())}


def models_distribution(range_key: str | None, project: str | None = None) -> dict:
    """`items` rolls up to family (donut); `models` is the exact model breakdown."""
    pricing = load_pricing()
    start, end = resolve_range(range_key)
    clause, cparams = project_clause(project)
    rows = _model_agg(start, end, clause, cparams)

    fams: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    for row in rows:
        fam = fams.setdefault(row["f"], {"family": row["f"], "tokens": 0, "events": 0,
                                         "cost": 0.0, "models": 0})
        fam["tokens"] += _row_tokens(row)
        fam["events"] += row["n"]
        fam["cost"] += _row_cost(row, pricing)
        _model_bucket(by_model, row, pricing)

    items = list(fams.values())
    for x in items:
        x["cost"] = round(x["cost"], 4)
    models = _finalize_models(by_model, pricing)
    for m in models:
        fams[m["family"]]["models"] += 1

    total_tokens = sum(x["tokens"] for x in items) or 1
    total_cost = sum(x["cost"] for x in items) or 1
    for x in items:
        x["token_share"] = round(x["tokens"] / total_tokens, 4)
        x["cost_share"] = round(x["cost"] / total_cost, 4)
    items.sort(key=lambda x: -x["tokens"])

    return {"items": items, "models": models,
            "totals": {"tokens": sum(x["tokens"] for x in items),
                       "cost": round(sum(x["cost"] for x in items), 4),
                       "events": sum(x["events"] for x in items),
                       "model_count": len(models)}}


def _project_rows(start, end):
    where, params = _where(start, end)
    with locked_conn() as conn:
        return conn.execute(
            f"SELECT project_path p, MAX(project_name) name, {GROUP_COLS}, {TOKEN_SUM}, "
            f"COUNT(*) n, MAX(ts) last_ts, MIN(ts) first_ts "
            f"FROM events {where} GROUP BY project_path, model, model_family",
            params,
        ).fetchall()


def _session_pairs(start, end):
    """(project_path, session_id) pairs — counted after folding, since one
    session spans several models and would be double-counted per group."""
    where, params = _where(start, end)
    with locked_conn() as conn:
        return conn.execute(
            f"SELECT DISTINCT project_path p, session_id s FROM events {where}", params,
        ).fetchall()


def _merge_projects(rows, pricing, folder: Folder | None = None, session_rows=None):
    folder = folder or Folder()
    projects: dict[str, dict] = {}
    for row in rows:
        key = folder.fold(row["p"])
        pr = projects.setdefault(key, {
            "path": key, "name": folder.name(key), "tokens": 0, "cost": 0.0,
            "events": 0, "sessions": 0, "last_active": row["last_ts"], "first_seen": row["first_ts"],
            "tokens_detail": _blank_detail(),
            "cwds": set(), "_models": {},
        })
        pr["cwds"].add(row["p"])
        pr["tokens"] += _row_tokens(row)
        _add_detail(pr["tokens_detail"], row)
        pr["cost"] += _row_cost(row, pricing)
        _model_bucket(pr["_models"], row, pricing)
        pr["events"] += row["n"]
        pr["last_active"] = max(pr["last_active"], row["last_ts"])
        pr["first_seen"] = min(pr["first_seen"], row["first_ts"])

    if session_rows is not None:
        sessions: dict[str, set] = {}
        for row in session_rows:
            if row["s"]:
                sessions.setdefault(folder.fold(row["p"]), set()).add(row["s"])
        for key, pr in projects.items():
            pr["sessions"] = len(sessions.get(key, ()))

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
        pr["cwds"] = sorted(pr["cwds"])
        pr["by_model"] = _finalize_models(pr.pop("_models"), pricing)
    return sorted(projects.values(), key=lambda x: -x["cost"])


def projects_top(range_key: str | None, limit: int = 10) -> dict:
    pricing = load_pricing()
    start, end = resolve_range(range_key)
    items = _merge_projects(_project_rows(start, end), pricing)
    return {"items": [{k: pr[k] for k in ("path", "name", "tokens", "cost")} for pr in items[:limit]]}


def projects_list(range_key: str | None) -> dict:
    pricing = load_pricing()
    folder = Folder()
    start, end = resolve_range(range_key)
    items = _merge_projects(_project_rows(start, end), pricing, folder,
                            _session_pairs(start, end))
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
        days = spark.setdefault(folder.fold(row["p"]), {})
        days[row["d"]] = days.get(row["d"], 0) + (row["t"] or 0)
    local_tz = datetime.now().astimezone().tzinfo
    now = datetime.now(local_tz)
    day_keys = [(now - timedelta(days=29 - i)).strftime("%Y-%m-%d") for i in range(30)]
    for pr in items:
        days_map = spark.get(pr["path"], {})
        pr["spark"] = [{"day": d[5:], "tokens": days_map.get(d, 0)} for d in day_keys]

    # Today's figures ride along regardless of the selected range, so "what is
    # burning right now" stays visible while looking at a 30-day view.
    today = _today_by_project(pricing, folder)
    for pr in items:
        pr["today"] = today.get(pr["path"]) or {"tokens": 0, "cost": 0.0, "events": 0}
    return {"items": items}


def _today_by_project(pricing, folder: Folder) -> dict[str, dict]:
    """Today's tokens/cost/calls per folded project — one query for all."""
    t_start, _ = resolve_range("today")
    where, params = _where(t_start, None)
    with locked_conn() as conn:
        rows = conn.execute(
            f"SELECT project_path p, {GROUP_COLS}, {TOKEN_SUM}, COUNT(*) n "
            f"FROM events {where} GROUP BY project_path, model, model_family",
            params,
        ).fetchall()
    out: dict[str, dict] = {}
    for row in rows:
        e = out.setdefault(folder.fold(row["p"]), {"tokens": 0, "cost": 0.0, "events": 0})
        e["tokens"] += _row_tokens(row)
        e["cost"] += _row_cost(row, pricing)
        e["events"] += row["n"]
    for e in out.values():
        e["cost"] = round(e["cost"], 4)
    return out


def project_detail(path: str) -> dict | None:
    pricing = load_pricing()
    folder = Folder()
    key = folder.fold(path)
    rows = [r for r in _project_rows(None, None) if folder.fold(r["p"]) == key]
    if not rows:
        return None
    sess = [r for r in _session_pairs(None, None) if folder.fold(r["p"]) == key]
    pr = _merge_projects(rows, pricing, folder, sess)[0]
    cwds = pr["cwds"]
    # this month vs previous month token delta
    local_tz = datetime.now().astimezone().tzinfo
    today = datetime.now(local_tz).replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today.replace(day=1)
    prev_start = (month_start - timedelta(days=1)).replace(day=1)

    def _tokens_between(a, b):
        placeholders = ",".join("?" * len(cwds))
        with locked_conn() as conn:
            row = conn.execute(
                "SELECT SUM(input_tokens + output_tokens + cache_write_tokens + cache_read_tokens) t "
                f"FROM events WHERE project_path IN ({placeholders}) AND ts >= ? AND ts < ?",
                (*cwds, _utc(a), _utc(b)),
            ).fetchone()
        return row["t"] or 0

    cur = _tokens_between(month_start, today + timedelta(days=1))
    prev = _tokens_between(prev_start, month_start)
    delta_pct = round((cur - prev) / prev * 100, 1) if prev else None
    pr["month_tokens"] = cur
    pr["prev_month_tokens"] = prev
    pr["tokens_delta_pct"] = delta_pct
    pr["avg_cost_per_event"] = round(pr["cost"] / pr["events"], 4) if pr["events"] else 0.0
    pr["today"] = (_today_by_project(pricing, folder).get(key)
                   or {"tokens": 0, "cost": 0.0, "events": 0})
    return pr


def _cwds_for(project: str) -> list[str]:
    """Every raw cwd that folds into `project` (which may itself be a raw cwd)."""
    folder = Folder()
    key = folder.fold(project)
    with locked_conn() as conn:
        rows = conn.execute("SELECT DISTINCT project_path p FROM events").fetchall()
    return [r["p"] for r in rows if folder.fold(r["p"]) == key] or [project]


def logs(from_: str | None, to_: str | None, model_family: str | None,
         project: str | None, q: str | None, page: int, page_size: int,
         model: str | None = None):
    pricing = load_pricing()
    start, end = resolve_range(None, from_, to_)
    clauses, params = [], []
    if start:
        clauses.append("ts >= ?"); params.append(start)
    if end:
        clauses.append("ts < ?"); params.append(end)
    if model_family:
        clauses.append("model_family = ?"); params.append(model_family)
    if model:
        clauses.append("model = ?"); params.append(model)
    if project:
        cwds = _cwds_for(project)
        clauses.append(f"project_path IN ({','.join('?' * len(cwds))})")
        params += cwds
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
        "cost": round(cost_of_model(r["model"], r["model_family"],
                                    r["input_tokens"], r["output_tokens"],
                                    r["cache_write_tokens"], r["cache_read_tokens"],
                                    pricing), 6),
    }


def scope_info(project: str | None) -> dict | None:
    """Resolve a raw path/key into the project the dashboard is scoped to."""
    if not project:
        return None
    folder = Folder()
    key = folder.fold(project)
    cwds = _cwds_for(project)
    with locked_conn() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) n FROM events WHERE project_path IN ({','.join('?' * len(cwds))})",
            cwds,
        ).fetchone()
    return {"project": key, "name": folder.name(key), "cwds": sorted(cwds),
            "events": row["n"], "known": bool(row["n"])}


def project_share(project: str) -> dict:
    """What one project cost this month, against the account and the plan fee.

    Replaces the savings panel when scoped: a subscription fee buys the whole
    account, so the honest per-project question is "how much of it did this
    project use up", not "how much did this project save".
    """
    pricing = load_pricing()
    info = subscription.plan_info()
    m_start, _ = resolve_range("month")
    clause, cparams = project_clause(project)

    scoped = _block(_model_agg(m_start, None, clause, cparams), pricing)
    account = _block(_model_agg(m_start, None), pricing)
    scoped_cost = scoped["cost"]["total"]
    account_cost = account["cost"]["total"]
    fee = float(info["monthly_usd"])

    return {
        "scope": scope_info(project),
        "month_cost": round(scoped_cost, 2),
        "month_tokens": scoped["tokens"]["total"],
        "events": scoped["events"],
        "account_month_cost": round(account_cost, 2),
        "cost_share": round(scoped_cost / account_cost, 4) if account_cost else 0.0,
        "by_model": scoped["by_model"],
        # Only meaningful on a flat-fee plan; false on pay-as-you-go API billing.
        "comparable": info["comparable"],
        "plan_label": info["label"],
        "monthly_fee": round(fee, 2),
        # Share of the fee this project consumed, at API-equivalent price.
        "pct_of_fee": round(scoped_cost / fee * 100, 1) if fee else None,
    }


def monthly_costs() -> list[dict]:
    """Virtual API cost per calendar month, all history, local time."""
    pricing = load_pricing()
    with locked_conn() as conn:
        rows = conn.execute(
            f"SELECT strftime('%Y-%m', ts, 'localtime') b, {GROUP_COLS}, {TOKEN_SUM}, "
            f"COUNT(*) n FROM events GROUP BY b, model, model_family",
        ).fetchall()
    by_month: dict[str, dict] = {}
    for row in rows:
        m = by_month.setdefault(row["b"], {"month": row["b"], "cost": 0.0,
                                           "tokens": 0, "events": 0})
        m["cost"] += _row_cost(row, pricing)
        m["tokens"] += _row_tokens(row)
        m["events"] += row["n"]
    for m in by_month.values():
        m["cost"] = round(m["cost"], 4)
    return sorted(by_month.values(), key=lambda x: x["month"])


def savings_report() -> dict:
    """Plan info + this month's savings + the month-by-month cumulative total."""
    info = subscription.plan_info()
    months = monthly_costs()
    this_month = datetime.now().astimezone().strftime("%Y-%m")
    mtd = next((m["cost"] for m in months if m["month"] == this_month), 0.0)
    return {
        "subscription": info,
        "current": subscription.savings(mtd, info),
        "timeline": subscription.savings_timeline(months, info),
    }


def logs_iter(from_: str | None, to_: str | None, model_family: str | None,
              project: str | None, q: str | None, model: str | None = None):
    """Yield all matching log rows (for CSV export)."""
    page, page_size = 1, 2000
    while True:
        chunk = logs(from_, to_, model_family, project, q, page, page_size, model)
        yield from chunk["items"]
        if page * page_size >= chunk["total"]:
            break
        page += 1
