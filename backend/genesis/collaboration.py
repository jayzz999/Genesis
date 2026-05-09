"""Module 4 — multi-agent collaboration and debate.

This phase gives Genesis a deliberation surface above single-organism action:
specialist agents independently propose, critique each other, then synthesize
one auditable verdict.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional
from uuid import uuid4

from backend.shared.gemini_client import generate_text

from . import memory

EventCallback = Callable[[str, dict], Awaitable[None]]

_BASE = Path(os.getenv("GENESIS_COLLAB_STORAGE", "collaborations")).resolve()

DEFAULT_AGENTS = [
    {
        "id": "architect",
        "name": "Systems Architect",
        "stance": "Design the cleanest system shape and identify integration pressure.",
    },
    {
        "id": "critic",
        "name": "Adversarial Critic",
        "stance": "Find hidden failure modes, missing evidence, and unsafe assumptions.",
    },
    {
        "id": "operator",
        "name": "Execution Operator",
        "stance": "Convert ideas into shippable steps, tests, and operational guardrails.",
    },
]


def _now() -> str:
    return datetime.utcnow().isoformat()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _path(run_id: str) -> Path:
    return _BASE / f"{run_id}.json"


def _save(run: dict) -> dict:
    run["updated_at"] = _now()
    _atomic_write_text(_path(run["id"]), json.dumps(run, indent=2, default=str))
    return run


def _parse_json(text: str) -> dict:
    s = (text or "").strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 2:
            s = parts[1].strip()
            if s.startswith("json"):
                s = s[4:].strip()
    try:
        return json.loads(s)
    except Exception:
        i, j = s.find("{"), s.rfind("}")
        if i != -1 and j != -1:
            try:
                return json.loads(s[i : j + 1])
            except Exception:
                pass
    return {}


def _tokens(value: object) -> set[str]:
    text = json.dumps(value, default=str).lower() if not isinstance(value, str) else value.lower()
    return set(re.findall(r"[a-z0-9_]{4,}", text))


def _score_proposal(proposal: dict, critiques: list[dict]) -> float:
    critique_scores = [
        float(c.get("score", 0.5))
        for c in critiques
        if c.get("target_agent_id") == proposal.get("agent_id")
    ]
    confidence = float(proposal.get("confidence", 0.5) or 0.5)
    support = len(_tokens(proposal.get("recommendation", "")) | _tokens(proposal.get("evidence", [])))
    risk_penalty = min(len(proposal.get("risks", []) or []) * 0.04, 0.2)
    peer = sum(critique_scores) / len(critique_scores) if critique_scores else 0.55
    return round(max(0.0, min(1.0, (confidence * 0.45) + (peer * 0.45) + min(support / 80, 0.1) - risk_penalty)), 4)


def _memory_context(topic: str, context: dict, limit: int = 5) -> list[dict]:
    query_tokens = _tokens({"topic": topic, "context": context})
    scored = []
    for item in memory.list_memories(limit=200):
        overlap = len(query_tokens & _tokens({"text": item.text, "tags": item.tags}))
        if overlap:
            scored.append((overlap + item.score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item.model_dump(mode="json") for _, item in scored[:limit]]


async def _agent_proposal(agent: dict, topic: str, context: dict, memories: list[dict]) -> dict:
    prompt = json.dumps({
        "topic": topic,
        "context": context,
        "agent": agent,
        "relevant_long_term_memory": memories,
        "contract": {
            "recommendation": "one concrete position",
            "evidence": ["specific evidence or assumptions"],
            "risks": ["important risks"],
            "tests": ["how to validate the position"],
            "confidence": "number 0..1",
        },
    }, indent=2, default=str)
    raw = await generate_text(
        prompt=prompt,
        system="Genesis multi-agent debate participant. Return strict JSON only.",
        temperature=0.25,
        max_tokens=1400,
    )
    data = _parse_json(raw)
    return {
        "agent_id": agent["id"],
        "agent_name": agent["name"],
        "stance": agent["stance"],
        "recommendation": str(data.get("recommendation") or data.get("position") or raw)[:3000],
        "evidence": list(data.get("evidence") or data.get("supporting_evidence") or [])[:8],
        "risks": list(data.get("risks") or [])[:8],
        "tests": list(data.get("tests") or data.get("validation") or [])[:8],
        "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.55) or 0.55))),
    }


async def _agent_critique(agent: dict, topic: str, proposals: list[dict]) -> dict:
    prompt = json.dumps({
        "topic": topic,
        "critic": agent,
        "proposals_to_review": [
            {
                "agent_id": p["agent_id"],
                "agent_name": p["agent_name"],
                "recommendation": p["recommendation"],
                "evidence": p["evidence"],
                "risks": p["risks"],
                "tests": p["tests"],
            }
            for p in proposals
            if p["agent_id"] != agent["id"]
        ],
        "contract": {
            "target_agent_id": "proposal being critiqued most directly",
            "strongest_point": "best thing in that proposal",
            "weakest_point": "main flaw or missing evidence",
            "revision": "specific improvement",
            "score": "number 0..1",
        },
    }, indent=2, default=str)
    raw = await generate_text(
        prompt=prompt,
        system="Genesis multi-agent debate critic. Return strict JSON only.",
        temperature=0.2,
        max_tokens=1200,
    )
    data = _parse_json(raw)
    targets = [p["agent_id"] for p in proposals if p["agent_id"] != agent["id"]]
    return {
        "critic_agent_id": agent["id"],
        "critic_agent_name": agent["name"],
        "target_agent_id": data.get("target_agent_id") if data.get("target_agent_id") in targets else (targets[0] if targets else None),
        "strongest_point": str(data.get("strongest_point") or "")[:1200],
        "weakest_point": str(data.get("weakest_point") or data.get("critique") or raw)[:1200],
        "revision": str(data.get("revision") or "")[:1200],
        "score": max(0.0, min(1.0, float(data.get("score", 0.55) or 0.55))),
    }


async def _synthesize(topic: str, context: dict, proposals: list[dict], critiques: list[dict]) -> dict:
    scored = [
        {**proposal, "debate_score": _score_proposal(proposal, critiques)}
        for proposal in proposals
    ]
    scored.sort(key=lambda p: p["debate_score"], reverse=True)
    prompt = json.dumps({
        "topic": topic,
        "context": context,
        "scored_proposals": scored,
        "critiques": critiques,
        "contract": {
            "decision": "final recommended answer",
            "consensus": ["points all or most agents agree on"],
            "dissent": ["important unresolved disagreements"],
            "risks": ["risks to monitor"],
            "next_actions": ["concrete next steps"],
            "confidence": "number 0..1",
        },
    }, indent=2, default=str)
    raw = await generate_text(
        prompt=prompt,
        system="Genesis multi-agent debate synthesis judge. Return strict JSON only.",
        temperature=0.15,
        max_tokens=1600,
    )
    data = _parse_json(raw)
    if not data:
        best = scored[0] if scored else {}
        data = {
            "decision": best.get("recommendation", raw),
            "consensus": [best.get("recommendation", "")],
            "dissent": [],
            "risks": best.get("risks", []),
            "next_actions": best.get("tests", []),
            "confidence": best.get("debate_score", 0.5),
        }
    return {
        "decision": str(data.get("decision") or "")[:4000],
        "consensus": list(data.get("consensus") or [])[:8],
        "dissent": list(data.get("dissent") or [])[:8],
        "risks": list(data.get("risks") or [])[:8],
        "next_actions": list(data.get("next_actions") or data.get("actions") or [])[:8],
        "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.55) or 0.55))),
        "ranked_agents": [
            {
                "agent_id": p["agent_id"],
                "agent_name": p["agent_name"],
                "debate_score": p["debate_score"],
            }
            for p in scored
        ],
    }


def list_debates(limit: int = 50) -> list[dict]:
    if not _BASE.exists():
        return []
    runs = []
    for path in _BASE.glob("debate_*.json"):
        run = get_debate(path.stem)
        if run:
            runs.append(run)
    runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return runs[:limit]


def get_debate(run_id: str) -> Optional[dict]:
    path = _path(run_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


async def run_debate(
    *,
    topic: str,
    context: Optional[dict] = None,
    agents: Optional[list[dict]] = None,
    event_callback: Optional[EventCallback] = None,
) -> dict:
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("debate topic is required")

    selected_agents = (agents or DEFAULT_AGENTS)[:5]
    if len(selected_agents) < 2:
        raise ValueError("at least two debate agents are required")

    run = {
        "id": f"debate_{uuid4().hex[:12]}",
        "created_at": _now(),
        "updated_at": None,
        "topic": topic,
        "context": context or {},
        "status": "running",
        "agents": selected_agents,
        "memories": _memory_context(topic, context or {}),
        "proposals": [],
        "critiques": [],
        "synthesis": None,
        "error": None,
    }
    _save(run)
    if event_callback:
        await event_callback("collaboration.started", {"debate": _public_summary(run)})

    try:
        proposals = await asyncio.gather(*[
            _agent_proposal(agent, topic, run["context"], run["memories"])
            for agent in selected_agents
        ])
        run["proposals"] = proposals
        _save(run)
        if event_callback:
            await event_callback("collaboration.proposals_ready", {"debate_id": run["id"], "proposals": proposals})

        critiques = await asyncio.gather(*[
            _agent_critique(agent, topic, proposals)
            for agent in selected_agents
        ])
        run["critiques"] = critiques
        _save(run)
        if event_callback:
            await event_callback("collaboration.critiques_ready", {"debate_id": run["id"], "critiques": critiques})

        run["synthesis"] = await _synthesize(topic, run["context"], proposals, critiques)
        run["status"] = "complete"
        _save(run)
        memory.remember(
            f"Debate on '{topic}' concluded: {run['synthesis'].get('decision', '')[:600]}",
            kind="debate_result",
            scope="global",
            tags=["module-4", "debate", "collaboration"],
            source_run_id=run["id"],
            score=run["synthesis"].get("confidence", 0.6),
        )
        if event_callback:
            await event_callback("collaboration.completed", {"debate": run})
        return run
    except Exception as exc:
        run["status"] = "error"
        run["error"] = str(exc)
        _save(run)
        if event_callback:
            await event_callback("collaboration.failed", {"debate": _public_summary(run), "error": str(exc)})
        return run


def _public_summary(run: dict) -> dict:
    return {
        "id": run.get("id"),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "topic": run.get("topic"),
        "status": run.get("status"),
        "agent_count": len(run.get("agents") or []),
        "proposal_count": len(run.get("proposals") or []),
        "critique_count": len(run.get("critiques") or []),
        "confidence": (run.get("synthesis") or {}).get("confidence"),
        "decision": (run.get("synthesis") or {}).get("decision"),
        "error": run.get("error"),
    }
