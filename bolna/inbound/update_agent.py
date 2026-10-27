"""PUT-update TradeCall inbound agent from local graph/tools."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# Reuse create_agent builder
sys.path.insert(0, str(HERE))
from create_agent import build_payload  # noqa: E402

KEY = os.environ.get("BOLNA_API_KEY", "").strip()
AGENT_ID = (HERE / "AGENT_ID.txt").read_text(encoding="utf-8").strip()
BASE = (ROOT / "scripts" / "PUBLIC_URL.txt").read_text(encoding="utf-8").strip().rstrip("/")

if not KEY or not AGENT_ID or not BASE:
    print("Need BOLNA_API_KEY, AGENT_ID.txt, PUBLIC_URL.txt", file=sys.stderr)
    sys.exit(1)

payload = build_payload()
(HERE / "agent_payload.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
)

body = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(
    f"https://api.bolna.ai/v2/agent/{AGENT_ID}",
    data=body,
    headers={
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
    },
    method="PUT",
)
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode(errors='replace')}", file=sys.stderr)
    sys.exit(1)

print(json.dumps(data, indent=2, ensure_ascii=False)[:1500])
print(f"Updated inbound agent {AGENT_ID}")
print(f"Tools BASE_URL={BASE}")
