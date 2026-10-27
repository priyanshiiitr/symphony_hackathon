"""Log every request so we can see Bolna tool hits in the uvicorn console."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        started = time.perf_counter()
        body_preview = ""
        if request.method in ("POST", "PATCH", "PUT"):
            raw = await request.body()
            body_preview = raw.decode("utf-8", errors="replace")[:500]

            # Starlette consumes body — re-inject for FastAPI
            async def receive():
                return {"type": "http.request", "body": raw, "more_body": False}

            request = Request(request.scope, receive)

        response = await call_next(request)
        ms = (time.perf_counter() - started) * 1000
        print(
            f"[REQ] {request.method} {request.url.path}{('?' + request.url.query) if request.url.query else ''} "
            f"→ {response.status_code} ({ms:.0f}ms)"
            + (f" body={body_preview}" if body_preview else "")
        )
        return response
