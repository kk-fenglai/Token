"""F30 — pull revenue signals from TrustMRR into the local inspiration board.

Two sources, both official (no page scraping):

  discovery  GET /api/ai/discovery — public, no key: the 25 most recently
             added + 25 fastest-growing startups. Amounts in US dollars.
  api        GET /api/v1/startups (+ /startups/{slug}) with a personal
             `tmrr_` key. Amounts in US cents. 10 rows a page, 10 requests a
             minute on a standard key, so a run is throttled and resumable:
             the list sweep keeps its page cursor in `meta` and continues
             where the last run stopped.

A run happens at most once per `sync_hours` (the web scheduler calls
`maybe_start`), or on demand from the settings tab. It runs on its own
thread; `status()` reports progress.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import ideas
from .agent import secrets
from .config import load_config, save_config
from .db import get_meta, locked_conn, set_meta

BASE = "https://trustmrr.com"
ENV_VAR = "TRUSTMRR_API_KEY"
SECRET_NAME = "trustmrr"
USER_AGENT = "TokenScope-ideas/1.0 (private research)"

DEFAULTS = {
    "auto_sync": True,
    "sync_hours": 24,
    # Revenue band the list sweep asks the API for, in US dollars of MRR.
    "min_mrr": 1000,
    "max_mrr": 20000,
    # Budget per run; 10 req/min means 120 requests take about 12 minutes.
    "max_requests": 120,
    "max_details": 40,
    "rate_per_minute": 10,
}


def cfg(c: dict | None = None) -> dict:
    raw = (c if c is not None else load_config()).get("ideas") or {}
    out = dict(DEFAULTS)
    for k, v in raw.items():
        if k in DEFAULTS and type(v) is type(DEFAULTS[k]):
            out[k] = v
    return out


def save_cfg(patch: dict) -> dict:
    full = load_config()
    full["ideas"] = {**cfg(full), **patch}
    save_config(full)
    return cfg(full)


# -------------------------------------------------------------------- key ----

def get_key() -> tuple[str | None, str]:
    env = os.environ.get(ENV_VAR, "").strip()
    if env:
        return env, "env"
    stored = secrets._stored_key(SECRET_NAME)
    return (stored, "stored") if stored else (None, "none")


def key_status() -> dict:
    key, source = get_key()
    return {"configured": key is not None, "source": source, "masked": secrets.mask(key)}


def set_key(key: str) -> None:
    key = key.strip()
    if not key.startswith("tmrr_"):
        raise ValueError("TrustMRR keys start with tmrr_")
    secrets.set_api_key(key, SECRET_NAME)


def clear_key() -> None:
    secrets.clear_api_key(SECRET_NAME)


# ---------------------------------------------------------- normalization ----

def _slugify(text: str | None) -> str | None:
    if not text:
        return None
    return "-".join(text.strip().lower().replace("/", " ").split())


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _int(v):
    v = _num(v)
    return int(v) if v is not None else None


def _str(v, limit: int = 2000):
    return (ideas._clean(v, limit) or None) if isinstance(v, str) else None


def normalize(item: dict, *, cents: bool, source: str) -> dict | None:
    """One TrustMRR startup → an `idea_products` row (amounts in dollars)."""
    slug = item.get("slug")
    if not isinstance(slug, str) or not slug:
        return None
    rev = item.get("revenue") if isinstance(item.get("revenue"), dict) else {}
    div = 100 if cents else 1

    def money(v):
        v = _num(v)
        return round(v / div, 2) if v is not None else None

    return {
        "slug": slug[:200],
        "source": source,
        "name": _str(item.get("name"), 200) or slug,
        "description": _str(item.get("description")),
        "website": _str(item.get("website"), 500),
        "url": f"{BASE}/startup/{urllib.parse.quote(slug)}",
        "icon": _str(item.get("icon"), 500),
        "category": _slugify(_str(item.get("category"), 80)),
        "target_audience": _str(item.get("targetAudience"), 20),
        "payment_provider": _str(item.get("paymentProvider"), 40),
        "country": _str(item.get("country"), 8),
        "mrr": money(rev.get("mrr")),
        "revenue_30d": money(rev.get("last30Days")),
        "revenue_total": money(rev.get("total")),
        "customers": _int(item.get("customers")),
        "active_subs": _int(item.get("activeSubscriptions")),
        "growth_30d": _num(item.get("growth30d")),
        "growth_mrr_30d": _num(item.get("growthMRR30d")),
        "visitors_30d": _int(item.get("visitorsLast30Days")),
        "on_sale": 1 if item.get("onSale") else 0,
        "stealth": 1 if item.get("stealthMode") else 0,
    }


def detail_fields(item: dict) -> dict:
    """The detail endpoint's extras we keep: who it is for and how it sells."""
    ins = item.get("startupInsights") if isinstance(item.get("startupInsights"), dict) else {}

    def slugs(key):
        rows = item.get(key) if isinstance(item.get(key), list) else []
        return [{"slug": _str(r.get("slug"), 60), "category": _str(r.get("category"), 40)}
                for r in rows if isinstance(r, dict) and isinstance(r.get("slug"), str)][:40]

    return {
        "description": _str(item.get("description"), 6000),
        "value_proposition": _str(ins.get("valueProposition")),
        "problem_solved": _str(ins.get("problemSolved")),
        "pricing_model": _str(ins.get("pricingModel"), 500),
        "target_persona": _str(ins.get("targetPersona")),
        "business_type": _str(ins.get("businessType"), 20),
        "team_size": _str(ins.get("teamSize"), 10),
        "funding_status": _str(ins.get("fundingStatus"), 20),
        "estimated_users": _int(ins.get("estimatedUserCount")),
        "tech_stack": slugs("techStack"),
        "marketing_channels": slugs("marketingChannels"),
        "founded": _str(item.get("foundedDate"), 40),
        "x_followers": _int(item.get("xFollowerCount")),
        "domain_rating": _num(item.get("domainRating")),
    }


