"""F30 — inspiration board endpoints. Everything here is private research
data, so every route goes through the loopback guard."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from .. import ideas, ideas_sync
from .guard import require_local


def _local(request: Request) -> None:
    require_local(request)


router = APIRouter(prefix="/ideas", dependencies=[Depends(_local)])


def _bad(detail) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _404(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what} not found")


def _opt_int(body: dict, key: str):
    v = body.get(key)
    if v is not None and (not isinstance(v, int) or isinstance(v, bool)):
        raise _bad(f"{key} must be an integer or null")
    return v


# ------------------------------------------------------------------- week ----

@router.get("/week")
async def week():
    data = await asyncio.to_thread(ideas.week)
    return {**data, "sync": await asyncio.to_thread(ideas_sync.status)}


@router.get("/search")
async def search(q: str = ""):
    return await asyncio.to_thread(ideas.search, q)


# --------------------------------------------------------------- products ----

@router.get("/products")
async def products(q: str = "", category: str = "", audience: str = "", view: str = "all", sort: str = "growth",
                   mark: str = "", min_mrr: float | None = None, max_mrr: float | None = None,
                   min_growth: float | None = None, min_customers: int | None = None,
                   page: int = 1, limit: int = 50):
    return await asyncio.to_thread(
        ideas.list_products, q=q, category=category, audience=audience, view=view, sort=sort, mark=mark,
        min_mrr=min_mrr, max_mrr=max_mrr, min_growth=min_growth, min_customers=min_customers,
        page=page, limit=limit)


@router.get("/products/{slug}")
async def product(slug: str):
    p = await asyncio.to_thread(ideas.get_product, slug)
    if not p:
        raise _404("product")
    return p


@router.post("/products/{slug}/public-md")
async def product_public_md(slug: str):
    if not await asyncio.to_thread(ideas.get_product, slug):
        raise _404("product")
    try:
        await asyncio.to_thread(ideas_sync.fetch_public_md, slug)
    except ideas_sync.ApiError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    except OSError as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}") from None
    return await asyncio.to_thread(ideas.get_product, slug)


@router.put("/products/{slug}/mark")
async def product_mark(slug: str, body: dict):
    mark = body.get("mark")
    if mark not in ("interested", "ignored", None):
        raise _bad("mark must be interested, ignored or null")
    await asyncio.to_thread(ideas.set_mark, slug, mark)
    return {"slug": slug, "mark": mark}


# --------------------------------------------------------------- clusters ----

@router.get("/clusters")
async def clusters():
    return await asyncio.to_thread(ideas.list_clusters)


@router.post("/clusters")
async def create_cluster(body: dict):
    name, note = body.get("name"), body.get("note", "")
    if not isinstance(name, str) or not isinstance(note, str):
        raise _bad("name and note must be strings")
    try:
        c = await asyncio.to_thread(ideas.create_cluster, name, note)
    except ValueError as e:
        raise _bad(str(e)) from None
    slug = body.get("slug")
    if isinstance(slug, str) and slug:
        try:
            c = await asyncio.to_thread(ideas.set_cluster_product, c["id"], slug, True)
        except KeyError:
            raise _404("product") from None
    return c


@router.get("/clusters/{cluster_id}")
async def get_cluster(cluster_id: int):
    c = await asyncio.to_thread(ideas.get_cluster, cluster_id)
    if not c:
        raise _404("cluster")
    return c


@router.put("/clusters/{cluster_id}")
async def update_cluster(cluster_id: int, body: dict):
    name, note = body.get("name"), body.get("note")
    if (name is not None and not isinstance(name, str)) or (note is not None and not isinstance(note, str)):
        raise _bad("name and note must be strings")
    try:
        c = await asyncio.to_thread(ideas.update_cluster, cluster_id, name, note)
    except ValueError as e:
        raise _bad(str(e)) from None
    if not c:
        raise _404("cluster")
    return c


@router.delete("/clusters/{cluster_id}")
async def delete_cluster(cluster_id: int):
    await asyncio.to_thread(ideas.delete_cluster, cluster_id)
    return {"ok": True}


@router.put("/clusters/{cluster_id}/products/{slug}")
async def add_to_cluster(cluster_id: int, slug: str):
    try:
        c = await asyncio.to_thread(ideas.set_cluster_product, cluster_id, slug, True)
    except KeyError:
        raise _404("product") from None
    if not c:
        raise _404("cluster")
    return c


@router.delete("/clusters/{cluster_id}/products/{slug}")
async def remove_from_cluster(cluster_id: int, slug: str):
    c = await asyncio.to_thread(ideas.set_cluster_product, cluster_id, slug, False)
    if not c:
        raise _404("cluster")
    return c


# ------------------------------------------------------------------ cards ----

@router.get("/cards")
async def cards(ids: str = ""):
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()][:3] if ids else None
    except ValueError:
        raise _bad("ids must be comma-separated integers") from None
    return await asyncio.to_thread(ideas.list_cards, id_list)


@router.post("/cards")
async def create_card(body: dict):
    cluster_id = _opt_int(body, "cluster_id")
    need = body.get("need", "")
    if not isinstance(need, str):
        raise _bad("need must be a string")
    try:
        return await asyncio.to_thread(ideas.create_card, cluster_id, need)
    except KeyError:
        raise _404("cluster") from None


@router.get("/cards/{card_id}")
async def get_card(card_id: int):
    c = await asyncio.to_thread(ideas.get_card, card_id)
    if not c:
        raise _404("card")
    return c


@router.put("/cards/{card_id}")
async def update_card(card_id: int, body: dict):
    patch, errors = ideas.clean_card_patch(body)
    if errors:
        raise _bad(errors)
    try:
        c = await asyncio.to_thread(ideas.update_card, card_id, patch)
    except ideas.DraftRule as e:
        raise HTTPException(status_code=409, detail={"code": "draft_rule", "reasons": e.reasons}) from None
    except KeyError:
        raise _404("cluster") from None
    if not c:
        raise _404("card")
    return c


@router.delete("/cards/{card_id}")
async def delete_card(card_id: int):
    await asyncio.to_thread(ideas.delete_card, card_id)
    return {"ok": True}


@router.get("/cards/{card_id}/markdown", response_class=PlainTextResponse)
async def card_markdown(card_id: int):
    c = await asyncio.to_thread(ideas.get_card, card_id)
    if not c:
        raise _404("card")
    return ideas.card_markdown(c)


@router.post("/cards/{card_id}/validations")
async def add_validation(card_id: int, body: dict):
    action, day, result = body.get("action"), body.get("day"), body.get("result", "")
    if not all(isinstance(x, str) for x in (action, day, result)):
        raise _bad("action, day and result must be strings")
    try:
        c = await asyncio.to_thread(ideas.add_validation, card_id, action, day, result)
    except ValueError as e:
        raise _bad(str(e)) from None
    if not c:
        raise _404("card")
    return c


@router.delete("/cards/{card_id}/validations/{validation_id}")
async def delete_validation(card_id: int, validation_id: int):
    c = await asyncio.to_thread(ideas.delete_validation, card_id, validation_id)
    if not c:
        raise _404("card")
    return c


# ----------------------------------------------------------- observations ----

@router.get("/observations")
async def observations():
    return await asyncio.to_thread(ideas.list_observations)


@router.post("/observations")
async def add_observation(body: dict):
    text = body.get("text")
    if not isinstance(text, str):
        raise _bad("text must be a string")
    cluster_id = _opt_int(body, "cluster_id")
    try:
        return await asyncio.to_thread(ideas.add_observation, text, body.get("tags"), cluster_id)
    except ValueError as e:
        raise _bad(str(e)) from None


@router.put("/observations/{obs_id}")
async def update_observation(obs_id: int, body: dict):
    if "cluster_id" in body:
        _opt_int(body, "cluster_id")
    if "text" in body and not isinstance(body["text"], str):
        raise _bad("text must be a string")
    try:
        o = await asyncio.to_thread(ideas.update_observation, obs_id, body)
    except ValueError as e:
        raise _bad(str(e)) from None
    if not o:
        raise _404("observation")
    return o


@router.delete("/observations/{obs_id}")
async def delete_observation(obs_id: int):
    await asyncio.to_thread(ideas.delete_observation, obs_id)
    return {"ok": True}


# ------------------------------------------------------------------- sync ----

@router.get("/sync")
async def sync_status():
    return await asyncio.to_thread(ideas_sync.status)


@router.post("/sync")
async def sync_now():
    started = ideas_sync.start(force=True)
    return {"started": started, **(await asyncio.to_thread(ideas_sync.status))}


@router.put("/settings")
async def put_settings(body: dict):
    patch, errors = {}, []
    for k, default in ideas_sync.DEFAULTS.items():
        if k not in body:
            continue
        v = body[k]
        if isinstance(default, bool):
            if not isinstance(v, bool):
                errors.append(f"{k} must be a boolean")
                continue
        elif not isinstance(v, int) or isinstance(v, bool) or v < (0 if k == "min_mrr" else 1):
            errors.append(f"{k} must be a positive integer")
            continue
        patch[k] = v
    unknown = set(body) - set(ideas_sync.DEFAULTS)
    if unknown:
        errors.append(f"unknown keys: {', '.join(sorted(unknown))}")
    merged = {**ideas_sync.cfg(), **patch}
    if merged["min_mrr"] > merged["max_mrr"]:
        errors.append("min_mrr must not exceed max_mrr")
    if merged["rate_per_minute"] > 60:
        errors.append("rate_per_minute must be at most 60")
    if errors:
        raise _bad(errors)
    return await asyncio.to_thread(ideas_sync.save_cfg, patch)


@router.put("/key")
async def put_key(body: dict):
    key = body.get("key")
    if not isinstance(key, str):
        raise _bad("key must be a string")
    try:
        await asyncio.to_thread(ideas_sync.set_key, key)
    except ValueError as e:
        raise _bad(str(e)) from None
    return ideas_sync.key_status()


@router.delete("/key")
async def delete_key():
    await asyncio.to_thread(ideas_sync.clear_key)
    return ideas_sync.key_status()
