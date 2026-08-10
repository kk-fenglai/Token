from fastapi import APIRouter, HTTPException

from ..pricing import load_pricing, save_pricing, validate_pricing

router = APIRouter()


@router.get("/pricing")
def get_pricing():
    return load_pricing()


@router.put("/pricing")
def put_pricing(doc: dict):
    errors = validate_pricing(doc)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    save_pricing(doc)
    return load_pricing()