# ------------------------------------------------------------------- HTTP ----

class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


class Client:
    """Throttled GETs: at most `rate_per_minute` requests, and a wait until
    the reset time whenever the server says the window is spent."""

    def __init__(self, key: str | None, rate_per_minute: int = 10, opener=None, sleep=time.sleep,
                 clock=time.monotonic):
        self.key = key
        self.min_gap = 60.0 / max(1, rate_per_minute) + 0.2
        self.opener = opener or urllib.request.urlopen
        self.sleep, self.clock = sleep, clock
        self.last = None
        self.requests = 0

    def _wait_reset(self, headers) -> None:
        try:
            reset = float(headers.get("X-RateLimit-Reset") or 0)
        except ValueError:
            reset = 0
        delay = reset - time.time() if reset > 1e9 else 60
        self.sleep(min(max(delay, 1), 120))

    def get(self, path: str, params: dict | None = None, *, auth: bool = True, raw: bool = False):
        if self.last is not None:
            gap = self.clock() - self.last
            if gap < self.min_gap:
                self.sleep(self.min_gap - gap)
        url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
        headers = {"User-Agent": USER_AGENT, "Accept": "text/markdown" if raw else "application/json"}
        if auth and self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        for attempt in range(2):
            self.last = self.clock()
            self.requests += 1
            try:
                with self.opener(urllib.request.Request(url, headers=headers), timeout=30) as res:
                    body = res.read().decode("utf-8", "replace")
                    if res.headers.get("X-RateLimit-Remaining") == "0":
                        self._wait_reset(res.headers)
                        self.last = self.clock()
                    return body if raw else json.loads(body)
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt == 0:
                    self._wait_reset(e.headers)
                    continue
                msg = ""
                try:
                    msg = json.loads(e.read().decode("utf-8", "replace")).get("error", "")
                except Exception:
                    pass
                raise ApiError(e.code, msg or e.reason) from None
        raise ApiError(429, "rate limited")


# -------------------------------------------------------------------- run ----

_state_lock = threading.Lock()
_state: dict = {"running": False}


def status() -> dict:
    with _state_lock:
        state = dict(_state)
    with locked_conn() as conn:
        ideas._ensure(conn)
        runs = [dict(r) for r in conn.execute(
            "SELECT * FROM idea_sync_runs ORDER BY id DESC LIMIT 10").fetchall()]
    return {**state, "runs": runs, "key": key_status(), "config": cfg(),
            "cursor_page": int(get_meta("ideas.list_page") or 1),
            "last_full_sweep": get_meta("ideas.last_full_sweep")}


def _progress(**kw) -> None:
    with _state_lock:
        _state.update(kw)


