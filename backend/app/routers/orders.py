"""Order routes — flat Bolna params + list forms."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from app.store import create_order, get_order, get_order_status, update_order_status

router = APIRouter(prefix="/v1", tags=["orders"])


class OrderItemIn(BaseModel):
    sku_or_name: str
    qty: int = Field(..., ge=1)


class CreateOrderIn(BaseModel):
    retailer_id: str
    sku_or_name: str | None = None
    qty: int | str | None = None
    items: list[OrderItemIn] | None = None
    items_json: str | None = None
    confirmed_by_voice: bool | str = True
    call_execution_id: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "CreateOrderIn":
        if isinstance(self.confirmed_by_voice, str):
            self.confirmed_by_voice = self.confirmed_by_voice.lower() in (
                "1",
                "true",
                "yes",
            )
        if self.items:
            return self
        if self.items_json:
            parsed = json.loads(self.items_json)
            self.items = [OrderItemIn.model_validate(row) for row in parsed]
            return self
        if self.sku_or_name is not None and self.qty is not None:
            self.items = [
                OrderItemIn(sku_or_name=self.sku_or_name, qty=int(self.qty))
            ]
            return self
        raise ValueError("Provide sku_or_name+qty, or items, or items_json")


class UpdateStatusIn(BaseModel):
    status: str
    eta_text: str | None = None
    eta_date: str | None = None


@router.post("/orders")
def post_order(body: CreateOrderIn) -> dict[str, Any]:
    if not body.items:
        raise HTTPException(status_code=400, detail="No items")
    try:
        order = create_order(
            body.retailer_id,
            [i.model_dump() for i in body.items],
            confirmed_by_voice=bool(body.confirmed_by_voice),
            call_execution_id=body.call_execution_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "order_id": order["order_id"],
        "status": order["status"],
        "eta_date": order["eta_date"],
        "eta_text": order["eta_text"],
        "items": order["items"],
        "retailer_id": order["retailer_id"],
        "phone": order["phone"],
    }


@router.get("/orders/{order_id}/status")
def read_order_status(
    order_id: str,
    phone: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        return get_order_status(order_id, phone=phone)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.patch("/orders/{order_id}/status")
def patch_order_status(order_id: str, body: UpdateStatusIn) -> dict[str, Any]:
    try:
        return update_order_status(
            order_id,
            body.status,
            eta_text=body.eta_text,
            eta_date=body.eta_date,
        )
    except ValueError as exc:
        detail = str(exc)
        code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=code, detail=detail) from exc


@router.get("/orders/{order_id}")
def read_order(order_id: str) -> dict[str, Any]:
    order = get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return order
