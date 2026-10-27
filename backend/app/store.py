"""
In-memory store backed by seed.json.

Why this exists:
  Bolna tools and our dashboard need a place that "remembers" retailers,
  SKUs, and (later) orders. For Phase A we use a JSON file + RAM:
  - On startup we load seed.json into Python dicts
  - Reads are fast (from memory)
  - Later steps will append orders into this same structure

This is NOT production Postgres. It is a teaching mock ERP.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# India-ish offset for demo timestamps / ETA text
_IST = timezone(timedelta(hours=5, minutes=30))

# Path to seed file next to this package: app/data/seed.json
_DATA_PATH = Path(__file__).parent / "data" / "seed.json"

# Module-level state = our "database" while the server process is alive.
# Survives across HTTP requests, wiped if you restart uvicorn (until we
# write orders back to disk in a later step).
_db: dict[str, Any] | None = None


def load_db() -> dict[str, Any]:
    """Load seed.json once; reuse the same dict for every request."""
    global _db
    if _db is None:
        with _DATA_PATH.open(encoding="utf-8") as f:
            _db = json.load(f)
    return _db


def get_retailers() -> list[dict[str, Any]]:
    return list(load_db()["retailers"])


def get_retailer(retailer_id: str) -> dict[str, Any] | None:
    """Return one retailer by id, or None if not found."""
    for r in load_db()["retailers"]:
        if r["id"] == retailer_id:
            return r
    return None


def normalize_phone(phone: str) -> str:
    """
    Keep digits only so '+91 98765-43210' and '919876543210' match.

    Bolna sends E.164; humans type many formats — we compare on digits.
    """
    return "".join(ch for ch in phone if ch.isdigit())


def get_retailer_by_phone(phone: str) -> dict[str, Any] | None:
    """Inbound identify: caller CLI → retailer row."""
    target = normalize_phone(phone)
    if not target:
        return None
    for r in load_db()["retailers"]:
        if normalize_phone(r.get("phone", "")) == target:
            return r
        # Also allow last-10 match (India mobiles often compared that way)
        stored = normalize_phone(r.get("phone", ""))
        if len(target) >= 10 and len(stored) >= 10 and target[-10:] == stored[-10:]:
            return r
    return None


# Statuses still "in flight" for inbound open-order lists
_OPEN_STATUSES = {
    "confirmed",
    "packed",
    "dispatched",
    "out_for_delivery",
    "partial",
}

_STATUS_LABELS = {
    "confirmed": {"en": "confirmed", "hi": "confirm ho gaya hai"},
    "packed": {"en": "packed", "hi": "pack ho gaya hai"},
    "dispatched": {"en": "dispatched", "hi": "dispatch ho gaya hai"},
    "out_for_delivery": {"en": "out for delivery", "hi": "delivery ke liye nikal chuka hai"},
    "delivered": {"en": "delivered", "hi": "deliver ho chuka hai"},
    "partial": {"en": "partially dispatched", "hi": "kuch saman aa gaya, kuch pending hai"},
    "cancelled": {"en": "cancelled", "hi": "cancel ho gaya hai"},
}


def get_orders_for_retailer(retailer_id: str) -> list[dict[str, Any]]:
    """All orders for one shop, newest first (by created_at string)."""
    orders = [
        o for o in load_db()["orders"] if o["retailer_id"] == retailer_id
    ]
    orders.sort(key=lambda o: o.get("created_at", ""), reverse=True)
    return orders


def get_open_orders_summary(retailer_id: str) -> list[dict[str, Any]]:
    """Compact list for inbound: which orders can we talk about?"""
    out: list[dict[str, Any]] = []
    for o in get_orders_for_retailer(retailer_id):
        if o.get("status") in _OPEN_STATUSES:
            out.append(
                {
                    "order_id": o["order_id"],
                    "status": o["status"],
                    "eta_text": o.get("eta_text"),
                }
            )
    return out


def get_last_order(retailer_id: str) -> dict[str, Any] | None:
    """
    Most recent order for a retailer — what the outbound agent will recall.

    Returns None if this shop has never ordered (e.g. R05 in seed).
    """
    orders = get_orders_for_retailer(retailer_id)
    return orders[0] if orders else None


def get_skus() -> list[dict[str, Any]]:
    return list(load_db()["skus"])


def get_sku(sku_code: str) -> dict[str, Any] | None:
    for s in load_db()["skus"]:
        if s["sku"] == sku_code:
            return s
    return None


def resolve_sku(sku_or_name: str) -> dict[str, Any] | None:
    """
    Map spoken/typed text → one catalog SKU.

    Step 4 matching (simple, deterministic):
      1. Exact SKU code (e.g. MCB-32A)
      2. Exact name (case-insensitive)
      3. Alias hit (e.g. "mcb batti wala", "taar")

    Phase G will upgrade this to real fuzzy matching.
    """
    q = sku_or_name.strip().lower()
    if not q:
        return None

    # Spoken / ASR noise common on Hindi calls
    q = (
        q.replace("mca", "mcb")
        .replace("mcp", "mcb")
        .replace("mps", "amp")
        .replace("amps", "amp")
        .replace("battis", "32")
        .replace("battees", "32")
        .replace("बत्तीस", "32")
    )

    skus = load_db()["skus"]

    for s in skus:
        if s["sku"].lower() == q:
            return s

    for s in skus:
        if s["name"].lower() == q:
            return s

    for s in skus:
        aliases = [a.lower() for a in s.get("aliases", [])]
        if q in aliases:
            return s

    # Soft contains: query inside alias/name (helps "32 amp mcb" vs "mcb 32")
    for s in skus:
        haystacks = [s["name"].lower(), s["sku"].lower(), *s.get("aliases", [])]
        for h in haystacks:
            h = h.lower()
            if q in h or h in q:
                return s

    return None


def check_stock(items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    For each requested line, see warehouse qty vs asked qty.

    Input item shape: { "sku_or_name": str, "qty": int }
    Output includes per-line status + optional substitute from seed.
    """
    lines: list[dict[str, Any]] = []
    all_available = True

    for raw in items:
        sku_or_name = str(raw.get("sku_or_name", "")).strip()
        try:
            qty = int(raw.get("qty", 0))
        except (TypeError, ValueError):
            qty = 0

        matched = resolve_sku(sku_or_name)
        if matched is None:
            all_available = False
            lines.append(
                {
                    "requested": sku_or_name,
                    "qty_requested": qty,
                    "status": "not_found",
                    "available": 0,
                    "sku": None,
                    "name": None,
                    "unit": None,
                    "substitute": None,
                }
            )
            continue

        available = int(matched.get("stock_qty", 0))
        if available >= qty and qty > 0:
            status = "available"
        elif available <= 0:
            status = "out_of_stock"
            all_available = False
        else:
            status = "partial"
            all_available = False

        substitute = None
        sub_code = matched.get("substitute_sku")
        if status != "available" and sub_code:
            sub = get_sku(sub_code)
            if sub:
                substitute = {
                    "sku": sub["sku"],
                    "name": sub["name"],
                    "unit": sub["unit"],
                    "available": sub.get("stock_qty", 0),
                }

        lines.append(
            {
                "requested": sku_or_name,
                "qty_requested": qty,
                "status": status,
                "available": available,
                "sku": matched["sku"],
                "name": matched["name"],
                "unit": matched["unit"],
                "substitute": substitute,
            }
        )

    return {"all_available": all_available, "lines": lines}


