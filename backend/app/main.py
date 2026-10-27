"""
TradeCall API entry point.

Phase A Step 7: + WhatsApp mock outbox (send + list).
"""

from fastapi import FastAPI

from app.middleware_log import RequestLogMiddleware
from app.routers import debug, inbound_tools, orders, retailers, stock, whatsapp
from app.store import load_db

app = FastAPI(title="TradeCall API", version="0.2.0")
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
app.include_router(debug.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "tradecall-api",
        "phase": "C-inbound",
    }
