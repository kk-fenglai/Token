"""Project scope: pin the whole dashboard to one project.

`tokenscope-web --project <path>` (or TOKENSCOPE_PROJECT) sets the scope the UI
opens with, so launching from inside a repo shows that repo's spend rather than
the whole account. The UI can still switch scope at runtime — the flag only
picks the default.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

from .. import queries
from ..parser import normalize_cwd

router = APIRouter()

# Set by web.main() from --project; env var lets `uvicorn tokenscope.web:app`
# and the MCP launcher pass a scope without going through argparse.
_default_project: str | None = None


def set_default_project(path: str | None) -> None:
    global _default_project
    _default_project = normalize_cwd(os.path.abspath(path)) if path else None


def default_project() -> str | None:
    if _default_project:
        return _default_project
    env = os.environ.get("TOKENSCOPE_PROJECT")
    return normalize_cwd(os.path.abspath(env)) if env else None


@router.get("/scope")
def get_scope():
    """The scope the UI should open with. `scope` is null for account-wide."""
    project = default_project()
    return {"default_project": project, "scope": queries.scope_info(project)}


@router.get("/projects/share")
def project_share(project: str):
    if not project.strip():
        raise HTTPException(status_code=422, detail="project is required")
    return queries.project_share(project)
