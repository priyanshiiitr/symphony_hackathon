"""Create TradeCall inbound status graph agent on Bolna."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = (ROOT / "scripts" / "PUBLIC_URL.txt").read_text(encoding="utf-8").strip().rstrip("/")
KEY = os.environ.get("BOLNA_API_KEY", "").strip()

if not KEY:
    print("Set BOLNA_API_KEY", file=sys.stderr)
    sys.exit(1)
if not BASE:
    print("Missing scripts/PUBLIC_URL.txt", file=sys.stderr)
    sys.exit(1)


def build_payload() -> dict:
    graph = json.loads((HERE / "graph_nodes.json").read_text(encoding="utf-8"))
    tools_doc = json.loads((HERE / "tools.json").read_text(encoding="utf-8"))
    for t in tools_doc["tools"]:
        pcm = t.get("pre_call_message")
        if isinstance(pcm, dict):
            t["pre_call_message"] = pcm.get("hi") or pcm.get("en") or "Please wait…"

    tools_params = json.loads(
        json.dumps(tools_doc["tools_params"]).replace("{{BASE_URL}}", BASE)
    )

    return {
        "agent_config": {
            "agent_name": "TradeCall Inbound Status",
            "agent_type": "other",
            "agent_welcome_message": "नमस्ते, भारत हार्डवेयर डिस्ट्रीब्यूटर्स से रवि। ऑर्डर स्टेटस या डिलीवरी पूछनी है?",
            "tasks": [
                {
                    "task_type": "conversation",
                    "toolchain": {
                        "execution": "parallel",
                        "pipelines": [["transcriber", "llm", "synthesizer"]],
                    },
                    "task_config": {
                        "optimize_latency": True,
                        "call_terminate": 300,
                        "hangup_after_LLMCall": False,
                        "hangup_after_silence": 35,
                        "number_of_words_for_interruption": 1,
                        "inbound_limit": -1,
                    },
                    "tools_config": {
                        # Number is VoBiz — Plivo I/O here causes 2s "End Of XML" hangups
                        "input": {"format": "wav", "provider": "vobiz"},
                        "output": {"format": "wav", "provider": "vobiz"},
                        "api_tools": {
                            "tools": tools_doc["tools"],
                            "tools_params": tools_params,
                        },
                        "llm_agent": {
                            "agent_type": "graph_agent",
                            "agent_flow_type": "streaming",
                            "llm_config": {
                                **graph,
                                "provider": "openai",
                                "model": "gpt-4.1-mini",
                                "max_tokens": 120,
                                "temperature": 0.1,
                            },
                        },
                        "transcriber": {
                            "provider": "deepgram",
                            "model": "nova-3",
                            "language": "hi",
                            "stream": True,
                            "encoding": "linear16",
                            "sampling_rate": 16000,
                            "endpointing": 400,
                        },
                        "synthesizer": {
                            "provider": "sarvam",
                            "stream": True,
                            "buffer_size": 150,
                            "audio_format": "wav",
                            "provider_config": {
                                "voice": "Suhani",
                                "voice_id": "suhani",
                                "model": "bulbul:v3",
                                "language": "hi",
                                "speed": 1.0,
                            },
                        },
                    },
                }
            ],
        },
        "agent_prompts": {
            "task_1": {
                "system_prompt": (
                    "You are Ravi on the inbound status line for Bharat Hardware. "
                    "Follow graph nodes. Prefer preloaded {{shop_name}} / {{open_orders_summary}}. "
                    "Never invent status or ETA."
                )
            }
        },
    }


def main() -> None:
    payload = build_payload()
    (HERE / "agent_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"BASE_URL={BASE}")

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.bolna.ai/v2/agent",
        data=body,
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode(errors='replace')}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
    agent_id = data.get("agent_id")
    if agent_id:
        (HERE / "AGENT_ID.txt").write_text(agent_id, encoding="utf-8")
        print(f"Saved AGENT_ID={agent_id}")


if __name__ == "__main__":
    main()
