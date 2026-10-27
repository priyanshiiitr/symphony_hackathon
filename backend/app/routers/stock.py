"""POST /v1/stock/check — supports flat Bolna params OR items list."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.store import check_stock

router = APIRouter(prefix="/v1", tags=["stock"])


class StockItemIn(BaseModel):
    sku_or_name: str
    qty: int = Field(..., ge=1)


class StockCheckIn(BaseModel):
    retailer_id: str | None = None
    # Flat (preferred for Bolna)
    sku_or_name: str | None = None
    qty: int | str | None = None
    # Nested / string forms
    items: list[StockItemIn] | None = None
    items_json: str | None = None

    @model_validator(mode="after")
    def normalize(self) -> "StockCheckIn":
        if self.items:
            return self
        if self.items_json:
            parsed = json.loads(self.items_json)
            self.items = [StockItemIn.model_validate(row) for row in parsed]
            return self
        if self.sku_or_name is not None and self.qty is not None:
            q = int(self.qty)
            self.items = [StockItemIn(sku_or_name=self.sku_or_name, qty=q)]
            return self
        raise ValueError("Provide sku_or_name+qty, or items, or items_json")


@router.post("/stock/check")
def stock_check(body: StockCheckIn) -> dict[str, Any]:
    if not body.items:
        raise HTTPException(status_code=400, detail="No items")
    result = check_stock([i.model_dump() for i in body.items])
    return {"retailer_id": body.retailer_id, **result}
