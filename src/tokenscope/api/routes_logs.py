import csv
import io

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from .. import queries

router = APIRouter()


@router.get("/logs")
def logs(from_: str | None = Query(None, alias="from"),
         to_: str | None = Query(None, alias="to"),
         model_family: str | None = None,
         project: str | None = None,
         q: str | None = None,
         page: int = Query(1, ge=1),
         page_size: int = Query(50, ge=1, le=500)):
    return queries.logs(from_, to_, model_family, project, q, page, page_size)


@router.get("/logs/export.csv")
def export_csv(from_: str | None = Query(None, alias="from"),
               to_: str | None = Query(None, alias="to"),
               model_family: str | None = None,
               project: str | None = None,
               q: str | None = None):
    cols = ["ts", "model", "model_family", "project_name", "project_path",
            "session_id", "input", "output", "cache_write", "cache_read", "cost"]

    def generate():
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)
        for item in queries.logs_iter(from_, to_, model_family, project, q):
            writer.writerow(item)
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    return StreamingResponse(
        generate(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tokenscope-logs.csv"},
    )
