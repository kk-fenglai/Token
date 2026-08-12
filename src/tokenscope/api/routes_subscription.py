from fastapi import APIRouter, HTTPException

from .. import queries, subscription

router = APIRouter()


@router.get("/subscription")
def get_subscription():
    """Detected/pinned plan, this month's savings, and the cumulative timeline."""
    return queries.savings_report()


@router.put("/subscription")
def put_subscription(body: dict):
    """Pin the plan (`mode: "manual"`) or hand control back to detection."""
    try:
        subscription.set_subscription(
            mode=body.get("mode", "auto"),
            plan=body.get("plan"),
            monthly_usd=body.get("monthly_usd"),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return queries.savings_report()
