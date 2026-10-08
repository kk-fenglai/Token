"""F30 — inspiration board: find real-life needs behind products people pay for.

Private research only (TrustMRR ToS §9 allows it): everything lives in the
local TokenScope DB, nothing is published, no page is scraped.

  products      revenue signals pulled by `ideas_sync` (TrustMRR API or the
                public discovery endpoint), one row per startup slug
  snapshots     one metric row per product per day, for our own trend view
  marks         interested / ignored, so a weekly scan only shows what's new
  clusters      a "need": a group of products that solve the same problem
  cards         the need card — 8 fields, 5 gates, 6 scores, red flags
  observations  one-line notes from daily life, optionally tied to a cluster
  validations   what was done to test a card and what came of it

Founder-written text (descriptions, insights) is untrusted: it is stored and
shown as plain text and never interpreted.
"""
from __future__ import annotations

import json
import re
import statistics
from datetime import datetime, timedelta, timezone

from .db import locked_conn

_SCHEMA = """
CREATE TABLE IF NOT EXISTS idea_products (
  slug             TEXT PRIMARY KEY,
  source           TEXT NOT NULL,
  name             TEXT NOT NULL,
  description      TEXT,
  website          TEXT,
  url              TEXT,
  icon             TEXT,
  category         TEXT,
  target_audience  TEXT,
  payment_provider TEXT,
  country          TEXT,
  mrr              REAL,
  revenue_30d      REAL,
  revenue_total    REAL,
  customers        INTEGER,
  active_subs      INTEGER,
  growth_30d       REAL,
  growth_mrr_30d   REAL,
  visitors_30d     INTEGER,
  on_sale          INTEGER NOT NULL DEFAULT 0,
  stealth          INTEGER NOT NULL DEFAULT 0,
  in_recent        TEXT,
  baseline         INTEGER NOT NULL DEFAULT 0,
  detail           TEXT,
  detail_at        TEXT,
  detail_mrr       REAL,
  public_md        TEXT,
  public_md_at     TEXT,
  first_seen       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_idea_products_mrr ON idea_products(mrr);
CREATE TABLE IF NOT EXISTS idea_snapshots (
  slug        TEXT NOT NULL,
  day         TEXT NOT NULL,
  mrr         REAL,
  revenue_30d REAL,
  customers   INTEGER,
  growth_30d  REAL,
  PRIMARY KEY (slug, day)
);
CREATE TABLE IF NOT EXISTS idea_marks (
  slug TEXT PRIMARY KEY,
  mark TEXT NOT NULL,
  ts   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idea_clusters (
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  note       TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idea_cluster_products (
  cluster_id INTEGER NOT NULL,
  slug       TEXT NOT NULL,
  added_at   TEXT NOT NULL,
  PRIMARY KEY (cluster_id, slug)
);
CREATE TABLE IF NOT EXISTS idea_cards (
  id                INTEGER PRIMARY KEY,
  cluster_id        INTEGER,
  need              TEXT NOT NULL DEFAULT '',
  payer             TEXT NOT NULL DEFAULT '',
  job               TEXT NOT NULL DEFAULT '',
  alternative       TEXT NOT NULL DEFAULT '',
  life_mapping      TEXT NOT NULL DEFAULT '',
  validation_action TEXT NOT NULL DEFAULT '',
  conclusion        TEXT NOT NULL DEFAULT '',
  status            TEXT NOT NULL DEFAULT 'draft',
  gates             TEXT NOT NULL DEFAULT '{}',
  scores            TEXT NOT NULL DEFAULT '{}',
  red_flags         TEXT NOT NULL DEFAULT '[]',
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idea_observations (
  id         INTEGER PRIMARY KEY,
  text       TEXT NOT NULL,
  tags       TEXT NOT NULL DEFAULT '[]',
  cluster_id INTEGER,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idea_validations (
  id         INTEGER PRIMARY KEY,
  card_id    INTEGER NOT NULL,
  action     TEXT NOT NULL,
  day        TEXT NOT NULL,
  result     TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idea_sync_runs (
  id          INTEGER PRIMARY KEY,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  mode        TEXT NOT NULL,
  requests    INTEGER NOT NULL DEFAULT 0,
  products    INTEGER NOT NULL DEFAULT 0,
  details     INTEGER NOT NULL DEFAULT 0,
  status      TEXT NOT NULL DEFAULT 'running',
  error       TEXT
);
"""

STATUSES = ("draft", "validating", "doing", "watching", "dropped")
GATES = ("paying", "recurring", "who", "reach", "doable")
SCORES = ("strength", "breadth", "frequency", "alternative_gap", "reach", "trend")
RED_FLAGS = ("peer_loop", "founder_audience", "head_monopoly", "overseas_only", "hype_churn", "nobody_cares")
TEXT_FIELDS = ("need", "payer", "job", "alternative", "life_mapping", "validation_action", "conclusion")
TEXT_LIMIT = 4000
MIN_SIGNALS = 3          # products a cluster needs before its card can leave draft
SIGNAL_MRR = 1000        # a product counts as a paying signal at MRR >= $1k
STALE_DAYS = 14

