"""Callback dispositions — Phase E busy→callback demo."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.store import list_callbacks, log_callback

router = APIRouter(prefix="/v1/callbacks", tags=["callbacks"])


class CallbackIn(BaseModel):
    retailer_id: str | None = None
    phone: str | None = None
    shop_name: str | None = None
    callback_slot: str = Field(
        default="n/a",
        description="e.g. shaam 5 baje; use 'do_not_call' for DNC",
    )
    reason: str | None = Field(default="busy")
    disposition: str | None = Field(
        default=None,
        description="callback | dnc | retained",
    )


@router.post("")
def post_callback(body: CallbackIn) -> dict[str, Any]:
    row = log_callback(
        retailer_id=body.retailer_id,
        phone=body.phone,
        shop_name=body.shop_name,
        callback_slot=body.callback_slot or "n/a",
        reason=body.reason,
        disposition=body.disposition,
    )
    return {"ok": True, "callback": row}


@router.get("")
def get_callbacks() -> dict[str, Any]:
    rows = list_callbacks()
    return {"count": len(rows), "callbacks": rows}