def run_once(client: Client | None = None) -> dict:
    """One sync pass. Discovery always (1 request, and the only source of
    "recently added"); with a key, then the list sweep and detail fetches
    until the run's request budget is spent."""
    c = cfg()
    key, _ = get_key()
    client = client or Client(key, c["rate_per_minute"])
    first_ever = not ideas.has_products()
    started = ideas.now_iso()
    with locked_conn() as conn:
        ideas._ensure(conn)
        run_id = conn.execute("INSERT INTO idea_sync_runs(started_at, mode) VALUES (?, ?)",
                              (started, "api" if key else "discovery")).lastrowid
        conn.commit()
    products = details = 0
    error = None
    try:
        _progress(phase="discovery")
        disc = client.get("/api/ai/discovery", auth=False)
        for group, recent in (("recentlyAddedStartups", True), ("fastestGrowingStartups", False)):
            rows = [r for r in (normalize(x, cents=False, source="discovery")
                                for x in (disc.get(group) or []) if isinstance(x, dict)) if r]
            products += ideas.upsert_products(rows, baseline=first_ever and not recent, recent=recent)
        if key:
            budget = c["max_requests"]
            page = int(get_meta("ideas.list_page") or 1)
            sweep_first = get_meta("ideas.last_full_sweep") is None
            reserve = min(c["max_details"], budget // 3)
            while client.requests < budget - reserve:
                _progress(phase="list", page=page)
                res = client.get("/api/v1/startups", {
                    "page": page, "limit": 10, "sort": "growth-desc",
                    "minMrr": int(c["min_mrr"] * 100), "maxMrr": int(c["max_mrr"] * 100)})
                rows = [r for r in (normalize(x, cents=True, source="trustmrr_api")
                                    for x in (res.get("data") or []) if isinstance(x, dict)) if r]
                products += ideas.upsert_products(rows, baseline=sweep_first)
                meta = res.get("meta") or {}
                _progress(total=meta.get("total"))
                if not meta.get("hasMore"):
                    page = 1
                    set_meta("ideas.last_full_sweep", ideas.now_iso())
                    sweep_first = False
                    set_meta("ideas.list_page", "1")
                    break
                page += 1
                set_meta("ideas.list_page", str(page))
            for slug in ideas.detail_queue(c["max_details"]):
                if client.requests >= budget:
                    break
                _progress(phase="detail", slug=slug)
                try:
                    item = client.get(f"/api/v1/startups/{urllib.parse.quote(slug)}").get("data") or {}
                except ApiError as e:
                    if e.status == 404:
                        continue
                    raise
                row = normalize(item, cents=True, source="trustmrr_api") or {}
                ideas.save_detail(slug, detail_fields(item),
                                  {k: v for k, v in row.items() if k not in ("slug", "source", "url")})
                details += 1
    except ApiError as e:
        error = str(e) if e.status != 401 else "API Key 无效或已失效(401)"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        error = f"{type(e).__name__}: {e}"
    status_ = "error" if error else "ok"
    with locked_conn() as conn:
        conn.execute("UPDATE idea_sync_runs SET finished_at=?, requests=?, products=?, details=?, status=?, error=? "
                     "WHERE id=?", (ideas.now_iso(), client.requests, products, details, status_, error, run_id))
        conn.commit()
    set_meta("ideas.last_sync", ideas.now_iso())
    return {"status": status_, "error": error, "requests": client.requests, "products": products, "details": details}


def start(force: bool = False) -> bool:
    """Start a run on a background thread unless one is going already."""
    with _state_lock:
        if _state.get("running"):
            return False
        _state.clear()
        _state.update(running=True, phase="starting", started_at=ideas.now_iso())

    def work():
        try:
            result = run_once()
            _progress(last_result=result)
        except Exception as e:  # never let a bad payload kill the thread silently
            _progress(last_result={"status": "error", "error": f"{type(e).__name__}: {e}"})
        finally:
            _progress(running=False, phase=None)

    threading.Thread(target=work, name="ideas-sync", daemon=True).start()
    return True


def due(now: datetime | None = None) -> bool:
    c = cfg()
    if not c["auto_sync"]:
        return False
    last = get_meta("ideas.last_sync")
    if not last:
        return True
    try:
        t = datetime.fromisoformat(last)
    except ValueError:
        return True
    return (now or datetime.now(timezone.utc)) - t >= timedelta(hours=max(1, c["sync_hours"]))


def maybe_start() -> bool:
    return start() if due() else False


def fetch_public_md(slug: str, client: Client | None = None) -> str:
    """The startup's public Markdown page (official, no key needed) — used
    for the detail view when no API key is configured. Cached in the DB."""
    client = client or Client(None, cfg()["rate_per_minute"])
    text = client.get(f"/startup/{urllib.parse.quote(slug)}.md", auth=False, raw=True)
    ideas.save_public_md(slug, text)
    return text
