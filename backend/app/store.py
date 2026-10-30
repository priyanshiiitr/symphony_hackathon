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


def _ensure_schedules() -> dict[str, Any]:
    db = load_db()
    if "call_schedules" not in db:
        # Demo seeds so the dashboard timer is visible immediately
        now = datetime.now(_IST)
        db["call_schedules"] = {
            "R01": {
                "retailer_id": "R01",
                "next_call_at": (now + timedelta(hours=2)).isoformat(),
                "note": "Weekly order window",
                "cadence": "custom",
                "updated_at": now.isoformat(),
            },
            "R02": {
                "retailer_id": "R02",
                "next_call_at": (now + timedelta(minutes=45)).isoformat(),
                "note": "Prefer late morning",
                "cadence": "custom",
                "updated_at": now.isoformat(),
            },
        }
    return db["call_schedules"]


def _parse_iso_ist(value: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("next_call_at is required")
    # datetime-local from browser: 2026-10-29T17:30
    if len(raw) == 16 and "T" in raw and raw.count(":") == 1:
        raw = raw + ":00"
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_IST)
    return dt.astimezone(_IST)


def schedule_payload(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Enrich a schedule row with countdown fields for the ops console."""
    if not row or not row.get("next_call_at"):
        return None
    try:
        when = _parse_iso_ist(str(row["next_call_at"]))
    except ValueError:
        return None
    now = datetime.now(_IST)
    seconds = int((when - now).total_seconds())
    if seconds > 0:
        status = "upcoming"
    elif seconds > -3600:
        status = "due"
    else:
        status = "overdue"
    return {
        "retailer_id": row.get("retailer_id"),
        "next_call_at": when.isoformat(),
        "note": row.get("note") or "",
        "cadence": row.get("cadence") or "custom",
        "updated_at": row.get("updated_at"),
        "seconds_until": seconds,
        "status": status,
        "label": when.strftime("%d %b %I:%M %p"),
    }


def get_call_schedule(retailer_id: str) -> dict[str, Any] | None:
    row = _ensure_schedules().get(retailer_id)
    return schedule_payload(row)


def set_call_schedule(
    retailer_id: str,
    *,
    next_call_at: str,
    note: str | None = None,
    cadence: str | None = None,
) -> dict[str, Any]:
    if get_retailer(retailer_id) is None:
        raise ValueError(f"Retailer {retailer_id} not found")
    when = _parse_iso_ist(next_call_at)
    row = {
        "retailer_id": retailer_id,
        "next_call_at": when.isoformat(),
        "note": (note or "").strip(),
        "cadence": (cadence or "custom").strip() or "custom",
        "updated_at": datetime.now(_IST).isoformat(),
    }
    _ensure_schedules()[retailer_id] = row
    return schedule_payload(row)  # type: ignore[return-value]


def clear_call_schedule(retailer_id: str) -> None:
    _ensure_schedules().pop(retailer_id, None)


def list_due_schedules() -> list[dict[str, Any]]:
    """Retailers whose call window is due/overdue — for the dashboard strip."""
    out: list[dict[str, Any]] = []
    for rid, row in list(_ensure_schedules().items()):
        payload = schedule_payload({**row, "retailer_id": rid})
        if payload and payload["status"] in {"due", "overdue"}:
            retailer = get_retailer(rid)
            payload["shop_name"] = (retailer or {}).get("shop_name")
            out.append(payload)
    out.sort(key=lambda x: x.get("seconds_until", 0))
    return out


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


def list_orders(*, retailer_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Newest-first order list for the ops console."""
    orders = list(load_db()["orders"])
    if retailer_id:
        orders = [o for o in orders if o["retailer_id"] == retailer_id]
    orders.sort(key=lambda o: o.get("created_at", ""), reverse=True)
    return orders[: max(1, limit)]


def status_pipeline() -> list[str]:
    """Demo scrubber order (excludes cancelled)."""
    return [
        "confirmed",
        "packed",
        "dispatched",
        "out_for_delivery",
        "delivered",
    ]


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

    items_summary = ", ".join(
        f"{i['qty']} {i['unit']} {i['name']}" for i in resolved_items
    )

    # Link to the open outbound call so the dashboard can show ORD-… when the call ends.
    attach_order_to_call(
        retailer_id=retailer_id,
        order_id=order_id,
        call_execution_id=call_execution_id,
        items_summary=items_summary,
    )

    # Always push a mock WhatsApp confirmation when an order is booked
    # (Bolna may also call /whatsapp/send — send_whatsapp is idempotent per order_id).
    send_whatsapp(
        retailer["phone"],
        order_id=order_id,
        summary_text=(
            f"TradeCall: Order {order_id} confirm - {items_summary}. "
            f"{order.get('eta_text') or ''}"
        ).strip(),
    )

    return order


def _ensure_call_sessions() -> list[dict[str, Any]]:
    db = load_db()
    if "call_sessions" not in db:
        db["call_sessions"] = []
    return db["call_sessions"]


def start_call_session(
    *,
    execution_id: str,
    retailer_id: str,
    shop_name: str | None,
    phone: str | None,
) -> dict[str, Any]:
    """Record an outbound dial so the console can poll for the resulting order."""
    now = datetime.now(_IST)
    # Close older open dials for this shop — they aren't "waiting for order" anymore.
    for s in _ensure_call_sessions():
        if (
            s.get("retailer_id") == retailer_id
            and s.get("status") == "in_progress"
            and not s.get("order_id")
        ):
            s["status"] = "no_order"
            s["ended_at"] = now.isoformat()
            s["updated_at"] = s["ended_at"]

    row = {
        "execution_id": execution_id,
        "retailer_id": retailer_id,
        "shop_name": shop_name or "",
        "phone": phone or "",
        "status": "in_progress",
        "order_id": None,
        "items_summary": None,
        "started_at": now.isoformat(),
        "ended_at": None,
        "updated_at": now.isoformat(),
    }
    _ensure_call_sessions().insert(0, row)
    # Keep last 40 only
    sessions = _ensure_call_sessions()
    del sessions[40:]
    return row


def attach_order_to_call(
    *,
    retailer_id: str,
    order_id: str,
    call_execution_id: str | None = None,
    items_summary: str | None = None,
) -> dict[str, Any] | None:
    """Bind a newly created order to the matching open call session."""
    sessions = _ensure_call_sessions()
    target: dict[str, Any] | None = None
    if call_execution_id:
        for s in sessions:
            if s.get("execution_id") == call_execution_id:
                target = s
                break
    if target is None:
        for s in sessions:
            if (
                s.get("retailer_id") == retailer_id
                and s.get("status") == "in_progress"
                and not s.get("order_id")
            ):
                target = s
                break
    if target is None:
        # Still surface on dashboard even if Call now wasn't used (manual tool test)
        target = {
            "execution_id": call_execution_id or f"local-{order_id}",
            "retailer_id": retailer_id,
            "shop_name": (get_retailer(retailer_id) or {}).get("shop_name") or "",
            "phone": (get_retailer(retailer_id) or {}).get("phone") or "",
            "status": "completed",
            "started_at": datetime.now(_IST).isoformat(),
        }
        sessions.insert(0, target)

    target["order_id"] = order_id
    target["items_summary"] = items_summary
    target["status"] = "completed"
    target["ended_at"] = datetime.now(_IST).isoformat()
    target["updated_at"] = target["ended_at"]
    return target


def get_call_session(execution_id: str) -> dict[str, Any] | None:
    for s in _ensure_call_sessions():
        if s.get("execution_id") == execution_id:
            return dict(s)
    return None


def list_call_sessions(*, limit: int = 20) -> list[dict[str, Any]]:
    _close_stale_sessions()
    rows = list(_ensure_call_sessions())[: max(1, limit)]
    return [dict(r) for r in rows]


def _parse_session_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_IST)
        return dt.astimezone(_IST)
    except ValueError:
        return None


