"""
Retailer routes — Phase A Steps 2–3 + 6 (by-phone).

Full paths:
  GET /v1/retailers
  GET /v1/retailers/by-phone/{phone}
  GET /v1/retailers/{retailer_id}/last-order
  GET /v1/retailers/{retailer_id}
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.store import (
    get_last_order,
    get_open_orders_summary,
    get_retailer,
    get_retailer_by_phone,
    get_retailers,
)

router = APIRouter(prefix="/v1", tags=["retailers"])


@router.get("/retailers")
def list_retailers():
    """
    GET /v1/retailers

    Returns every hardware shop in our seed data.
    Used later by the ops console "retailer list".
    """
    retailers = get_retailers()
    return {"count": len(retailers), "retailers": retailers}


class LastOrderIn(BaseModel):
    """Bolna POST body — more reliable than path substitution on GET."""

    retailer_id: str = Field(..., description="e.g. R01")


@router.post("/retailers/last-order")
def post_last_order(body: LastOrderIn) -> dict[str, Any]:
    """
    POST /v1/retailers/last-order  { "retailer_id": "R01" }

    Same data as GET .../last-order — preferred for Bolna custom tools.
    """
    if get_retailer(body.retailer_id) is None:
        raise HTTPException(status_code=404, detail=f"Retailer {body.retailer_id} not found")
    order = get_last_order(body.retailer_id)
    if order is None:
        raise HTTPException(
            status_code=404,
            detail=f"No previous orders for retailer {body.retailer_id}",
        )
    return {
        "retailer_id": body.retailer_id,
        "order_id": order["order_id"],
        "last_order_date": order["created_at"],
        "status": order["status"],
        "total_amount": order.get("total_amount"),
        "items": order["items"],
        "summary": ", ".join(
            f"{i.get('qty')} {i.get('unit')} {i.get('name')}" for i in order["items"]
        ),
    }


@router.get("/retailers/by-phone")
def read_retailer_by_phone(
    phone: str = Query(..., description="Caller number, e.g. +919876543210"),
):
    """
    GET /v1/retailers/by-phone?phone=+919876543210

    Inbound identify tool: Bolna passes caller number → we return shop + open orders.

    Phone is a QUERY param (not path) so '+' and spaces encode cleanly.
    Route path `/retailers/by-phone` must stay before `/retailers/{retailer_id}`.
    """
    retailer = get_retailer_by_phone(phone)
    if retailer is None:
        raise HTTPException(
            status_code=404,
            detail=f"No retailer found for phone {phone}",
        )
    open_orders = get_open_orders_summary(retailer["id"])
    return {
        "retailer_id": retailer["id"],
        "shop_name": retailer["shop_name"],
        "contact_name": retailer["contact_name"],
        "phone": retailer["phone"],
        "preferred_language": retailer.get("preferred_language"),
        "open_orders": open_orders,
        "open_order_count": len(open_orders),
    }


@router.get("/retailers/{retailer_id}/last-order")
def read_last_order(retailer_id: str):
    """
    GET /v1/retailers/{retailer_id}/last-order

    Bolna outbound tool will call this so the agent can say:
    "Last time aapne copper wire aur MCB liye the…"

    Declared BEFORE the plain /{retailer_id} route so the path
    segment `last-order` is never mistaken for an id.
    """
    if get_retailer(retailer_id) is None:
        raise HTTPException(status_code=404, detail=f"Retailer {retailer_id} not found")

    order = get_last_order(retailer_id)
    if order is None:
        raise HTTPException(
            status_code=404,
            detail=f"No previous orders for retailer {retailer_id}",
        )

    # Shape the response for the voice agent (clear field names).
    return {
        "retailer_id": retailer_id,
        "order_id": order["order_id"],
        "last_order_date": order["created_at"],
        "status": order["status"],
        "total_amount": order.get("total_amount"),
        "items": order["items"],
    }


@router.get("/retailers/{retailer_id}")
def read_retailer(retailer_id: str):
    """
    GET /v1/retailers/{retailer_id}

    Path param `retailer_id` comes from the URL, e.g. R01.
    FastAPI injects it into this function argument automatically.

    404 if the id is not in seed — correct HTTP behavior for "not found".
    """
    retailer = get_retailer(retailer_id)
    if retailer is None:
        raise HTTPException(status_code=404, detail=f"Retailer {retailer_id} not found")
    return retailer
