"""Outbound call trigger for the ops console → Bolna."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.store import get_last_order, get_retailer

router = APIRouter(prefix="/v1/calls", tags=["calls"])

# Avoid zoneinfo/tzdata (often missing on Windows venvs)
_IST = timezone(timedelta(hours=5, minutes=30))

# Voice_Ops/bolna/outbound/AGENT_ID.txt (backend/app/routers → parents[3] = Voice_Ops)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_AGENT_ID_FILE = _REPO_ROOT / "bolna" / "outbound" / "AGENT_ID.txt"


class OutboundCallIn(BaseModel):
    retailer_id: str = Field(..., description="e.g. R01")
    phone: str | None = Field(
        default=None,
        description="Override dial number; defaults to retailer.phone",
    )


def _agent_id() -> str:
    if not _AGENT_ID_FILE.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Missing outbound AGENT_ID at {_AGENT_ID_FILE}",
        )
    return _AGENT_ID_FILE.read_text(encoding="utf-8").strip()


def _last_order_summary(retailer_id: str) -> str:
    order = get_last_order(retailer_id)
    if order is None:
        return "NONE"
    summary = ", ".join(
        f"{i.get('qty')} {i.get('unit')} {i.get('name')}" for i in order.get("items", [])
    )
    return f"Last order {order.get('order_id')}: {summary}"


@router.post("/outbound")
def trigger_outbound(body: OutboundCallIn) -> dict[str, Any]:
    """
    POST /v1/calls/outbound

    Places a Bolna outbound call for the selected retailer.
    Requires BOLNA_API_KEY in the server environment.
    """
    key = os.environ.get("BOLNA_API_KEY", "").strip()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="BOLNA_API_KEY not set on the API process — set User env and restart uvicorn",
        )

    retailer = get_retailer(body.retailer_id)
    if retailer is None:
        raise HTTPException(status_code=404, detail=f"Retailer {body.retailer_id} not found")

    to = (body.phone or retailer.get("phone") or "").strip()
    if not to:
        raise HTTPException(status_code=400, detail="No phone number for retailer")

    week = datetime.now(_IST).strftime("%d %b")
    payload = {
        "agent_id": _agent_id(),
        "recipient_phone_number": to,
        "user_data": {
            "retailer_id": retailer["id"],
            "retailer_name": retailer.get("contact_name") or "",
            "shop_name": retailer.get("shop_name") or "",
            "retailer_phone": to,
            "distributor_name": "Bharat Hardware Distributors",
            "week_label": week,
            "preferred_language": retailer.get("preferred_language") or "hi",
            "timezone": "Asia/Kolkata",
            "flow": "outbound",
            "last_order_summary": _last_order_summary(retailer["id"]),
        },
    }

    req = urllib.request.Request(
        "https://api.bolna.ai/call",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise HTTPException(status_code=502, detail=f"Bolna HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise HTTPException(status_code=502, detail=f"Bolna unreachable: {e}") from e

    return {
        "ok": True,
        "retailer_id": retailer["id"],
        "shop_name": retailer.get("shop_name"),
        "dialed": to,
        "execution_id": data.get("execution_id") or data.get("run_id"),
        "bolna": data,
    }
