"""
Distributor agent management — list / customize / create Bolna agents.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/agents", tags=["agents"])

_REPO = Path(__file__).resolve().parents[3]
_REGISTRY = _REPO / "bolna" / "agents_registry.json"
_OUTBOUND = _REPO / "bolna" / "outbound"
_INBOUND = _REPO / "bolna" / "inbound"
_PUBLIC = _REPO / "scripts" / "PUBLIC_URL.txt"


def _key() -> str:
    key = os.environ.get("BOLNA_API_KEY", "").strip()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="BOLNA_API_KEY not set on API process",
        )
    return key


def _base_url() -> str:
    if not _PUBLIC.exists():
        raise HTTPException(status_code=500, detail="Missing scripts/PUBLIC_URL.txt")
    return _PUBLIC.read_text(encoding="utf-8").strip().rstrip("/")


def _load_registry() -> dict[str, Any]:
    if not _REGISTRY.exists():
        return {"agents": []}
    return json.loads(_REGISTRY.read_text(encoding="utf-8"))


def _save_registry(data: dict[str, Any]) -> None:
    _REGISTRY.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _bolna_get(path: str) -> Any:
    req = urllib.request.Request(
        f"https://api.bolna.ai{path}",
        headers={"Authorization": f"Bearer {_key()}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Bolna GET {path} → {e.code}: {e.read().decode(errors='replace')[:500]}",
        ) from e


def _bolna_json(method: str, path: str, body: dict[str, Any]) -> Any:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.bolna.ai{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {_key()}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Bolna {method} {path} → {e.code}: {e.read().decode(errors='replace')[:800]}",
        ) from e


def _summarize_agent(raw: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    tasks = raw.get("tasks") or []
    system_prompt = ""
    # prompts may live on agent or nested
    prompts = raw.get("agent_prompts") or {}
    if isinstance(prompts, dict):
        system_prompt = (prompts.get("task_1") or {}).get("system_prompt") or ""
    return {
        "agent_id": raw.get("id") or raw.get("agent_id") or (meta or {}).get("agent_id"),
        "agent_name": raw.get("agent_name") or (meta or {}).get("name"),
        "agent_welcome_message": raw.get("agent_welcome_message") or "",
        "agent_status": raw.get("agent_status"),
        "inbound_phone_number": raw.get("inbound_phone_number"),
        "system_prompt": system_prompt,
        "role": (meta or {}).get("role"),
        "label": (meta or {}).get("label"),
        "task_count": len(tasks),
    }


def _build_payload(
    *,
    role: str,
    agent_name: str,
    welcome_message: str,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    folder = _OUTBOUND if role == "outbound" else _INBOUND
    graph = json.loads((folder / "graph_nodes.json").read_text(encoding="utf-8"))
    tools_doc = json.loads((folder / "tools.json").read_text(encoding="utf-8"))
    for t in tools_doc["tools"]:
        pcm = t.get("pre_call_message")
        if isinstance(pcm, dict):
            t["pre_call_message"] = pcm.get("hi") or pcm.get("en") or "Please wait…"
    base = _base_url()
    tools_params = json.loads(
        json.dumps(tools_doc["tools_params"]).replace("{{BASE_URL}}", base)
    )
    provider = "plivo" if role == "outbound" else "vobiz"
    default_system = (
        "You are Ravi from Bharat Hardware Distributors. Follow graph node instructions. Keep replies short."
        if role == "outbound"
        else "You are Ravi on the inbound status line for Bharat Hardware. Never invent status or ETA."
    )
    return {
        "agent_config": {
            "agent_name": agent_name,
            "agent_type": "other",
            "agent_welcome_message": welcome_message,
            "tasks": [
                {
                    "task_type": "conversation",
                    "toolchain": {
                        "execution": "parallel",
                        "pipelines": [["transcriber", "llm", "synthesizer"]],
                    },
                    "task_config": {
                        "optimize_latency": True,
                        "call_terminate": 480 if role == "outbound" else 300,
                        "hangup_after_LLMCall": False,
                        "hangup_after_silence": 35,
                        "number_of_words_for_interruption": 1,
                        "inbound_limit": -1,
                    },
                    "tools_config": {
                        "input": {"format": "wav", "provider": provider},
                        "output": {"format": "wav", "provider": provider},
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
                "system_prompt": system_prompt or default_system,
            }
        },
    }


class CustomizeIn(BaseModel):
    agent_name: str | None = None
    agent_welcome_message: str | None = None
    system_prompt: str | None = None


class CreateAgentIn(BaseModel):
    role: str = Field(..., description="outbound | inbound")
    agent_name: str
    agent_welcome_message: str
    system_prompt: str | None = None
    label: str | None = None
    set_as_default: bool = False


@router.get("")
def list_agents() -> dict[str, Any]:
    reg = _load_registry()
    out = []
    for meta in reg.get("agents", []):
        aid = meta.get("agent_id")
        if not aid:
            continue
        try:
            raw = _bolna_get(f"/v2/agent/{aid}")
            out.append(_summarize_agent(raw, meta))
        except HTTPException as exc:
            out.append(
                {
                    **meta,
                    "error": str(exc.detail),
                    "agent_id": aid,
                }
            )
    return {"count": len(out), "agents": out, "public_url": _base_url()}


@router.get("/{agent_id}")
def get_agent(agent_id: str) -> dict[str, Any]:
    reg = _load_registry()
    meta = next((a for a in reg.get("agents", []) if a.get("agent_id") == agent_id), None)
    raw = _bolna_get(f"/v2/agent/{agent_id}")
    return {"agent": _summarize_agent(raw, meta), "raw_keys": list(raw.keys())}


@router.patch("/{agent_id}")
def customize_agent(agent_id: str, body: CustomizeIn) -> dict[str, Any]:
    """Update name / welcome / system prompt, preserving graph tools from Bolna GET."""
    raw = _bolna_get(f"/v2/agent/{agent_id}")
    # Rebuild PUT payload from live agent + edits
    name = body.agent_name or raw.get("agent_name") or "TradeCall Agent"
    welcome = (
        body.agent_welcome_message
        if body.agent_welcome_message is not None
        else (raw.get("agent_welcome_message") or "")
    )
    prompts = deepcopy(raw.get("agent_prompts") or {"task_1": {"system_prompt": ""}})
    if body.system_prompt is not None:
        prompts.setdefault("task_1", {})["system_prompt"] = body.system_prompt

    tasks = raw.get("tasks")
    if not tasks:
        raise HTTPException(status_code=500, detail="Agent has no tasks to update")

    payload = {
        "agent_config": {
            "agent_name": name,
            "agent_type": raw.get("agent_type") or "other",
            "agent_welcome_message": welcome,
            "tasks": tasks,
        },
        "agent_prompts": prompts,
    }
    result = _bolna_json("PUT", f"/v2/agent/{agent_id}", payload)

    # sync registry name
    reg = _load_registry()
    for a in reg.get("agents", []):
        if a.get("agent_id") == agent_id:
            a["name"] = name
            break
    _save_registry(reg)

    return {"ok": True, "bolna": result, "agent_id": agent_id}


@router.post("")
def create_agent(body: CreateAgentIn) -> dict[str, Any]:
    role = body.role.strip().lower()
    if role not in ("outbound", "inbound"):
        raise HTTPException(status_code=400, detail="role must be outbound or inbound")

    payload = _build_payload(
        role=role,
        agent_name=body.agent_name,
        welcome_message=body.agent_welcome_message,
        system_prompt=body.system_prompt,
    )
    created = _bolna_json("POST", "/v2/agent", payload)
    agent_id = created.get("agent_id") or created.get("id")
    if not agent_id:
        raise HTTPException(status_code=502, detail=f"No agent_id in create response: {created}")

    reg = _load_registry()
    entry = {
        "role": role,
        "agent_id": agent_id,
        "name": body.agent_name,
        "label": body.label or body.agent_name,
    }
    reg.setdefault("agents", []).append(entry)

    if body.set_as_default:
        folder = _OUTBOUND if role == "outbound" else _INBOUND
        (folder / "AGENT_ID.txt").write_text(agent_id + "\n", encoding="utf-8")
        rest = [a for a in reg["agents"] if a.get("agent_id") != agent_id]
        reg["agents"] = [entry] + rest

    _save_registry(reg)
    return {"ok": True, "agent_id": agent_id, "role": role, "bolna": created}
