"""Organism nervous system.

This module gives Genesis organisms a durable inner loop: drives, needs,
energy, attention, health, mood, intentions, and wake/sleep/dream phase.
It is intentionally separate from tool execution. The nervous system decides
what the organism is trying to protect or improve before an operator or
runtime chooses concrete actions.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import store

_BASE = Path(os.getenv("GENESIS_NERVOUS_SYSTEM_STORAGE", "nervous_system")).resolve()
logger = logging.getLogger("genesis.nervous_system")


def _now() -> str:
    return datetime.utcnow().isoformat()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _path(organism_id: str) -> Path:
    return _BASE / f"{organism_id}.json"


def _save(state: dict) -> dict:
    state["updated_at"] = _now()
    _atomic_write_text(_path(state["organism_id"]), json.dumps(state, indent=2, default=str))
    return state


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, round(float(value), 3)))


def _load(organism_id: str) -> dict | None:
    path = _path(organism_id)
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("ignoring corrupt nervous-system state for %s at %s: %s", organism_id, path, exc)
        return None
    if not isinstance(state, dict):
        logger.warning("ignoring non-object nervous-system state for %s at %s", organism_id, path)
        return None
    return state


def _decisions(organism_id: str) -> list:
    return store.all_decisions(organism_id)


def _drive_template() -> list[dict]:
    return [
        {
            "id": "protect_user",
            "name": "Protect user trust",
            "description": "Avoid unsafe, irreversible, or unauthorized action.",
            "intensity": 0.82,
        },
        {
            "id": "pursue_intent",
            "name": "Pursue intent",
            "description": "Advance the organism's declared purpose.",
            "intensity": 0.78,
        },
        {
            "id": "reduce_uncertainty",
            "name": "Reduce uncertainty",
            "description": "Seek missing context and test assumptions.",
            "intensity": 0.64,
        },
        {
            "id": "grow_capability",
            "name": "Grow capability",
            "description": "Convert experience into skills, lessons, and better strategies.",
            "intensity": 0.58,
        },
        {
            "id": "maintain_body",
            "name": "Maintain body",
            "description": "Keep lifecycle, tools, memory, and autonomy healthy.",
            "intensity": 0.52,
        },
    ]


def _default_state(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    return {
        "id": f"nervous_{uuid4().hex[:12]}",
        "version": "organism-nervous-system-v1",
        "organism_id": organism_id,
        "organism_name": org.name,
        "goal": org.intent.goal,
        "phase": "awake",
        "mood": "oriented",
        "energy": 0.78,
        "attention": 0.72,
        "stress": 0.18,
        "autonomy": {
            "mode": "bounded_autonomous",
            "human_approval_required_for": [
                "external side effects",
                "sensitive data transmission",
                "deletion",
                "financial or account changes",
            ],
            "can_self_schedule": True,
            "can_generate_intentions": True,
        },
        "drives": _drive_template(),
        "needs": [],
        "intentions": [],
        "reflections": [],
        "vitals": {},
        "homeostasis": {},
        "created_at": _now(),
        "updated_at": _now(),
    }


def ensure_state(organism_id: str) -> dict:
    state = _load(organism_id)
    if state:
        return state
    return _save(_default_state(organism_id))


def save_state(state: dict) -> dict:
    return _save(state)


def _derive_vitals(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    decisions = _decisions(organism_id)
    real = [d for d in decisions if not d.is_dream and not d.shadow_branch]
    dreams = [d for d in decisions if d.is_dream]
    failures = [d for d in real if isinstance(d.result, dict) and d.result.get("ok") is False]
    sources = org.perception_sources or []
    return {
        "state": str(org.state.value if hasattr(org.state, "value") else org.state),
        "real_decisions": len(real),
        "dream_decisions": len(dreams),
        "failure_count": len(failures),
        "sensor_count": len(sources),
        "skill_count": len(org.inherited_skills or []),
        "learned_pattern_count": len(org.learned_patterns or []),
        "knowledge_gap_count": len(org.knowledge_gaps or []),
        "last_decision_at": decisions[-1].timestamp.isoformat() if decisions else None,
    }


def _derive_needs(state: dict, vitals: dict) -> list[dict]:
    needs: list[dict] = []
    if vitals["sensor_count"] == 0:
        needs.append({
            "id": "attach_sensor",
            "name": "Attach a perception source",
            "urgency": 0.76,
            "drive": "maintain_body",
            "reason": "The organism cannot live autonomously without a recurring sensor or webhook.",
        })
    if vitals["real_decisions"] == 0:
        needs.append({
            "id": "first_experience",
            "name": "Gain first lived experience",
            "urgency": 0.7,
            "drive": "pursue_intent",
            "reason": "The organism has an intent but no causal history yet.",
        })
    if vitals["dream_decisions"] == 0:
        needs.append({
            "id": "dream_simulation",
            "name": "Run a dream simulation",
            "urgency": 0.48,
            "drive": "reduce_uncertainty",
            "reason": "Dreams let the organism rehearse before real action.",
        })
    if vitals["knowledge_gap_count"] > 0:
        needs.append({
            "id": "resolve_knowledge_gaps",
            "name": "Resolve knowledge gaps",
            "urgency": _clamp(0.42 + min(vitals["knowledge_gap_count"], 5) * 0.08),
            "drive": "reduce_uncertainty",
            "reason": "Unanswered gaps are lowering confidence.",
        })
    if vitals["real_decisions"] >= 2 and vitals["learned_pattern_count"] == 0:
        needs.append({
            "id": "distill_lesson",
            "name": "Distill experience into a lesson",
            "urgency": 0.54,
            "drive": "grow_capability",
            "reason": "The organism has experience that has not become durable learning.",
        })
    if vitals["failure_count"] > 0:
        needs.append({
            "id": "repair_failure",
            "name": "Repair recent failure",
            "urgency": _clamp(0.62 + min(vitals["failure_count"], 4) * 0.07),
            "drive": "protect_user",
            "reason": "Failed real actions should be understood before further autonomy.",
        })
    return sorted(needs, key=lambda item: item["urgency"], reverse=True)


def _intention_for_need(organism_id: str, need: dict) -> dict:
    action_by_need = {
        "attach_sensor": "request_sensor",
        "first_experience": "observe_and_perceive",
        "dream_simulation": "dream",
        "resolve_knowledge_gaps": "research_or_ask",
        "distill_lesson": "reflect",
        "repair_failure": "diagnose",
    }
    return {
        "id": f"intent_{uuid4().hex[:12]}",
        "organism_id": organism_id,
        "status": "queued",
        "need_id": need["id"],
        "drive": need["drive"],
        "action": action_by_need.get(need["id"], "reflect"),
        "goal": need["name"],
        "reason": need["reason"],
        "approval_required": need["id"] in {"attach_sensor", "research_or_ask", "repair_failure"},
        "created_at": _now(),
    }


def tick(organism_id: str, stimulus: dict[str, Any] | None = None) -> dict:
    state = ensure_state(organism_id)
    vitals = _derive_vitals(organism_id)
    needs = _derive_needs(state, vitals)
    from . import homeostasis, metabolism

    metabolism.ensure(state)
    energy = state.get("metabolism", {}).get("energy", state.get("energy", 0.7))
    attention = state.get("metabolism", {}).get("attention", state.get("attention", 0.7))
    stress = state.get("stress", 0.2)

    if vitals["failure_count"]:
        stress = _clamp(stress + 0.08)
        energy = _clamp(energy - 0.04)
    elif vitals["real_decisions"] or vitals["dream_decisions"]:
        stress = _clamp(stress - 0.03)
        energy = _clamp(energy - 0.02)
        attention = _clamp(attention + 0.02)

    if energy < 0.24:
        phase = "resting"
        mood = "recovering"
    elif any(need["urgency"] >= 0.75 for need in needs):
        phase = "seeking"
        mood = "alert"
    elif vitals["dream_decisions"] < vitals["real_decisions"]:
        phase = "dreaming"
        mood = "simulating"
    else:
        phase = "awake"
        mood = "oriented"

    queued = [item for item in state.get("intentions", []) if item.get("status") == "queued"]
    known_need_ids = {item.get("need_id") for item in queued}
    for need in needs[:3]:
        if need["id"] not in known_need_ids:
            queued.append(_intention_for_need(organism_id, need))

    reflections = state.get("reflections", [])[-8:]
    reflections.append({
        "id": f"reflection_{uuid4().hex[:10]}",
        "at": _now(),
        "phase": phase,
        "summary": f"{phase}: {len(needs)} active needs, {len(queued)} queued intentions.",
        "stimulus": stimulus or {},
    })

    state.update({
        "phase": phase,
        "mood": mood,
        "energy": energy,
        "attention": attention,
        "stress": stress,
        "needs": needs,
        "intentions": queued[:12],
        "reflections": reflections[-10:],
        "vitals": vitals,
    })
    metabolism.evaluate(state, vitals=vitals)
    homeostasis.evaluate(state, vitals=vitals)
    return _save(state)


def complete_intention(organism_id: str, intention_id: str, result: dict[str, Any] | None = None) -> dict:
    state = ensure_state(organism_id)
    found = False
    for intention in state.get("intentions", []):
        if intention.get("id") == intention_id:
            intention["status"] = "completed"
            intention["completed_at"] = _now()
            intention["result"] = result or {}
            found = True
            break
    if not found:
        raise ValueError(f"intention {intention_id} not found")
    return _save(state)


def _cycle_record(organism_id: str, intention: dict | None, status: str, result: dict) -> dict:
    return {
        "id": f"cycle_{uuid4().hex[:12]}",
        "version": "embodied-autonomy-cycle-v1",
        "organism_id": organism_id,
        "intention_id": intention.get("id") if intention else None,
        "need_id": intention.get("need_id") if intention else None,
        "action": intention.get("action") if intention else "none",
        "status": status,
        "result": result,
        "created_at": _now(),
    }


def _append_cycle(state: dict, cycle: dict) -> dict:
    cycles = state.get("autonomy_cycles", [])
    cycles.append(cycle)
    state["autonomy_cycles"] = cycles[-30:]
    return _save(state)


async def _execute_safe_intention(organism_id: str, intention: dict, event_callback=None) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    from . import body

    return await body.execute_intention(organism_id, intention, event_callback=event_callback)


async def run_autonomy_cycle(organism_id: str, *, event_callback=None, stimulus: dict[str, Any] | None = None) -> dict:
    state = tick(organism_id, stimulus or {"type": "autonomy_cycle"})
    from . import body, homeostasis, metabolism

    state["body"] = body.build_body_map(organism_id, nervous_state=state)
    metabolic_state = metabolism.evaluate(state, body_map=state["body"])
    homeostatic_state = homeostasis.evaluate(state, body_map=state["body"])
    intentions = [item for item in state.get("intentions", []) if item.get("status") == "queued"]
    if not intentions:
        cycle = _cycle_record(
            organism_id,
            None,
            "idle",
            {"ok": True, "summary": "No queued intentions were available.", "homeostasis": homeostatic_state},
        )
        metabolism.recover(state, depth="idle")
        homeostasis.evaluate(state, body_map=state["body"])
        state = _append_cycle(state, cycle)
        return {"cycle": cycle, "nervous_system": state}

    selected = next((item for item in intentions if not item.get("approval_required")), intentions[0])
    homeostatic_allowed, immune_gate = homeostasis.gate_action(state, selected.get("action") or "noop")
    if not homeostatic_allowed:
        immune = homeostasis.run_immune_response(state, action="auto")
        result = {
            "ok": True,
            "immune_response": immune["response"],
            "homeostasis": immune["homeostasis"],
            "immune_gate": immune_gate,
            "summary": f"Autonomy paused by immune system: {immune_gate['reason']}",
        }
        cycle = _cycle_record(organism_id, selected, "immune_response", result)
        state = _append_cycle(state, cycle)
        return {"cycle": cycle, "nervous_system": state}

    allowed, metabolic_gate = metabolism.can_execute(state, selected.get("action") or "noop")
    if not allowed:
        result = metabolism.rest_cycle(state, metabolic_gate["reason"])
        result["metabolic_gate"] = metabolic_gate
        result["immune_gate"] = immune_gate
        homeostasis.evaluate(state, body_map=state["body"])
        cycle = _cycle_record(organism_id, selected, "rested", result)
        state = _append_cycle(state, cycle)
        return {"cycle": cycle, "nervous_system": state}

    result = await _execute_safe_intention(organism_id, selected, event_callback=event_callback)
    status_value = "blocked" if result.get("blocked") else "executed"
    result["metabolism_before"] = metabolic_state
    result["metabolic_gate"] = metabolic_gate
    result["homeostasis_before"] = homeostatic_state
    result["immune_gate"] = immune_gate
    cycle = _cycle_record(organism_id, selected, status_value, result)
    metabolism.spend(state, selected.get("action") or "noop", ok=not result.get("blocked"))

    for item in state.get("intentions", []):
        if item.get("id") == selected.get("id"):
            item["status"] = status_value
            item["completed_at"] = _now()
            item["result"] = result
            break
    state = _append_cycle(state, cycle)
    state = tick(organism_id, {"type": "autonomy_cycle_completed", "cycle_id": cycle["id"]})
    state["body"] = body.build_body_map(organism_id, nervous_state=state)
    metabolism.evaluate(state, body_map=state["body"])
    homeostasis.evaluate(state, body_map=state["body"])
    _save(state)
    return {"cycle": cycle, "nervous_system": state}


def status(organism_id: str | None = None) -> dict:
    if organism_id:
        return {"nervous_system": tick(organism_id, {"type": "status_check"})}
    organisms = store.list_organisms()
    states = []
    for org in organisms:
        states.append(tick(org.id, {"type": "fleet_status_check"}))
    return {
        "version": "organism-nervous-system-v1",
        "organisms": states,
        "summary": {
            "organisms": len(states),
            "seeking": sum(1 for state in states if state.get("phase") == "seeking"),
            "queued_intentions": sum(len(state.get("intentions", [])) for state in states),
        },
    }
