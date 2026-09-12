"""Sessions, tool attribution, heatmap, alerts, weekly report, retention."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from .. import insights

router = APIRouter()


@router.get("/alerts")
def alerts(project: str | None = None):
    return insights.alerts(project)


@router.get("/heatmap")
def heatmap(range: str = Query("30d"), project: str | None = None):
    return insights.heatmap(range, project)


@router.get("/tools")
def tools(range: str = Query("30d"), project: str | None = None):
    return insights.tools_breakdown(range, project)


@router.get("/sessions")
def sessions(range: str | None = Query("7d"),
             from_: str | None = Query(None, alias="from"),
             to_: str | None = Query(None, alias="to"),
             project: str | None = None,
             q: str | None = None,
             sort: str = Query("start", pattern="^(start|cost)$"),
             page: int = Query(1, ge=1),
             page_size: int = Query(50, ge=1, le=500)):
    if from_ or to_:
        range = None
    return insights.sessions(range, from_, to_, project, q, sort, page, page_size)


@router.get("/sessions/detail")
def session_detail(id: str):
    detail = insights.session_detail(id)
    if detail is None:
        raise HTTPException(status_code=404, detail="session not found")
    return detail


@router.get("/report/weekly")
def weekly(week: int = Query(0, ge=0, le=52), project: str | None = None,
           lang: str = Query("zh", pattern="^(zh|en|fr)$")):
    report = insights.weekly_report(week, project)
    report["markdown"] = insights.render_weekly_markdown(report, "zh" if lang == "zh" else "en")
    return report


@router.get("/report/weekly.md")
def weekly_md(week: int = Query(0, ge=0, le=52), project: str | None = None,
              lang: str = Query("zh", pattern="^(zh|en|fr)$")):
    report = insights.weekly_report(week, project)
    md = insights.render_weekly_markdown(report, "zh" if lang == "zh" else "en")
    name = f"tokenscope-week-{report['week']['from']}.md"
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f"attachment; filename={name}"})


@router.get("/retention")
def retention():
    return {**insights.retention_info(), "pricing": insights.pricing_status()}