_ready: int | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure(conn) -> None:
    global _ready
    if _ready != id(conn):
        conn.executescript(_SCHEMA)
        _ready = id(conn)


def _clean(text, limit: int = TEXT_LIMIT) -> str:
    """Plain text only: drop control characters (keep newlines/tabs) and cap length."""
    if not isinstance(text, str):
        return ""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).strip()[:limit]


def _json(raw, default):
    try:
        v = json.loads(raw) if raw else default
    except ValueError:
        return default
    return v if isinstance(v, type(default)) else default


# --------------------------------------------------------------- products ----

PRODUCT_COLS = ("source", "name", "description", "website", "url", "icon", "category", "target_audience",
                "payment_provider", "country", "mrr", "revenue_30d", "revenue_total", "customers",
                "active_subs", "growth_30d", "growth_mrr_30d", "visitors_30d", "on_sale", "stealth")


def upsert_products(items: list[dict], *, baseline: bool = False, recent: bool = False) -> int:
    """Insert or refresh normalized products and record today's snapshot.

    `baseline` marks rows first seen in the very first sync, so the "new this
    week" view does not list the whole catalogue on day one. `recent` stamps
    rows that came from the discovery feed's recently-added group.
    """
    ts = now_iso()
    day = ts[:10]
    with locked_conn() as conn:
        _ensure(conn)
        for p in items:
            vals = [p.get(c) for c in PRODUCT_COLS]
            conn.execute(
                f"INSERT INTO idea_products(slug, {', '.join(PRODUCT_COLS)}, baseline, in_recent, first_seen, updated_at) "
                f"VALUES (?, {', '.join('?' * len(PRODUCT_COLS))}, ?, ?, ?, ?) "
                f"ON CONFLICT(slug) DO UPDATE SET "
                + ", ".join(f"{c}=COALESCE(excluded.{c}, {c})" for c in PRODUCT_COLS if c != "source")
                + ", in_recent=COALESCE(excluded.in_recent, in_recent), updated_at=excluded.updated_at, "
                  "source=CASE WHEN source='trustmrr_api' THEN source ELSE excluded.source END",
                [p["slug"], *vals, 1 if baseline else 0, ts if recent else None, ts, ts],
            )
            conn.execute(
                "INSERT INTO idea_snapshots(slug, day, mrr, revenue_30d, customers, growth_30d) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(slug, day) DO UPDATE SET mrr=excluded.mrr, revenue_30d=excluded.revenue_30d, "
                "customers=COALESCE(excluded.customers, customers), growth_30d=excluded.growth_30d",
                (p["slug"], day, p.get("mrr"), p.get("revenue_30d"), p.get("customers"), p.get("growth_30d")),
            )
        conn.commit()
    return len(items)


def save_detail(slug: str, detail: dict, extra: dict) -> None:
    """Store the detail endpoint's extra fields (insights, stack, channels)
    plus any list-level fields it refreshed."""
    ts = now_iso()
    with locked_conn() as conn:
        _ensure(conn)
        sets = ", ".join(f"{c}=COALESCE(?, {c})" for c in PRODUCT_COLS if c in extra)
        args = [extra[c] for c in PRODUCT_COLS if c in extra]
        conn.execute(
            f"UPDATE idea_products SET detail=?, detail_at=?, detail_mrr=mrr{', ' + sets if sets else ''} WHERE slug=?",
            [json.dumps(detail, ensure_ascii=False), ts, *args, slug],
        )
        conn.commit()


def save_public_md(slug: str, text: str) -> None:
    with locked_conn() as conn:
        _ensure(conn)
        conn.execute("UPDATE idea_products SET public_md=?, public_md_at=? WHERE slug=?",
                     (_clean(text, 60_000), now_iso(), slug))
        conn.commit()


