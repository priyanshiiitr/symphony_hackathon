"""
WhatsApp mock routes — Phase A Step 7.

  POST /v1/whatsapp/send
  GET  /v1/whatsapp/outbox
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.store import list_whatsapp_outbox, send_whatsapp

router = APIRouter(prefix="/v1/whatsapp", tags=["whatsapp"])


class WhatsAppSendIn(BaseModel):
    """
    Body after a successful order (Bolna workflow or create_order follow-up).
    """

    retailer_phone: str = Field(..., description="E.164 phone, e.g. +919876543210")
    summary_text: str = Field(..., description="Human-readable order confirmation")
    order_id: str | None = None


@router.post("/send")
def post_whatsapp(body: WhatsAppSendIn) -> dict[str, Any]:
    """
    POST /v1/whatsapp/send

    Fake send: store message in outbox with status=sent.
    Later: swap internals for AiSensy/Meta without changing this contract.
    """
    msg = send_whatsapp(
        body.retailer_phone,
        order_id=body.order_id,
        summary_text=body.summary_text,
    )
    return {"ok": True, "message": msg}


@router.get("/outbox")
def get_outbox() -> dict[str, Any]:
    """
    GET /v1/whatsapp/outbox

    Demo proof panel — every "sent" confirmation listed newest first.
    """
    messages = list_whatsapp_outbox()
    return {"count": len(messages), "messages": messages}
