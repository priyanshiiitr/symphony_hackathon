"""List Bolna phone numbers and link inbound agent via /inbound/setup.

Usage:
  py -3.12 bolna/inbound/setup_inbound.py           # list + link first free / first number
  py -3.12 bolna/inbound/setup_inbound.py --list    # list only
  py -3.12 bolna/inbound/setup_inbound.py --phone-id <uuid>
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY = os.environ.get("BOLNA_API_KEY", "").strip()
AGENT_ID = (HERE / "AGENT_ID.txt").read_text(encoding="utf-8").strip() if (HERE / "AGENT_ID.txt").exists() else ""

if not KEY:
    print("Set BOLNA_API_KEY", file=sys.stderr)
    sys.exit(1)


def api_get(path: str):
    req = urllib.request.Request(
        f"https://api.bolna.ai{path}",
        headers={"Authorization": f"Bearer {KEY}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def api_post(path: str, body: dict):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"https://api.bolna.ai{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode(errors='replace')}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    numbers = api_get("/phone-numbers/all")
    if not isinstance(numbers, list):
        numbers = numbers.get("phone_numbers") or numbers.get("data") or []

    print("=== Phone numbers ===")
    for n in numbers:
        print(
            json.dumps(
                {
                    "id": n.get("id"),
                    "phone_number": n.get("phone_number"),
                    "telephony_provider": n.get("telephony_provider"),
                    "agent_id": n.get("agent_id"),
                },
                ensure_ascii=False,
            )
        )

    if "--list" in sys.argv or not numbers:
        if not numbers:
            print(
                "\nNo numbers on account. Buy/assign a number in Bolna dashboard, "
                "then re-run setup_inbound.py",
                file=sys.stderr,
            )
        return

    if not AGENT_ID:
        print("Missing bolna/inbound/AGENT_ID.txt — run create_agent.py first", file=sys.stderr)
        sys.exit(1)

    phone_id = None
    if "--phone-id" in sys.argv:
        i = sys.argv.index("--phone-id")
        phone_id = sys.argv[i + 1]
    else:
        # Prefer a number with no agent, else first
        free = [n for n in numbers if not n.get("agent_id")]
        chosen = free[0] if free else numbers[0]
        phone_id = chosen["id"]
        print(f"\nLinking agent {AGENT_ID} → {chosen.get('phone_number')} ({phone_id})")

    result = api_post(
        "/inbound/setup",
        {"agent_id": AGENT_ID, "phone_number_id": phone_id, "allow_multiple": True},
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    dial = result.get("phone_number") or ""
    (HERE / "INBOUND_NUMBER.txt").write_text(dial or phone_id, encoding="utf-8")
    (HERE / "PHONE_NUMBER_ID.txt").write_text(str(phone_id), encoding="utf-8")
    print(f"\nDial {dial or phone_id} from +919571025342 for dual demo.")


if __name__ == "__main__":
    main()