def get_order(order_id: str) -> dict[str, Any] | None:
    for o in load_db()["orders"]:
        if o["order_id"] == order_id:
            return o
    return None


def _next_order_id() -> str:
    """
    Scan existing ORD-#### ids and return the next one.

    Seed has ORD-1001 … ORD-1005 → first create becomes ORD-1006.
    """
    highest = 1000
    for o in load_db()["orders"]:
        m = re.match(r"ORD-(\d+)$", o.get("order_id", ""))
        if m:
            highest = max(highest, int(m.group(1)))
    return f"ORD-{highest + 1}"


def create_order(
    retailer_id: str,
    items: list[dict[str, Any]],
    *,
    confirmed_by_voice: bool = True,
    call_execution_id: str | None = None,
) -> dict[str, Any]:
    """
    Persist a new order in memory (append to db['orders']).

    Steps:
      1. Retailer must exist
      2. Each line must resolve to a known SKU
      3. Build order with status=confirmed + provisional ETA (+2 days)
      4. Optionally reduce warehouse stock_qty (so next stock check sees it)
      5. Return the new order dict

    NOTE: Memory only — restart uvicorn and seed reloads from disk,
    so newly created orders disappear unless we add disk save later.
    """
    retailer = get_retailer(retailer_id)
    if retailer is None:
        raise ValueError(f"Retailer {retailer_id} not found")

    resolved_items: list[dict[str, Any]] = []
    for raw in items:
        sku_or_name = str(raw.get("sku_or_name", "")).strip()
        try:
            qty = int(raw.get("qty", 0))
        except (TypeError, ValueError):
            qty = 0
        if qty < 1:
            raise ValueError(f"Invalid qty for '{sku_or_name}'")

        matched = resolve_sku(sku_or_name)
        if matched is None:
            raise ValueError(f"Unknown product: {sku_or_name}")

        resolved_items.append(
            {
                "sku": matched["sku"],
                "name": matched["name"],
                "qty": qty,
                "unit": matched["unit"],
            }
        )

    now = datetime.now(_IST)
    eta_date = (now + timedelta(days=2)).date()
    order_id = _next_order_id()

    order: dict[str, Any] = {
        "order_id": order_id,
        "retailer_id": retailer_id,
        "phone": retailer["phone"],
        "created_at": now.isoformat(),
        "status": "confirmed",
        "eta_date": eta_date.isoformat(),
        "eta_text": f"Expected delivery by {eta_date.strftime('%d %b')} afternoon",
        "total_amount": None,
        "items": resolved_items,
        "confirmed_by_voice": confirmed_by_voice,
        "call_execution_id": call_execution_id,
    }

    db = load_db()
    db["orders"].append(order)

    # Reduce stock so create → stock-check feels real in demos.
    for line in resolved_items:
        sku_row = get_sku(line["sku"])
        if sku_row is not None:
            sku_row["stock_qty"] = max(0, int(sku_row.get("stock_qty", 0)) - line["qty"])

    return order