def _order_already_linked(order_id: str) -> bool:
    for s in _ensure_call_sessions():
        if s.get("order_id") == order_id and s.get("status") == "completed":
            return True
    return False


def _link_order_if_ready(session: dict[str, Any]) -> bool:
    """If an order was created for this retailer after dial, attach it. Returns True if linked."""
    if session.get("order_id"):
        return True
    started = _parse_session_time(session.get("started_at"))
    if started is None:
        return False
    for order in get_orders_for_retailer(session["retailer_id"]):
        created = _parse_session_time(order.get("created_at"))
        if created is None or created < started:
            continue
        oid = order["order_id"]
        # Don't steal an order already credited to another completed call
        if _order_already_linked(oid):
            continue
        session["order_id"] = oid
        session["items_summary"] = ", ".join(
            f"{i.get('qty')} {i.get('unit')} {i.get('name')}"
            for i in order.get("items", [])
        )
        session["status"] = "completed"
        session["ended_at"] = datetime.now(_IST).isoformat()
        session["updated_at"] = session["ended_at"]
        return True
    return False


_STALE_CALL_MINUTES = 8


def _close_stale_sessions() -> None:
    """Mark long-running dials with no order as finished (no_order)."""
    now = datetime.now(_IST)
    for s in _ensure_call_sessions():
        if s.get("status") != "in_progress" or s.get("order_id"):
            continue
        started = _parse_session_time(s.get("started_at"))
        if started is None:
            continue
        if (now - started) > timedelta(minutes=_STALE_CALL_MINUTES):
            s["status"] = "no_order"
            s["ended_at"] = now.isoformat()
            s["updated_at"] = s["ended_at"]


