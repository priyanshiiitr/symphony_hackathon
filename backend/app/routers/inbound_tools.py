"""
POST adapters for Bolna inbound custom tools + GET for Bolna 'identify callers'.

  POST /v1/retailers/lookup-by-phone   { "phone": "+91..." }
  POST /v1/orders/status              { "order_id": "ORD-1006", "phone": "..."? }
  GET  /v1/inbound/caller-context     ?contact_number=+91...  (Bolna identify API)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.store import (
    get_open_orders_summary,
    get_order_status,
    get_retailer_by_phone,
    order_status_payload,
    get_orders_for_retailer,
)

router = APIRouter(prefix="/v1", tags=["inbound-tools"])


class LookupByPhoneIn(BaseModel):
    phone: str = Field(..., description="Caller E.164, e.g. +919571025342")


class OrderStatusIn(BaseModel):
    order_id: str = Field(..., description="e.g. ORD-1006")
    phone: str | None = Field(
        default=None,
        description="Optional caller phone for ownership check",
    )


def _retailer_context(phone: str) -> dict[str, Any]:
    retailer = get_retailer_by_phone(phone)
    if retailer is None:
        raise HTTPException(
            status_code=404,
            detail=f"No retailer found for phone {phone}",
        )
    open_orders = get_open_orders_summary(retailer["id"])
    # Newest open first already; also expose latest order_id for voice
    latest_open = open_orders[0]["order_id"] if open_orders else None
    return {
        "found": True,
        "retailer_id": retailer["id"],
        "shop_name": retailer["shop_name"],
        "contact_name": retailer["contact_name"],
        "phone": retailer["phone"],
        "preferred_language": retailer.get("preferred_language"),
        "open_orders": open_orders,
        "open_order_count": len(open_orders),
        "latest_open_order_id": latest_open,
        "open_orders_summary": "; ".join(
            f"{o['order_id']} ({o['status']}, {o.get('eta_text') or 'ETA TBD'})"
            for o in open_orders
        )
        or "NONE",
    }


@router.post("/retailers/lookup-by-phone")
def post_lookup_by_phone(body: LookupByPhoneIn) -> dict[str, Any]:
    """Bolna tool: identify shop from caller CLI."""
    return _retailer_context(body.phone)


@router.post("/orders/status")
def post_order_status(body: OrderStatusIn) -> dict[str, Any]:
    """
    Bolna tool: speak status + ETA for one order_id.

    Ownership: if phone is sent, require it to match the order's retailer
    (by retailer phone OR order.phone last-10).
    """
    try:
        return get_order_status(body.order_id, phone=body.phone)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/inbound/caller-context")
def get_caller_context(
    contact_number: str = Query(
        ...,
        description="Bolna Identify Callers passes contact_number",
    ),
    agent_id: str | None = None,
    execution_id: str | None = None,
) -> dict[str, Any]:
    """
    Bolna 'Use your internal APIs' identify-callers endpoint (GET, <3s).

    Top-level keys become {{shop_name}}, {{retailer_id}}, etc. in prompts.
    Unknown numbers return found=false with empty fields (call still proceeds).
    """
    _ = agent_id, execution_id  # accepted for Bolna query signature
    retailer = get_retailer_by_phone(contact_number)
    if retailer is None:
        return {
            "found": False,
            "shop_name": "",
            "contact_name": "",
            "retailer_id": "",
            "phone": contact_number,
            "open_order_count": 0,
            "latest_open_order_id": "",
            "open_orders_summary": "NONE",
            "caller_known": "no",
        }
    ctx = _retailer_context(contact_number)
    ctx["caller_known"] = "yes"
    # Flatten for prompt vars (Bolna injects top-level keys)
    return {
        "found": True,
        "caller_known": "yes",
        "shop_name": ctx["shop_name"],
        "contact_name": ctx["contact_name"],
        "retailer_id": ctx["retailer_id"],
        "phone": ctx["phone"],
        "preferred_language": ctx.get("preferred_language") or "hi",
        "open_order_count": ctx["open_order_count"],
        "latest_open_order_id": ctx["latest_open_order_id"] or "",
        "open_orders_summary": ctx["open_orders_summary"],
    }


@router.get("/retailers/{retailer_id}/open-orders")
def list_open_orders(retailer_id: str) -> dict[str, Any]:
    """Helper for console / smoke tests."""
    orders = [
        order_status_payload(o)
        for o in get_orders_for_retailer(retailer_id)
        if o.get("status")
        in {
            "confirmed",
            "packed",
            "dispatched",
            "out_for_delivery",
            "partial",
        }
    ]
    return {"retailer_id": retailer_id, "count": len(orders), "orders": orders}