def detail_queue(limit: int) -> list[str]:
    """Slugs whose detail is missing or stale: interested ones first, then
    rows in clusters, then never-fetched rows by growth; a row is stale once
    its MRR moved more than 10% since the last detail fetch."""
    with locked_conn() as conn:
        _ensure(conn)
        rows = conn.execute(
            """SELECT p.slug FROM idea_products p
               LEFT JOIN idea_marks m ON m.slug = p.slug
               WHERE p.source = 'trustmrr_api' AND p.stealth = 0 AND COALESCE(m.mark, '') != 'ignored'
                 AND (p.detail_at IS NULL
                      OR ABS(COALESCE(p.mrr, 0) - COALESCE(p.detail_mrr, 0)) > 0.1 * MAX(COALESCE(p.detail_mrr, 0), 1))
               ORDER BY (m.mark = 'interested') DESC,
                        EXISTS (SELECT 1 FROM idea_cluster_products c WHERE c.slug = p.slug) DESC,
                        p.detail_at IS NOT NULL, COALESCE(p.growth_30d, 0) DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [r["slug"] for r in rows]


def has_products() -> bool:
    with locked_conn() as conn:
        _ensure(conn)
        return conn.execute("SELECT 1 FROM idea_products LIMIT 1").fetchone() is not None


def _product_row(r) -> dict:
    d = {k: r[k] for k in r.keys() if k not in ("detail", "public_md")}
    d["on_sale"] = bool(d["on_sale"])
    d["stealth"] = bool(d["stealth"])
    d["detail"] = _json(r["detail"], {}) if "detail" in r.keys() else {}
    return d


SORTS = {
    "growth": "COALESCE(p.growth_30d, -1e18) DESC",
    "mrr": "COALESCE(p.mrr, 0) DESC",
    "customers": "COALESCE(p.customers, 0) DESC",
    "new": "p.first_seen DESC, COALESCE(p.in_recent, '') DESC",
}


def list_products(*, q: str = "", category: str = "", min_mrr: float | None = None,
                  max_mrr: float | None = None, min_growth: float | None = None,
                  min_customers: int | None = None, audience: str = "", view: str = "all",
                  sort: str = "growth", mark: str = "", page: int = 1, limit: int = 50) -> dict:
    """`view`: all | new (first seen in 7 days, not baseline, or in the
    discovery recently-added feed in 7 days) | todo (not yet marked).
    `mark`: "" hides ignored rows; interested / ignored shows only those."""
    where, args = ["p.stealth = 0"], []
    if q:
        like = f"%{q}%"
        where.append("(p.name LIKE ? OR p.description LIKE ? OR p.detail LIKE ? OR p.slug LIKE ?)")
        args += [like, like, like, like]
    if category:
        where.append("p.category = ?")
        args.append(category)
    if audience:
        where.append("p.target_audience = ?")
        args.append(audience)
    if min_mrr is not None:
        where.append("COALESCE(p.mrr, 0) >= ?")
        args.append(min_mrr)
    if max_mrr is not None:
        where.append("COALESCE(p.mrr, 0) <= ?")
        args.append(max_mrr)
    if min_growth is not None:
        where.append("COALESCE(p.growth_30d, 0) >= ?")
        args.append(min_growth)
    if min_customers is not None:
        where.append("COALESCE(p.customers, 0) >= ?")
        args.append(min_customers)
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
    if view == "new":
        where.append("((p.first_seen >= ? AND p.baseline = 0) OR COALESCE(p.in_recent, '') >= ?)")
        args += [week_ago, week_ago]
    if mark in ("interested", "ignored"):
        where.append("m.mark = ?")
        args.append(mark)
    elif view == "todo":
        where.append("m.mark IS NULL")
    else:
        where.append("COALESCE(m.mark, '') != 'ignored'")
    order = SORTS.get(sort, SORTS["growth"])
    page, limit = max(1, page), max(1, min(limit, 200))
    sql_where = " AND ".join(where)
    with locked_conn() as conn:
        _ensure(conn)
        total = conn.execute(
            f"SELECT COUNT(*) FROM idea_products p LEFT JOIN idea_marks m ON m.slug = p.slug WHERE {sql_where}",
            args).fetchone()[0]
        rows = conn.execute(
            f"""SELECT p.*, m.mark,
                  (SELECT GROUP_CONCAT(cluster_id) FROM idea_cluster_products c WHERE c.slug = p.slug) AS clusters
                FROM idea_products p LEFT JOIN idea_marks m ON m.slug = p.slug
                WHERE {sql_where} ORDER BY {order}, p.slug LIMIT ? OFFSET ?""",
            [*args, limit, (page - 1) * limit]).fetchall()
        cats = [r[0] for r in conn.execute(
            "SELECT category FROM idea_products WHERE category IS NOT NULL AND stealth = 0 "
            "GROUP BY category ORDER BY COUNT(*) DESC").fetchall()]
    items = []
    for r in rows:
        d = _product_row(r)
        d["clusters"] = [int(x) for x in (r["clusters"] or "").split(",") if x]
        items.append(d)
    return {"items": items, "total": total, "page": page, "limit": limit, "categories": cats}


def get_product(slug: str) -> dict | None:
    with locked_conn() as conn:
        _ensure(conn)
        r = conn.execute("SELECT p.*, m.mark FROM idea_products p LEFT JOIN idea_marks m ON m.slug = p.slug "
                         "WHERE p.slug = ?", (slug,)).fetchone()
        if not r:
            return None
        snaps = conn.execute("SELECT day, mrr, revenue_30d, customers, growth_30d FROM idea_snapshots "
                             "WHERE slug = ? ORDER BY day", (slug,)).fetchall()
        clusters = conn.execute(
            "SELECT c.id, c.name FROM idea_clusters c JOIN idea_cluster_products cp ON cp.cluster_id = c.id "
            "WHERE cp.slug = ? ORDER BY c.name", (slug,)).fetchall()
    d = _product_row(r)
    d["public_md"] = r["public_md"]
    d["snapshots"] = [dict(s) for s in snaps]
    d["clusters"] = [dict(c) for c in clusters]
    return d


def set_mark(slug: str, mark: str | None) -> None:
    with locked_conn() as conn:
        _ensure(conn)
        if mark:
            conn.execute("INSERT INTO idea_marks(slug, mark, ts) VALUES (?,?,?) "
                         "ON CONFLICT(slug) DO UPDATE SET mark=excluded.mark, ts=excluded.ts",
                         (slug, mark, now_iso()))
        else:
            conn.execute("DELETE FROM idea_marks WHERE slug = ?", (slug,))
        conn.commit()


# --------------------------------------------------------------- clusters ----

def _stats(products: list[dict]) -> dict:
    mrrs = [p["mrr"] or 0 for p in products]
    paying = [m for m in mrrs if m >= SIGNAL_MRR]
    arpu = [p["mrr"] / p["customers"] for p in products if p.get("customers") and p.get("mrr")]
    growths = [p["growth_30d"] for p in products if p.get("growth_30d") is not None]
    total = sum(mrrs)
    return {
        "count": len(products),
        "paying_count": len(paying),
        "mrr_median": statistics.median(mrrs) if mrrs else None,
        "mrr_min": min(mrrs) if mrrs else None,
        "mrr_max": max(mrrs) if mrrs else None,
        "customers": sum(p.get("customers") or 0 for p in products),
        "arpu_median": statistics.median(arpu) if arpu else None,
        "growing_share": (sum(1 for g in growths if g > 0) / len(growths)) if growths else None,
        "top_share": (max(mrrs) / total) if total > 0 else None,
    }


def _cluster_products(conn, cluster_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT p.* FROM idea_products p JOIN idea_cluster_products c ON c.slug = p.slug "
        "WHERE c.cluster_id = ? ORDER BY COALESCE(p.mrr, 0) DESC", (cluster_id,)).fetchall()
    return [_product_row(r) for r in rows]


def list_clusters() -> list[dict]:
    with locked_conn() as conn:
        _ensure(conn)
        rows = conn.execute("SELECT * FROM idea_clusters ORDER BY updated_at DESC").fetchall()
        out = []
        for r in rows:
            prods = _cluster_products(conn, r["id"])
            card = conn.execute("SELECT id, status FROM idea_cards WHERE cluster_id = ? ORDER BY id LIMIT 1",
                                (r["id"],)).fetchone()
            obs = conn.execute("SELECT COUNT(*) FROM idea_observations WHERE cluster_id = ?",
                               (r["id"],)).fetchone()[0]
            out.append({**dict(r), "stats": _stats(prods), "observations": obs,
                        "products": [{"slug": p["slug"], "name": p["name"], "mrr": p["mrr"]} for p in prods],
                        "card": dict(card) if card else None})
    return out


def get_cluster(cluster_id: int) -> dict | None:
    with locked_conn() as conn:
        _ensure(conn)
        r = conn.execute("SELECT * FROM idea_clusters WHERE id = ?", (cluster_id,)).fetchone()
        if not r:
            return None
        prods = _cluster_products(conn, cluster_id)
    return {**dict(r), "products": prods, "stats": _stats(prods)}


def create_cluster(name: str, note: str = "") -> dict:
    name = _clean(name, 120)
    if not name:
        raise ValueError("name required")
    ts = now_iso()
    with locked_conn() as conn:
        _ensure(conn)
        cur = conn.execute("INSERT INTO idea_clusters(name, note, created_at, updated_at) VALUES (?,?,?,?)",
                           (name, _clean(note), ts, ts))
        conn.commit()
        cid = cur.lastrowid
    return get_cluster(cid)


def update_cluster(cluster_id: int, name: str | None = None, note: str | None = None) -> dict | None:
    sets, args = [], []
    if name is not None:
        if not _clean(name, 120):
            raise ValueError("name required")
        sets.append("name = ?")
        args.append(_clean(name, 120))
    if note is not None:
        sets.append("note = ?")
        args.append(_clean(note))
    with locked_conn() as conn:
        _ensure(conn)
        conn.execute(f"UPDATE idea_clusters SET {', '.join([*sets, 'updated_at = ?'])} WHERE id = ?",
                     [*args, now_iso(), cluster_id])
        conn.commit()
    return get_cluster(cluster_id)


def delete_cluster(cluster_id: int) -> None:
    """Cards and observations keep their text; they just lose the link."""
    with locked_conn() as conn:
        _ensure(conn)
        conn.execute("DELETE FROM idea_cluster_products WHERE cluster_id = ?", (cluster_id,))
        conn.execute("UPDATE idea_cards SET cluster_id = NULL WHERE cluster_id = ?", (cluster_id,))
        conn.execute("UPDATE idea_observations SET cluster_id = NULL WHERE cluster_id = ?", (cluster_id,))
        conn.execute("DELETE FROM idea_clusters WHERE id = ?", (cluster_id,))
        conn.commit()


def set_cluster_product(cluster_id: int, slug: str, present: bool) -> dict | None:
    with locked_conn() as conn:
        _ensure(conn)
        if not conn.execute("SELECT 1 FROM idea_clusters WHERE id = ?", (cluster_id,)).fetchone():
            return None
        if present:
            if not conn.execute("SELECT 1 FROM idea_products WHERE slug = ?", (slug,)).fetchone():
                raise KeyError(slug)
            conn.execute("INSERT OR IGNORE INTO idea_cluster_products(cluster_id, slug, added_at) VALUES (?,?,?)",
                         (cluster_id, slug, now_iso()))
            # Clustering a product is a stronger signal than "interested".
            conn.execute("INSERT INTO idea_marks(slug, mark, ts) VALUES (?, 'interested', ?) "
                         "ON CONFLICT(slug) DO UPDATE SET mark='interested', ts=excluded.ts", (slug, now_iso()))
        else:
            conn.execute("DELETE FROM idea_cluster_products WHERE cluster_id = ? AND slug = ?", (cluster_id, slug))
        conn.execute("UPDATE idea_clusters SET updated_at = ? WHERE id = ?", (now_iso(), cluster_id))
        conn.commit()
    return get_cluster(cluster_id)


# ------------------------------------------------------------------ cards ----

def suggestions(stats: dict, products: list[dict]) -> dict:
    """What the data alone can say about a card's gates, scores and flags.
    Everything about my own life (who, reach, doable, frequency, gap) stays
    with me; these are only pre-fills the card shows next to my choices."""
    n, med = stats["paying_count"], stats["mrr_median"] or 0
    subs = [p for p in products if (p.get("active_subs") or 0) > 0 or (p.get("mrr") or 0) > 0]
    gates = {
        "paying": n >= MIN_SIGNALS,
        "recurring": bool(products) and len(subs) >= max(1, (len(products) + 1) // 2),
    }
    scores: dict[str, int] = {}
    if stats["count"]:
        scores["strength"] = 2 if (n >= 6 or med >= 5000) else 1 if n >= 3 else 0
    if stats["arpu_median"] is not None:
        a = stats["arpu_median"]
        scores["breadth"] = 2 if a <= 30 else 1 if a <= 200 else 0
    if stats["growing_share"] is not None:
        g = stats["growing_share"]
        scores["trend"] = 2 if g >= 0.6 else 1 if g >= 0.3 else 0
    flags = []
    if stats["top_share"] is not None and stats["count"] >= 2 and stats["top_share"] >= 0.7:
        flags.append("head_monopoly")
    return {"gates": gates, "scores": scores, "red_flags": flags}


def evaluate(gates: dict, scores: dict, red_flags: list[str]) -> dict:
    """Score 0–12 → tier (2 validate now, 1 watch, 0 drop); each red flag
    drops one tier; any failed gate means the need is not card-worthy yet."""
    total = sum(int(scores.get(k) or 0) for k in SCORES)
    scored = sum(1 for k in SCORES if scores.get(k) is not None)
    base = 2 if total >= 9 else 1 if total >= 6 else 0
    tier = max(0, base - len(red_flags))
    gates_ok = all(gates.get(k) for k in GATES)
    if not gates_ok:
        verdict = "gates"
    else:
        verdict = ("drop", "watch", "validate")[tier]
    return {"total": total, "scored": scored, "base_tier": base, "tier": tier,
            "gates_passed": sum(1 for k in GATES if gates.get(k)), "gates_ok": gates_ok, "verdict": verdict}


def leave_draft_errors(card: dict) -> list[str]:
    errors = []
    if (card.get("cluster_stats") or {}).get("count", 0) < MIN_SIGNALS:
        errors.append("signals")
    if not card.get("life_mapping", "").strip():
        errors.append("life_mapping")
    return errors


def _card_row(conn, r) -> dict:
    d = dict(r)
    d["gates"] = {k: bool(v) for k, v in _json(r["gates"], {}).items() if k in GATES}
    d["scores"] = {k: v for k, v in _json(r["scores"], {}).items() if k in SCORES and v in (0, 1, 2)}
    d["red_flags"] = [f for f in _json(r["red_flags"], []) if f in RED_FLAGS]
    prods = _cluster_products(conn, r["cluster_id"]) if r["cluster_id"] else []
    stats = _stats(prods)
    cluster = conn.execute("SELECT id, name, note FROM idea_clusters WHERE id = ?",
                           (r["cluster_id"],)).fetchone() if r["cluster_id"] else None
    vals = conn.execute("SELECT * FROM idea_validations WHERE card_id = ? ORDER BY day DESC, id DESC",
                        (r["id"],)).fetchall()
    obs = conn.execute("SELECT * FROM idea_observations WHERE cluster_id = ? ORDER BY created_at DESC",
                       (r["cluster_id"],)).fetchall() if r["cluster_id"] else []
    d["cluster"] = dict(cluster) if cluster else None
    d["products"] = prods
    d["cluster_stats"] = stats
    d["validations"] = [dict(v) for v in vals]
    d["observations"] = [{**dict(o), "tags": _json(o["tags"], [])} for o in obs]
    d["suggested"] = suggestions(stats, prods)
    d["evaluation"] = evaluate(d["gates"], d["scores"], d["red_flags"])
    d["last_activity"] = max([d["updated_at"], *(v["created_at"] for v in vals)])
    d["stale"] = d["status"] == "validating" and _older_than(d["last_activity"], STALE_DAYS)
    return d


def _older_than(iso: str, days: int) -> bool:
    try:
        t = datetime.fromisoformat(iso)
    except ValueError:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - t > timedelta(days=days)


def get_card(card_id: int) -> dict | None:
    with locked_conn() as conn:
        _ensure(conn)
        r = conn.execute("SELECT * FROM idea_cards WHERE id = ?", (card_id,)).fetchone()
        return _card_row(conn, r) if r else None


def list_cards(ids: list[int] | None = None) -> list[dict]:
    with locked_conn() as conn:
        _ensure(conn)
        if ids:
            rows = conn.execute(f"SELECT * FROM idea_cards WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
            order = {i: n for n, i in enumerate(ids)}
            rows = sorted(rows, key=lambda r: order.get(r["id"], 0))
        else:
            rows = conn.execute("SELECT * FROM idea_cards ORDER BY updated_at DESC").fetchall()
        return [_card_row(conn, r) for r in rows]


def create_card(cluster_id: int | None, need: str = "") -> dict:
    ts = now_iso()
    with locked_conn() as conn:
        _ensure(conn)
        if cluster_id is not None:
            c = conn.execute("SELECT name FROM idea_clusters WHERE id = ?", (cluster_id,)).fetchone()
            if not c:
                raise KeyError(cluster_id)
            need = need or c["name"]
        cur = conn.execute("INSERT INTO idea_cards(cluster_id, need, created_at, updated_at) VALUES (?,?,?,?)",
                           (cluster_id, _clean(need), ts, ts))
        conn.commit()
        cid = cur.lastrowid
    return get_card(cid)


def clean_card_patch(body: dict) -> tuple[dict, list[str]]:
    out, errors = {}, []
    for k in TEXT_FIELDS:
        if k in body:
            if not isinstance(body[k], str):
                errors.append(f"{k} must be a string")
            else:
                out[k] = _clean(body[k])
    if "status" in body:
        if body["status"] not in STATUSES:
            errors.append("bad status")
        else:
            out["status"] = body["status"]
    if "cluster_id" in body:
        if body["cluster_id"] is not None and not (isinstance(body["cluster_id"], int) and not isinstance(body["cluster_id"], bool)):
            errors.append("cluster_id must be an integer or null")
        else:
            out["cluster_id"] = body["cluster_id"]
    if "gates" in body:
        g = body["gates"]
        if not isinstance(g, dict) or any(k not in GATES or not isinstance(v, bool) for k, v in g.items()):
            errors.append("gates must map gate names to booleans")
        else:
            out["gates"] = g
    if "scores" in body:
        s = body["scores"]
        if not isinstance(s, dict) or any(k not in SCORES or (v is not None and v not in (0, 1, 2)) or isinstance(v, bool)
                                          for k, v in s.items()):
            errors.append("scores must map score names to 0, 1, 2 or null")
        else:
            out["scores"] = {k: v for k, v in s.items() if v is not None}
    if "red_flags" in body:
        f = body["red_flags"]
        if not isinstance(f, list) or any(x not in RED_FLAGS for x in f):
            errors.append("red_flags must be a list of known flags")
        else:
            out["red_flags"] = list(dict.fromkeys(f))
    unknown = set(body) - set(TEXT_FIELDS) - {"status", "cluster_id", "gates", "scores", "red_flags"}
    if unknown:
        errors.append(f"unknown keys: {', '.join(sorted(unknown))}")
    return out, errors


class DraftRule(Exception):
    def __init__(self, reasons: list[str]):
        super().__init__(", ".join(reasons))
        self.reasons = reasons


def update_card(card_id: int, patch: dict) -> dict | None:
    """Partial update. Leaving draft needs >= 3 products in the card's
    cluster and a life mapping (PRD rule: no life mapping, no card)."""
    current = get_card(card_id)
    if current is None:
        return None
    if "cluster_id" in patch and patch["cluster_id"] is not None and get_cluster(patch["cluster_id"]) is None:
        raise KeyError(patch["cluster_id"])
    target_status = patch.get("status", current["status"])
    if target_status != "draft":
        preview = {**current, **{k: v for k, v in patch.items() if k in TEXT_FIELDS}}
        if "cluster_id" in patch:
            c = get_cluster(patch["cluster_id"]) if patch["cluster_id"] is not None else None
            preview["cluster_stats"] = c["stats"] if c else {"count": 0}
        errors = leave_draft_errors(preview)
        if errors:
            raise DraftRule(errors)
    cols, args = [], []
    for k, v in patch.items():
        cols.append(f"{k} = ?")
        args.append(json.dumps(v, ensure_ascii=False) if k in ("gates", "scores", "red_flags") else v)
    with locked_conn() as conn:
        _ensure(conn)
        conn.execute(f"UPDATE idea_cards SET {', '.join([*cols, 'updated_at = ?'])} WHERE id = ?",
                     [*args, now_iso(), card_id])
        conn.commit()
    return get_card(card_id)


def delete_card(card_id: int) -> None:
    with locked_conn() as conn:
        _ensure(conn)
        conn.execute("DELETE FROM idea_validations WHERE card_id = ?", (card_id,))
        conn.execute("DELETE FROM idea_cards WHERE id = ?", (card_id,))
        conn.commit()


def add_validation(card_id: int, action: str, day: str, result: str = "") -> dict | None:
    action = _clean(action, 1000)
    if not action:
        raise ValueError("action required")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day or ""):
        raise ValueError("day must be YYYY-MM-DD")
    with locked_conn() as conn:
        _ensure(conn)
        if not conn.execute("SELECT 1 FROM idea_cards WHERE id = ?", (card_id,)).fetchone():
            return None
        conn.execute("INSERT INTO idea_validations(card_id, action, day, result, created_at) VALUES (?,?,?,?,?)",
                     (card_id, action, day, _clean(result), now_iso()))
        conn.commit()
    return get_card(card_id)


def delete_validation(card_id: int, validation_id: int) -> dict | None:
    with locked_conn() as conn:
        _ensure(conn)
        conn.execute("DELETE FROM idea_validations WHERE id = ? AND card_id = ?", (validation_id, card_id))
        conn.commit()
    return get_card(card_id)


def card_markdown(card: dict) -> str:
    """Export for my own notes: my words plus links to the source pages, no
    TrustMRR metrics (bulk republication of API data is off-limits)."""
    labels = {"need": "需求一句话", "payer": "付费的人", "job": "要完成的事", "alternative": "现有替代",
              "life_mapping": "生活映射", "validation_action": "验证动作", "conclusion": "结论"}
    lines = [f"# {card['need'] or '未命名需求'}", ""]
    for k in TEXT_FIELDS[1:]:
        lines += [f"## {labels[k]}", "", card.get(k) or "(未填)", ""]
    if card["products"]:
        lines += ["## 付费信号(来源页面)", ""]
        lines += [f"- [{p['name']}]({p['url'] or p['website'] or ''})" for p in card["products"]]
        lines.append("")
    if card["validations"]:
        lines += ["## 验证记录", ""]
        lines += [f"- {v['day']} {v['action']}:{v['result'] or '待记录'}" for v in card["validations"]]
        lines.append("")
    ev = card["evaluation"]
    lines += [f"评分 {ev['total']}/12 · 门槛 {ev['gates_passed']}/5 · 反面信号 {len(card['red_flags'])} 条", ""]
    return "\n".join(lines)


# ----------------------------------------------------------- observations ----

def list_observations(limit: int = 200) -> list[dict]:
    with locked_conn() as conn:
        _ensure(conn)
        rows = conn.execute(
            "SELECT o.*, c.name AS cluster_name FROM idea_observations o "
            "LEFT JOIN idea_clusters c ON c.id = o.cluster_id ORDER BY o.created_at DESC, o.id DESC LIMIT ?",
            (limit,)).fetchall()
    return [{**dict(r), "tags": _json(r["tags"], [])} for r in rows]


def _clean_tags(tags) -> list[str]:
    if not isinstance(tags, list):
        return []
    return list(dict.fromkeys(t for t in (_clean(x, 32) for x in tags) if t))[:12]


def add_observation(text: str, tags=None, cluster_id: int | None = None) -> dict:
    text = _clean(text, 1000)
    if not text:
        raise ValueError("text required")
    with locked_conn() as conn:
        _ensure(conn)
        cur = conn.execute("INSERT INTO idea_observations(text, tags, cluster_id, created_at) VALUES (?,?,?,?)",
                           (text, json.dumps(_clean_tags(tags), ensure_ascii=False), cluster_id, now_iso()))
        conn.commit()
        oid = cur.lastrowid
    return next(o for o in list_observations(1000) if o["id"] == oid)


def update_observation(obs_id: int, body: dict) -> dict | None:
    sets, args = [], []
    if "text" in body:
        if not _clean(body["text"], 1000):
            raise ValueError("text required")
        sets.append("text = ?")
        args.append(_clean(body["text"], 1000))
    if "tags" in body:
        sets.append("tags = ?")
        args.append(json.dumps(_clean_tags(body["tags"]), ensure_ascii=False))
    if "cluster_id" in body:
        sets.append("cluster_id = ?")
        args.append(body["cluster_id"])
    if sets:
        with locked_conn() as conn:
            _ensure(conn)
            conn.execute(f"UPDATE idea_observations SET {', '.join(sets)} WHERE id = ?", [*args, obs_id])
            conn.commit()
    return next((o for o in list_observations(1000) if o["id"] == obs_id), None)


def delete_observation(obs_id: int) -> None:
    with locked_conn() as conn:
        _ensure(conn)
        conn.execute("DELETE FROM idea_observations WHERE id = ?", (obs_id,))
        conn.commit()


# ------------------------------------------------------------ search, week ----

def search(q: str, limit: int = 20) -> dict:
    """Keyword search over products and my own cards and observations. LIKE
    is enough at this size and matches Chinese and English alike."""
    q = q.strip()
    if not q:
        return {"products": [], "cards": [], "observations": []}
    like = f"%{q}%"
    with locked_conn() as conn:
        _ensure(conn)
        prods = conn.execute(
            "SELECT slug, name, description, mrr, category FROM idea_products WHERE stealth = 0 AND "
            "(name LIKE ? OR description LIKE ? OR detail LIKE ? OR category LIKE ?) "
            "ORDER BY COALESCE(mrr, 0) DESC LIMIT ?", (like, like, like, like, limit)).fetchall()
        cards = conn.execute(
            "SELECT id, need, status FROM idea_cards WHERE " +
            " OR ".join(f"{k} LIKE ?" for k in TEXT_FIELDS) + " ORDER BY updated_at DESC LIMIT ?",
            [*([like] * len(TEXT_FIELDS)), limit]).fetchall()
        obs = conn.execute("SELECT id, text, created_at FROM idea_observations WHERE text LIKE ? OR tags LIKE ? "
                           "ORDER BY created_at DESC LIMIT ?", (like, like, limit)).fetchall()
    return {"products": [dict(r) for r in prods], "cards": [dict(r) for r in cards],
            "observations": [dict(r) for r in obs]}


def week() -> dict:
    """The landing page: what to do today."""
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
    month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
    with locked_conn() as conn:
        _ensure(conn)
        new_count = conn.execute(
            "SELECT COUNT(*) FROM idea_products p LEFT JOIN idea_marks m ON m.slug = p.slug WHERE p.stealth = 0 "
            "AND ((p.first_seen >= ? AND p.baseline = 0) OR COALESCE(p.in_recent, '') >= ?) AND m.mark IS NULL",
            (week_ago, week_ago)).fetchone()[0]
        products = conn.execute("SELECT COUNT(*) FROM idea_products WHERE stealth = 0").fetchone()[0]
        unmarked = conn.execute(
            "SELECT COUNT(*) FROM idea_products p LEFT JOIN idea_marks m ON m.slug = p.slug "
            "WHERE p.stealth = 0 AND m.mark IS NULL").fetchone()[0]
        interested = conn.execute("SELECT COUNT(*) FROM idea_marks WHERE mark = 'interested'").fetchone()[0]
        clusters = conn.execute("SELECT COUNT(*) FROM idea_clusters").fetchone()[0]
        obs_week = conn.execute("SELECT COUNT(*) FROM idea_observations WHERE created_at >= ?",
                                (week_ago,)).fetchone()[0]
        validated_month = conn.execute(
            "SELECT COUNT(DISTINCT c.id) FROM idea_cards c JOIN idea_validations v ON v.card_id = c.id "
            "WHERE c.status IN ('doing', 'watching', 'dropped') AND c.updated_at >= ?", (month_ago,)).fetchone()[0]
        marked_week = conn.execute("SELECT COUNT(*) FROM idea_marks WHERE ts >= ?", (week_ago,)).fetchone()[0]
        ready = conn.execute(
            "SELECT c.id, c.name, COUNT(cp.slug) AS n FROM idea_clusters c "
            "JOIN idea_cluster_products cp ON cp.cluster_id = c.id "
            "WHERE NOT EXISTS (SELECT 1 FROM idea_cards k WHERE k.cluster_id = c.id) "
            "GROUP BY c.id HAVING n >= ? ORDER BY n DESC", (MIN_SIGNALS,)).fetchall()
    cards = list_cards()
    by_status = {s: 0 for s in STATUSES}
    for c in cards:
        by_status[c["status"]] += 1
    slim = lambda c: {"id": c["id"], "need": c["need"], "status": c["status"], "last_activity": c["last_activity"],
                      "evaluation": c["evaluation"], "stale": c["stale"]}
    return {
        "new_signals": new_count, "products": products, "unmarked": unmarked, "interested": interested,
        "clusters": clusters, "observations_week": obs_week, "validated_month": validated_month,
        "marked_week": marked_week, "cards_by_status": by_status,
        "validating": [slim(c) for c in sorted(cards, key=lambda c: c["last_activity"])
                       if c["status"] == "validating"],
        "ready_clusters": [dict(r) for r in ready],
        "recent_observations": list_observations(5),
    }
