from fastapi import APIRouter, Query

from .. import queries
from ..db import get_meta

router = APIRouter()


@router.get("/summary/cards")
def summary_cards():
    data = queries.summary_cards()
    data["last_sync_at"] = get_meta("last_sync_at")
    return data


@router.get("/trend")
def trend(granularity: str = Query("day", pattern="^(day|month)$"),
          days: int = Query(30, ge=1, le=366),
          months: int = Query(12, ge=1, le=36)):
    return queries.trend(granularity, days, months)


@router.get("/models")
def models(range: str = Query("month")):
    return queries.models_distribution(range)


@router.get("/projects/top")
def projects_top(range: str = Query("month"), limit: int = Query(10, ge=1, le=50)):
    return queries.projects_top(range, limit)