def refresh_call_session(execution_id: str) -> dict[str, Any] | None:
    """Poll helper: detect order booked mid-call without requiring Bolna webhooks."""
    _close_stale_sessions()
    for s in _ensure_call_sessions():
        if s.get("execution_id") == execution_id:
            if s.get("status") == "in_progress":
                _link_order_if_ready(s)
            return dict(s)
    return None


def complete_call_session(execution_id: str, *, status: str = "completed") -> dict[str, Any] | None:
    for s in _ensure_call_sessions():
        if s.get("execution_id") == execution_id:
            _link_order_if_ready(s)
            if not s.get("order_id"):
                s["status"] = "no_order" if status == "completed" else status
            elif s.get("status") == "in_progress":
                s["status"] = "completed"
            s["ended_at"] = s.get("ended_at") or datetime.now(_IST).isoformat()
            s["updated_at"] = datetime.now(_IST).isoformat()
            return dict(s)
    return None


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


def _ensure_whatsapp_outbox() -> list[dict[str, Any]]:
    db = load_db()
    if "whatsapp_outbox" not in db or db["whatsapp_outbox"] is None:
        db["whatsapp_outbox"] = []
    return db["whatsapp_outbox"]


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

    Idempotent: if order_id is already in the outbox, return that row
    (create_order + Bolna closing node both call this).
    """
    box = _ensure_whatsapp_outbox()
    if order_id:
        for existing in box:
            if existing.get("order_id") == order_id:
                return existing

    msg = {
        "id": f"WA-{len(box) + 1:04d}",
        "to": retailer_phone,
        "order_id": order_id,
        "summary_text": summary_text,
        "channel": "whatsapp_mock",
        "status": "sent",
        "sent_at": datetime.now(_IST).isoformat(),
    }
    box.append(msg)
    return msg


def list_whatsapp_outbox() -> list[dict[str, Any]]:
    """Newest first — dashboard reads this panel."""
    box = list(_ensure_whatsapp_outbox())
    box.sort(key=lambda m: m.get("sent_at", ""), reverse=True)
    return box


def _ensure_callbacks() -> list[dict[str, Any]]:
    db = load_db()
    if "callbacks" not in db:
        db["callbacks"] = []
    return db["callbacks"]


def log_callback(
    *,
    retailer_id: str | None,
    phone: str | None,
    shop_name: str | None,
    callback_slot: str,
    reason: str | None = None,
    disposition: str | None = None,
) -> dict[str, Any]:
    """Busy → callback, or DNC / do-not-call retention notes for the ops console."""
    disp = (disposition or "callback").strip().lower()
    row = {
        "id": f"CB-{len(_ensure_callbacks()) + 1:04d}",
        "retailer_id": retailer_id,
        "phone": phone,
        "shop_name": shop_name,
        "callback_slot": callback_slot,
        "reason": reason or ("dnc" if disp == "dnc" else "busy"),
        "disposition": disp,
        "created_at": datetime.now(_IST).isoformat(),
    }
    _ensure_callbacks().append(row)
    return row


def lookup_status_flexible(
    *,
    order_id: str | None = None,
    phone: str | None = None,
    retailer_id: str | None = None,
) -> dict[str, Any]:
    """
    Outbound mid-call status: by order_id, or latest open order for phone/retailer_id.
    """
    oid = (order_id or "").strip()
    phone = (phone or "").strip() or None
    rid = (retailer_id or "").strip()
    if oid:
        return get_order_status(oid, phone=phone)

    if not rid and phone:
        retailer = get_retailer_by_phone(phone)
        if retailer is None:
            raise ValueError(f"No retailer found for phone {phone}")
        rid = retailer["id"]
    if not rid:
        raise ValueError("Provide order_id, phone, or retailer_id")

    opens = get_open_orders_summary(rid)
    if not opens:
        # Fall back to any latest order for the shop
        all_orders = get_orders_for_retailer(rid)
        if not all_orders:
            raise ValueError(f"No orders found for retailer {rid}")
        return order_status_payload(all_orders[0])

    return get_order_status(opens[0]["order_id"], phone=phone)


def list_callbacks() -> list[dict[str, Any]]:
    rows = list(_ensure_callbacks())
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return rows