def order_status_payload(order: dict[str, Any]) -> dict[str, Any]:
    """Shape an order for the inbound voice agent (status + ETA + short item list)."""
    status = order.get("status", "confirmed")
    labels = _STATUS_LABELS.get(status, {"en": status, "hi": status})
    retailer = get_retailer(order["retailer_id"])
    items = order.get("items", [])
    items_summary = ", ".join(
        f"{i.get('qty')} {i.get('unit')} {i.get('name')}" for i in items
    )
    return {
        "order_id": order["order_id"],
        "retailer_id": order["retailer_id"],
        "shop_name": retailer["shop_name"] if retailer else None,
        "phone": order.get("phone"),
        "status": status,
        "status_label_en": labels["en"],
        "status_label_hi": labels["hi"],
        "eta_date": order.get("eta_date"),
        "eta_text": order.get("eta_text"),
        "items_summary": items_summary,
        "items": items,
        "last_updated": order.get("updated_at") or order.get("created_at"),
    }


def get_order_status(
    order_id: str,
    *,
    phone: str | None = None,
) -> dict[str, Any]:
    """
    Lookup status for inbound.

    If phone is provided, require ownership via:
      1) caller matches the order's retailer (by-phone → retailer_id), OR
      2) last-10 digit match on order.phone
    so guessing ORD-ids from a random number fails, but demo phone remaps work.
    """
    order = get_order(order_id)
    if order is None:
        raise ValueError(f"Order {order_id} not found")

    if phone:
        caller = normalize_phone(phone)
        order_phone = normalize_phone(order.get("phone", ""))
        retailer = get_retailer_by_phone(phone)
        owns_via_retailer = (
            retailer is not None and retailer["id"] == order.get("retailer_id")
        )
        owns_via_order_phone = (
            len(caller) >= 10
            and len(order_phone) >= 10
            and caller[-10:] == order_phone[-10:]
        )
        if not (owns_via_retailer or owns_via_order_phone):
            raise PermissionError("Phone does not match this order")

    return order_status_payload(order)


def update_order_status(
    order_id: str,
    status: str,
    *,
    eta_text: str | None = None,
    eta_date: str | None = None,
) -> dict[str, Any]:
    """
    Demo scrubber: advance packed → dispatched → … on the dashboard.
    Mutates the in-memory order dict in place.
    """
    if status not in _STATUS_LABELS:
        raise ValueError(
            f"Invalid status '{status}'. Allowed: {', '.join(sorted(_STATUS_LABELS))}"
        )

    order = get_order(order_id)
    if order is None:
        raise ValueError(f"Order {order_id} not found")

    order["status"] = status
    order["updated_at"] = datetime.now(_IST).isoformat()
    if eta_text is not None:
        order["eta_text"] = eta_text
    if eta_date is not None:
        order["eta_date"] = eta_date

    return order_status_payload(order)


def send_whatsapp(
    retailer_phone: str,
    *,
    order_id: str | None = None,
    summary_text: str,
) -> dict[str, Any]:
    """
    Mock WhatsApp send — does NOT talk to Meta/AiSensy.

    Appends a message to db['whatsapp_outbox'] so the ops console can prove
    "confirmation was sent" after a call. Real WA can replace this later.
    """
    msg = {
        "id": f"WA-{len(load_db()['whatsapp_outbox']) + 1:04d}",
        "to": retailer_phone,
        "order_id": order_id,
        "summary_text": summary_text,
        "channel": "whatsapp_mock",
        "status": "sent",
        "sent_at": datetime.now(_IST).isoformat(),
    }
    load_db()["whatsapp_outbox"].append(msg)
    return msg


def list_whatsapp_outbox() -> list[dict[str, Any]]:
    """Newest first — dashboard reads this panel."""
    box = list(load_db()["whatsapp_outbox"])
    box.sort(key=lambda m: m.get("sent_at", ""), reverse=True)
    return box

