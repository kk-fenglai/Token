import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..sync import service

router = APIRouter()


@router.get("/sync/status")
def sync_status():
    return service.status()


@router.post("/sync")
async def sync_now():
    if service.syncing:
        return JSONResponse(status_code=409, content={"syncing": True})
    return await asyncio.to_thread(service.sync_once)
