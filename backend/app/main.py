"""
TradeCall API + ops console (Phase D).
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.middleware_log import RequestLogMiddleware
from app.routers import (
    agents,
    callbacks,
    calls,
    debug,
    inbound_tools,
    orders,
    retailers,
    stock,
    whatsapp,
)
from app.store import load_db

STATIC_DIR = Path(__file__).parent / "static"
CONSOLE_DIR = STATIC_DIR / "console"

app = FastAPI(title="TradeCall API", version="0.4.0")
app.add_middleware(RequestLogMiddleware)


@app.on_event("startup")
def on_startup():
    db = load_db()
    print(
        f"[TradeCall] Loaded seed: "
        f"{len(db['retailers'])} retailers, {len(db['skus'])} skus, "
        f"{len(db['orders'])} orders"
    )


app.include_router(retailers.router)
app.include_router(stock.router)
app.include_router(orders.router)
app.include_router(whatsapp.router)
app.include_router(inbound_tools.router)
app.include_router(calls.router)
app.include_router(callbacks.router)
app.include_router(agents.router)
app.include_router(debug.router)

if CONSOLE_DIR.is_dir():
    app.mount("/console", StaticFiles(directory=str(CONSOLE_DIR), html=True), name="console")


@app.get("/")
def root():
    index = CONSOLE_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"service": "tradecall-api", "console": "/console/"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "tradecall-api",
        "phase": "product-agents",
        "console": "/console/",
        "agents": "/v1/agents",
    }
