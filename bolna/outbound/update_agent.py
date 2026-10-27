"""Rebuild payload and PUT-update the existing Bolna agent."""

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
AGENT_ID = (HERE / "AGENT_ID.txt").read_text(encoding="utf-8").strip()

if not KEY or not AGENT_ID or not BASE:
    print("Need BOLNA_API_KEY, AGENT_ID.txt, PUBLIC_URL.txt", file=sys.stderr)
    sys.exit(1)

# Force create_agent to only build: import payload from rewritten file after running build steps
graph = json.loads((HERE / "graph_nodes.json").read_text(encoding="utf-8"))
tools_doc = json.loads((HERE / "tools.json").read_text(encoding="utf-8"))
for t in tools_doc["tools"]:
    pcm = t.get("pre_call_message")
    if isinstance(pcm, dict):
        t["pre_call_message"] = pcm.get("hi") or pcm.get("en") or "Please wait…"

tools_params = json.loads(json.dumps(tools_doc["tools_params"]).replace("{{BASE_URL}}", BASE))

payload = {
    "agent_config": {
        "agent_name": "TradeCall Outbound Hardware",
        "agent_type": "other",
        "agent_welcome_message": "नमस्ते {{shop_name}}, मैं रवि बोल रहा हूँ भारत हार्डवेयर डिस्ट्रीब्यूटर्स से।",
        "tasks": [
            {
                "task_type": "conversation",
                "toolchain": {
                    "execution": "parallel",
                    "pipelines": [["transcriber", "llm", "synthesizer"]],
                },
                "task_config": {
                    "optimize_latency": True,
                    "call_terminate": 480,
                    "hangup_after_LLMCall": False,
                    "hangup_after_silence": 35,
                    "number_of_words_for_interruption": 1,
                },
                "tools_config": {
                    "input": {"format": "wav", "provider": "plivo"},
                    "output": {"format": "wav", "provider": "plivo"},
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
                            "max_tokens": 150,
                            "temperature": 0.2,
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
            "system_prompt": "You are Ravi from Bharat Hardware Distributors. Follow graph node instructions. Keep replies short. Prefer {{last_order_summary}} over tools at greeting."
        }
    },
}

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

print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
print(f"Updated agent {AGENT_ID}")
print(f"Tools BASE_URL={BASE}")
