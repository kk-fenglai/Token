"""Loopback guard for endpoints that write, push, or expose private data."""
from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import HTTPException, Request

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def require_local(request: Request) -> None:
    """Refuse anything that is not the dashboard itself: the Host must be
    loopback (defeats DNS rebinding) and a browser Origin, when sent, must be
    loopback too (defeats cross-site POSTs)."""
    host = urlsplit("//" + (request.headers.get("host") or "")).hostname
    origin = request.headers.get("origin")
    if host not in LOOPBACK or (origin and urlsplit(origin).hostname not in LOOPBACK):
        raise HTTPException(status_code=403, detail="only allowed from the local dashboard")
