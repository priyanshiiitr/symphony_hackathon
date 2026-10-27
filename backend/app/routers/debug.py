"""Catch-all debug for Bolna tool payloads."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/v1/debug", tags=["debug"])


@router.api_route("/echo", methods=["GET", "POST", "PUT", "PATCH"])
async def echo(request: Request) -> dict[str, Any]:
    raw = await request.body()
    text = raw.decode("utf-8", errors="replace")
    print(f"[DEBUG ECHO] {request.method} headers={dict(request.headers)}")
    print(f"[DEBUG ECHO] body={text}")
    return {
        "ok": True,
        "method": request.method,
        "path": str(request.url.path),
        "query": str(request.url.query),
        "body_text": text,
    }
