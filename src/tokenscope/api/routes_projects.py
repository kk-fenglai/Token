from fastapi import APIRouter, HTTPException, Query

from .. import queries

router = APIRouter()


@router.get("/projects")
def projects(range: str = Query("30d")):
    return queries.projects_list(range)


@router.get("/projects/detail")
def project_detail(path: str):
    detail = queries.project_detail(path)
    if detail is None:
        raise HTTPException(status_code=404, detail="project not found")
    return detail
