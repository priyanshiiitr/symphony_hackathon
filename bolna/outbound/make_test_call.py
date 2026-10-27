"""Place outbound call with last_order_summary preloaded (low latency greeting)."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KEY = os.environ.get("BOLNA_API_KEY") or os.environ.get("BOLNA_API_KEY".upper())
# Windows user env may need refresh
if not KEY:
    print("BOLNA_API_KEY missing", file=sys.stderr)
    sys.exit(1)

AGENT_ID = (HERE / "AGENT_ID.txt").read_text(encoding="utf-8").strip()
TO = sys.argv[1] if len(sys.argv) > 1 else "+919571025342"
RETAILER_ID = sys.argv[2] if len(sys.argv) > 2 else "R01"

# Prefetch last order from local API
import urllib.error

try:
    local = urllib.request.urlopen(
        f"http://127.0.0.1:8000/v1/retailers/{RETAILER_ID}/last-order", timeout=5
    )
    last = json.loads(local.read().decode())
    summary = ", ".join(
        f"{i.get('qty')} {i.get('unit')} {i.get('name')}" for i in last.get("items", [])
    )
    last_order_summary = f"Last order {last.get('order_id')}: {summary}"
except Exception as exc:  # noqa: BLE001
    last_order_summary = f"NONE ({exc})"

week = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b")
body = {
    "agent_id": AGENT_ID,
    "recipient_phone_number": TO,
    "user_data": {
        "retailer_id": RETAILER_ID,
        "retailer_name": "Ramesh Sharma",
        "shop_name": "Sharma Electricals",
        "retailer_phone": TO,
        "distributor_name": "Bharat Hardware Distributors",
        "week_label": week,
        "preferred_language": "hi",
        "timezone": "Asia/Kolkata",
        "flow": "outbound",
        "last_order_summary": last_order_summary,
    },
}

req = urllib.request.Request(
    "https://api.bolna.ai/call",
    data=json.dumps(body).encode(),
    headers={
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
    },
    method="POST",
)
with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.loads(resp.read().decode())

print(json.dumps(data, indent=2))
print(f"last_order_summary={last_order_summary}")
if data.get("execution_id"):
    (HERE / "LAST_EXECUTION_ID.txt").write_text(data["execution_id"], encoding="utf-8")
    print("ANSWER YOUR PHONE")
