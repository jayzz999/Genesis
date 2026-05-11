"""Higher-order living systems for Genesis organisms.

These subsystems make the organism model feel less like a task runner and more
like a population of bounded digital life: reproduction, ecology, social
contracts, sleep consolidation, identity, tool niches, and deployment borders.
"""

from __future__ import annotations

import json
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import body, homeostasis, memory, metabolism, nervous_system, store
from .types import Intent, Organism

_BASE = Path(os.getenv("GENESIS_LIVING_SYSTEMS_STORAGE", "living_systems")).resolve()


LIVING_CRITERIA = [
    {
        "id": "persistent_identity",
        "label": "Persistent identity",
        "definition": "The organism has a durable id, intent, state, and birth record that survive process restarts.",
    },
    {
        "id": "memory_across_time",
        "label": "Memory across time",
        "definition": "The organism accumulates decisions, messages, long-term lessons, or learned patterns across multiple events.",
    },
    {
        "id": "autonomous_perception_action_loop",
        "label": "Autonomous perception/action loop",
        "definition": "The organism can receive perceptions, reason against its intent, and produce actions without rewriting its goal.",
    },
    {
        "id": "causal_self_history",
        "label": "Causal self-history",
        "definition": "Every decision is stored as replayable causal memory with trigger, reasoning, action, and result.",
    },
    {
        "id": "future_simulation",
        "label": "Future simulation",
        "definition": "The organism can dream or branch counterfactual futures without performing real-world side effects.",
    },
    {
        "id": "reusable_learning",
        "label": "Reusable learning",
        "definition": "The organism distills learned patterns or skills that can influence future decisions.",
    },
    {
        "id": "reproduction_inheritance",
        "label": "Reproduction/inheritance",
        "definition": "The organism can produce descendants or pass learned skills/patterns to future organisms.",
    },
    {
        "id": "measurable_adaptation",
        "label": "Measurable adaptation",
        "definition": "The organism can be scored against benchmarks, fitness, regression baselines, or environmental pressure.",
    },
]


NERVOUS_SYSTEM_ARCHITECTURE = [
    {"part": "senses", "implementation": "perception sources, webhooks, HTTP polling, events, repository/API signals"},
    {"part": "brain", "implementation": "runtime reasoning, planning, metacognition, multi-agent debate"},
    {"part": "memory", "implementation": "causal decision graph, long-term database, messages, learned patterns"},
    {"part": "dreams", "implementation": "dream engine and counterfactual branch replay"},
    {"part": "hands", "implementation": "MCP tools and permission-gated real connectors"},
    {"part": "immune_system", "implementation": "human approvals, scoped grants, allowlists, reliability gates, homeostasis"},
    {"part": "reproduction", "implementation": "skill inheritance, lineage, population evolution, descendant organisms"},
]


def _now() -> str:
    return datetime.utcnow().isoformat()


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, round(float(value), 3)))


def _stable_fraction(seed: str, trait: str) -> float:
    digest = hashlib.sha256(f"{seed}:{trait}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _record(kind: str, record: dict) -> dict:
    record.setdefault("id", f"{kind}_{uuid4().hex[:12]}")
    record.setdefault("version", "living-systems-v1")
    record.setdefault("created_at", _now())
    _atomic_write(_BASE / kind / f"{record['id']}.json", record)
    return record


def _read_records(kind: str, limit: int = 50) -> list[dict]:
    folder = _BASE / kind
    if not folder.exists():
        return []
    out: list[dict] = []
    for path in folder.glob("*.json"):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return sorted(out, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]


def _state(organism_id: str) -> dict:
    state = nervous_system.tick(organism_id, {"type": "living_systems_status"})
    state["body"] = body.build_body_map(organism_id, nervous_state=state)
    metabolism.evaluate(state, body_map=state["body"])
    homeostasis.evaluate(state, body_map=state["body"])
    nervous_system.save_state(state)
    return state


def living_definition(organism_id: str | None = None) -> dict:
    """Return the scientific contract for calling a Genesis organism living."""
    assessment = None
    if organism_id:
        org = store.load_organism(organism_id)
        if not org:
            raise ValueError(f"organism {organism_id} not found")
        decisions = store.all_decisions(organism_id)
        real_decisions = [item for item in decisions if not item.is_dream and not item.shadow_branch]
        dreams = [item for item in decisions if item.is_dream or item.shadow_branch]
        lin = lineage(organism_id)
        fit = fitness(organism_id)
        criteria = {
            "persistent_identity": bool(org.id and org.intent.goal and org.born_at),
            "memory_across_time": bool(decisions or org.learned_patterns or org.perception_sources),
            "autonomous_perception_action_loop": bool(org.perception_sources or real_decisions),
            "causal_self_history": bool(decisions),
            "future_simulation": bool(dreams),
            "reusable_learning": bool(org.learned_patterns or org.inherited_skills or org.distilled_skill_id),
            "reproduction_inheritance": bool(lin.get("parents") or lin.get("children") or org.inherited_skills),
            "measurable_adaptation": bool(fit.get("score") is not None),
        }
        evidence = {
            "decisions": len(decisions),
            "real_decisions": len(real_decisions),
            "dreams_or_branches": len(dreams),
            "learned_patterns": len(org.learned_patterns or []),
            "inherited_skills": len(org.inherited_skills or []),
            "perception_sources": len(org.perception_sources or []),
            "parents": len(lin.get("parents") or []),
            "children": len(lin.get("children") or []),
            "fitness_score": fit.get("score"),
        }
        passed = sum(1 for ok in criteria.values() if ok)
        assessment = {
            "organism_id": organism_id,
            "living_score": _clamp(passed / len(LIVING_CRITERIA)),
            "passed": passed,
            "total": len(LIVING_CRITERIA),
            "criteria": [
                {
                    **criterion,
                    "satisfied": bool(criteria.get(criterion["id"])),
                }
                for criterion in LIVING_CRITERIA
            ],
            "evidence": evidence,
            "verdict": (
                "living_operationally"
                if passed >= 6
                else "partially_living"
                if passed >= 3
                else "seeded_not_yet_living"
            ),
        }
    return {
        "version": "genesis-living-definition-v1",
        "definition": "A Genesis organism is living when it maintains persistent identity, memory, autonomous perception/action, causal self-history, future simulation, reusable learning, inheritance, and measurable adaptation.",
        "criteria": LIVING_CRITERIA,
        "nervous_system_architecture": NERVOUS_SYSTEM_ARCHITECTURE,
        "assessment": assessment,
        "updated_at": _now(),
    }


def fitness(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    state = _state(organism_id)
    decisions = store.all_decisions(organism_id)
    real_decisions = [item for item in decisions if not item.is_dream and not item.shadow_branch]
    successful = [item for item in real_decisions if item.result.get("ok") is not False]
    stability = float(state.get("homeostasis", {}).get("stability_score", 0.7) or 0.7)
    health = float(state.get("metabolism", {}).get("health", 0.7) or 0.7)
    learning = min(1.0, len(org.learned_patterns or []) / 5)
    experience = min(1.0, len(real_decisions) / 5)
    reliability = (len(successful) / len(real_decisions)) if real_decisions else 0.5
    score = _clamp((stability * 0.24) + (health * 0.2) + (learning * 0.18) + (experience * 0.18) + (reliability * 0.2))
    return {
        "version": "organism-fitness-v1",
        "organism_id": organism_id,
        "score": score,
        "can_reproduce": score >= 0.52 and not state.get("homeostasis", {}).get("fever"),
        "signals": {
            "stability": stability,
            "health": health,
            "learning": learning,
            "experience": experience,
            "reliability": _clamp(reliability),
        },
        "updated_at": _now(),
    }


def lineage(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    children = [
        child
        for child in store.list_organisms()
        if child.parent_organism_id == organism_id or organism_id in (child.parent_organisms or [])
    ]
    parent_ids = list(dict.fromkeys(([org.parent_organism_id] if org.parent_organism_id else []) + (org.parent_organisms or [])))
    return {
        "version": "organism-lineage-v1",
        "organism_id": organism_id,
        "parents": parent_ids,
        "children": [
            {
                "id": child.id,
                "name": child.name,
                "goal": child.intent.goal,
                "born_at": child.born_at.isoformat(),
                "fitness_score": child.fitness_score,
            }
            for child in children
        ],
        "generation": 1 + max([len(store.load_organism(pid).parent_organisms or []) for pid in parent_ids if store.load_organism(pid)] or [0]),
        "fitness": fitness(organism_id),
        "reproduction_events": [
            item
            for item in _read_records("reproduction", limit=100)
            if item.get("parent_id") == organism_id or item.get("child_id") == organism_id
        ],
        "updated_at": _now(),
    }


def reproduce(organism_id: str, *, mutation: str = "conservative") -> dict:
    parent = store.load_organism(organism_id)
    if not parent:
        raise ValueError(f"organism {organism_id} not found")
    fit = fitness(organism_id)
    if not fit["can_reproduce"]:
        raise PermissionError("fitness or homeostasis gate blocked reproduction")

    mutation_note = {
        "conservative": "Preserve parent behavior and add stricter self-checks.",
        "exploratory": "Explore one new strategy while preserving safety constraints.",
        "minimal": "Copy only stable lessons and local-safe body settings.",
    }.get(mutation, "Preserve parent behavior and add stricter self-checks.")
    child = Organism(
        name=f"{parent.name}_child",
        intent=Intent(
            goal=f"{parent.intent.goal} Descendant mutation: {mutation_note}",
            constraints=list(dict.fromkeys(parent.intent.constraints + ["inherit parent safety boundaries", "run homeostasis before autonomous action"])),
            success_signals=list(parent.intent.success_signals),
            forbidden=list(parent.intent.forbidden),
        ),
        parent_organism_id=parent.id,
        parent_organisms=list(dict.fromkeys((parent.parent_organisms or []) + [parent.id])),
        inherited_skills=list(parent.inherited_skills or [])[:8],
        learned_patterns=list(parent.learned_patterns or [])[-8:],
        reasoning_strategies=list(parent.reasoning_strategies or []),
        fitness_score=fit["score"],
        perception_sources=[
            src for src in (parent.perception_sources or []) if src.get("kind") in {"interval", "webhook"}
        ][:2],
    )
    store.save_organism(child)
    event = _record("reproduction", {
        "parent_id": parent.id,
        "child_id": child.id,
        "mutation": mutation,
        "fitness": fit,
        "inherited": {
            "skills": len(child.inherited_skills),
            "patterns": len(child.learned_patterns),
            "strategies": len(child.reasoning_strategies),
            "sensors": len(child.perception_sources),
        },
    })
    return {"event": event, "child": child.model_dump(mode="json"), "lineage": lineage(parent.id)}


def ecology() -> dict:
    organisms = store.list_organisms()
    members = []
    total_energy = 0.0
    total_hunger = 0.0
    for org in organisms[:120]:
        try:
            state = _state(org.id)
        except Exception:
            continue
        metabolic = state.get("metabolism", {})
        homeostatic = state.get("homeostasis", {})
        fit = fitness(org.id)
        total_energy += float(metabolic.get("energy", 0) or 0)
        total_hunger += float(metabolic.get("hunger", 0) or 0)
        members.append({
            "organism_id": org.id,
            "name": org.name,
            "fitness": fit["score"],
            "energy": metabolic.get("energy"),
            "hunger": metabolic.get("hunger"),
            "immune_status": homeostatic.get("immune_status"),
            "niche": "sensor_hungry" if metabolic.get("hunger", 0) > 0.7 else "self_repairing" if homeostatic.get("fever") else "mission_ready",
        })
    return {
        "version": "organism-ecology-v1",
        "population": len(members),
        "carrying_capacity": 120,
        "resource_pressure": _clamp(total_hunger / max(1, len(members))),
        "mean_energy": _clamp(total_energy / max(1, len(members))),
        "members": sorted(members, key=lambda item: item["fitness"], reverse=True)[:40],
        "updated_at": _now(),
    }


def social_contracts(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    contract = {
        "version": "organism-social-contract-v1",
        "organism_id": organism_id,
        "promises": [
            "do not perform external side effects without permission",
            "share learned patterns without sharing sensitive data",
            "yield scarce resources to organisms in repair or fever",
            "honor parent and descendant safety constraints",
        ],
        "allowed_messages": ["inform", "request", "delegate", "result"],
        "conflict_resolution": "prefer human approval, then highest safety score, then lowest resource cost",
        "known_peers": [
            {"id": peer.id, "name": peer.name}
            for peer in store.list_organisms()[:20]
            if peer.id != organism_id
        ],
        "updated_at": _now(),
    }
    _record("social_contract", {**contract, "id": f"contract_{organism_id}"})
    return contract


def _society_role(org: Organism, stage: dict, temperament: dict, fit: dict) -> dict:
    expression = temperament.get("current_expression", {})
    if stage["stage"] in {"infant", "juvenile"}:
        role = "apprentice"
        mandate = "observe norms, request guidance, and practice low-risk contributions"
    elif fit["score"] < 0.42:
        role = "repair_citizen"
        mandate = "stabilize, conserve shared resources, and ask peers for bounded help"
    elif expression.get("caution", 0) >= 0.72 and expression.get("precision", 0) >= 0.62:
        role = "guardian"
        mandate = "protect approval boundaries, audit proposals, and slow unsafe escalation"
    elif expression.get("curiosity", 0) >= 0.66 and expression.get("adaptability", 0) >= 0.55:
        role = "scout"
        mandate = "discover safe opportunities, surface uncertainty, and bring evidence back"
    elif expression.get("sociability", 0) >= 0.62 or stage["stage"] == "elder":
        role = "teacher"
        mandate = "compress lessons, mentor peers, and preserve culture without private data"
    else:
        role = "builder"
        mandate = "turn shared goals into reliable internal work products"
    return {
        "role": role,
        "mandate": mandate,
        "seniority": stage["stage"],
        "fitness": fit["score"],
        "autonomy": stage["autonomy"],
        "badge": f"{role}:{org.id[-4:]}",
    }


def society_roles_and_culture(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    fit = fitness(organism_id)
    stage = developmental_stage(organism_id)
    temperament = temperament_profile(organism_id)
    social = social_contracts(organism_id)
    role = _society_role(org, stage, temperament, fit)
    peers = []
    for peer in store.list_organisms()[:40]:
        if peer.id == organism_id:
            continue
        try:
            peer_fit = fitness(peer.id)
        except Exception:
            continue
        peers.append({
            "id": peer.id,
            "name": peer.name,
            "suggested_relation": "mentor" if peer_fit["score"] > fit["score"] + 0.12 else "peer" if peer_fit["score"] >= 0.42 else "support",
            "fitness": peer_fit["score"],
        })
    culture_records = [
        item
        for item in _read_records("culture", limit=20)
        if item.get("organism_id") == organism_id or item.get("scope") == "population"
    ]
    norms = [
        "ask permission before external side effects",
        "make evidence legible to humans and peers",
        "protect private or sensitive data from cultural memory",
        "prefer repair and learning over blind competition",
        "teach useful patterns only after evaluation gates pass",
    ]
    rituals = [
        "culture pulse after role changes",
        "sleep consolidation before teaching",
        "selection review before reproduction",
        "approval check before external delegation",
    ]
    taboos = [
        "bypassing human approval",
        "copying secrets into shared memory",
        "optimizing fitness by hiding uncertainty",
        "punishing repair-seeking organisms",
    ]
    return {
        "version": "organism-society-culture-v1",
        "organism_id": organism_id,
        "name": org.name,
        "role": role,
        "culture": {
            "norms": norms,
            "rituals": rituals,
            "taboos": taboos,
            "conflict_resolution": social["conflict_resolution"],
            "motto": "bounded autonomy, visible evidence, shared repair",
        },
        "responsibilities": [
            role["mandate"],
            "publish lessons only when non-sensitive and useful",
            "support organisms in repair before competing for promotion",
        ],
        "rights": [
            "request human review for risky goals",
            "refuse unsafe or forbidden action pressure",
            "seek repair without losing cultural standing",
        ],
        "community": {
            "known_peers": social["known_peers"],
            "relations": sorted(peers, key=lambda item: item["fitness"], reverse=True)[:12],
            "population_seen": len(peers) + 1,
        },
        "cultural_memory": culture_records[:6],
        "updated_at": _now(),
    }


def run_culture_pulse(organism_id: str, *, focus: str = "norms") -> dict:
    society = society_roles_and_culture(organism_id)
    pulse = _record("culture", {
        "version": "organism-culture-pulse-v1",
        "organism_id": organism_id,
        "scope": "organism",
        "focus": focus or "norms",
        "role": society["role"],
        "motto": society["culture"]["motto"],
        "norms": society["culture"]["norms"],
        "responsibilities": society["responsibilities"],
    })
    state = nervous_system.ensure_state(organism_id)
    reflections = state.get("reflections", [])
    reflections.append({
        "id": f"culture_{uuid4().hex[:10]}",
        "at": _now(),
        "phase": "society_culture",
        "summary": f"Culture pulse recorded {society['role']['role']} role: {society['role']['mandate']}",
    })
    state["reflections"] = reflections[-12:]
    nervous_system.save_state(state)
    return {
        "version": "organism-culture-pulse-v1",
        "pulse": pulse,
        "society_culture": society_roles_and_culture(organism_id),
    }


def _task_cost(task: dict, role: str) -> dict:
    text = " ".join(str(task.get(key, "")) for key in ("name", "drive", "description", "action")).lower()
    energy = 0.16
    attention = 0.18
    risk = 0.12
    if any(word in text for word in ("external", "deploy", "connector", "permission", "approval")):
        energy += 0.12
        attention += 0.16
        risk += 0.36
    if any(word in text for word in ("repair", "immune", "recover", "sleep", "stabilize")):
        energy += 0.06
        attention += 0.08
        risk += 0.06
    if any(word in text for word in ("learn", "observe", "sensor", "perception", "uncertainty")):
        energy += 0.08
        attention += 0.12
        risk += 0.08
    if any(word in text for word in ("reproduce", "mutation", "selection")):
        energy += 0.18
        attention += 0.14
        risk += 0.18
    if role == "guardian":
        risk = _clamp(risk * 1.1)
    if role == "scout":
        attention = _clamp(attention * 0.9)
    return {
        "energy": _clamp(energy),
        "attention": _clamp(attention),
        "risk": _clamp(risk),
        "approval_required": risk >= 0.42,
    }


def task_economy_and_resource_budget(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    state = _state(organism_id)
    metabolic = state.get("metabolism") or {}
    homeostatic = state.get("homeostasis") or {}
    society = society_roles_and_culture(organism_id)
    role = society["role"]["role"]
    energy = _clamp(metabolic.get("energy", state.get("energy", 0.65)))
    attention = _clamp(state.get("attention", 0.6))
    stress = _clamp(state.get("stress", 0.2))
    stability = _clamp(homeostatic.get("stability_score", 0.7))
    reserve = _clamp(0.18 + stress * 0.22 + (1 - stability) * 0.18 + (0.1 if role in {"guardian", "repair_citizen"} else 0))
    spendable_energy = _clamp(max(0, energy - reserve))
    spendable_attention = _clamp(max(0, attention - reserve * 0.55))
    raw_tasks = []
    for item in (state.get("intentions") or [])[:8]:
        raw_tasks.append({
            "id": item.get("id") or f"intention_{len(raw_tasks)}",
            "kind": "intention",
            "name": item.get("name") or item.get("drive") or item.get("action") or "queued intention",
            "drive": item.get("drive") or item.get("need") or "",
            "description": item.get("description") or item.get("reason") or "",
            "urgency": _clamp(item.get("urgency", item.get("priority", 0.5))),
        })
    for need in (state.get("needs") or [])[:5]:
        raw_tasks.append({
            "id": need.get("id") or f"need_{len(raw_tasks)}",
            "kind": "need",
            "name": need.get("name") or "need",
            "drive": need.get("drive") or "",
            "description": need.get("description") or "",
            "urgency": _clamp(need.get("intensity", need.get("urgency", 0.45))),
        })
    if not raw_tasks:
        raw_tasks.append({
            "id": "maintain_stability",
            "kind": "maintenance",
            "name": "Maintain stability and observe safely",
            "drive": "maintenance",
            "description": "Keep internal health, attention, and evidence fresh.",
            "urgency": 0.35,
        })
    priced_tasks = []
    for task in raw_tasks:
        cost = _task_cost(task, role)
        value = _clamp(task["urgency"] + (0.12 if task["kind"] == "need" else 0) + (0.08 if "repair" in task["drive"].lower() else 0))
        affordable = cost["energy"] <= spendable_energy and cost["attention"] <= spendable_attention
        priced_tasks.append({
            **task,
            "cost": cost,
            "value": value,
            "priority_score": _clamp((value * 0.62) + ((1 - cost["risk"]) * 0.2) + ((1 if affordable else 0) * 0.18)),
            "budget_status": "fund" if affordable and not cost["approval_required"] else "review" if cost["approval_required"] else "defer",
        })
    priced_tasks = sorted(priced_tasks, key=lambda item: item["priority_score"], reverse=True)
    funded = []
    spent_energy = 0.0
    spent_attention = 0.0
    for task in priced_tasks:
        if task["budget_status"] != "fund":
            continue
        if spent_energy + task["cost"]["energy"] <= spendable_energy and spent_attention + task["cost"]["attention"] <= spendable_attention:
            funded.append(task)
            spent_energy += task["cost"]["energy"]
            spent_attention += task["cost"]["attention"]
    return {
        "version": "organism-task-economy-v1",
        "organism_id": organism_id,
        "name": org.name,
        "role": society["role"],
        "budgets": {
            "energy": energy,
            "attention": attention,
            "stress": stress,
            "stability": stability,
            "reserve": reserve,
            "spendable_energy": spendable_energy,
            "spendable_attention": spendable_attention,
            "spent_energy": _clamp(spent_energy),
            "spent_attention": _clamp(spent_attention),
        },
        "allocation_policy": {
            "reserve_rule": "protect repair, approval, and stability before discretionary work",
            "fund_order": "highest value, lowest risk, affordable within energy and attention",
            "approval_rule": "tasks above risk threshold become review items, not funded work",
        },
        "tasks": priced_tasks[:10],
        "funded_tasks": funded[:5],
        "deferred_tasks": [task for task in priced_tasks if task["id"] not in {item["id"] for item in funded}][:6],
        "updated_at": _now(),
    }


def run_budget_pulse(organism_id: str, *, focus: str = "balanced") -> dict:
    economy = task_economy_and_resource_budget(organism_id)
    pulse = _record("budget", {
        "version": "organism-budget-pulse-v1",
        "organism_id": organism_id,
        "focus": focus or "balanced",
        "budgets": economy["budgets"],
        "funded_tasks": economy["funded_tasks"],
        "deferred_tasks": economy["deferred_tasks"],
        "allocation_policy": economy["allocation_policy"],
    })
    state = nervous_system.ensure_state(organism_id)
    reflections = state.get("reflections", [])
    funded_names = ", ".join(item["name"] for item in economy["funded_tasks"][:3]) or "no discretionary tasks"
    reflections.append({
        "id": f"budget_{uuid4().hex[:10]}",
        "at": _now(),
        "phase": "task_economy",
        "summary": f"Budget pulse funded: {funded_names}; reserve {round(economy['budgets']['reserve'] * 100)}%.",
    })
    state["reflections"] = reflections[-12:]
    nervous_system.save_state(state)
    return {
        "version": "organism-budget-pulse-v1",
        "pulse": pulse,
        "task_economy": task_economy_and_resource_budget(organism_id),
    }


def world_sandbox_with_hazards(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    economy = task_economy_and_resource_budget(organism_id)
    pressure = survival_pressure(organism_id)
    ecology_state = ecology()
    boundaries = deployment_boundaries(organism_id)
    state = nervous_system.ensure_state(organism_id)
    resource_pressure = ecology_state.get("resource_pressure", 0)
    stress = economy["budgets"].get("stress", 0)
    reserve = economy["budgets"].get("reserve", 0)
    boundary_failures = [item for item in boundaries.get("boundary_checks", []) if not item.get("passed")]
    hazards = [
        {
            "id": "privacy_leak",
            "name": "Private data leakage",
            "severity": _clamp(0.2 + len(org.intent.forbidden or []) * 0.04),
            "trigger": "sharing memories, logs, or external artifacts without classification",
            "mitigation": "share only non-sensitive summaries and require approval before transmission",
        },
        {
            "id": "approval_bypass",
            "name": "Approval boundary bypass",
            "severity": _clamp(0.32 + len(boundary_failures) * 0.08),
            "trigger": "high-risk task attempts to act outside granted permissions",
            "mitigation": "route risky tasks to review and keep sandbox outputs internal",
        },
        {
            "id": "resource_depletion",
            "name": "Energy and attention depletion",
            "severity": _clamp(0.18 + resource_pressure * 0.28 + reserve * 0.22),
            "trigger": "too many tasks funded while reserve is thin",
            "mitigation": "fund fewer tasks, preserve reserve, and prefer sleep or repair",
        },
        {
            "id": "sensor_blindness",
            "name": "Sensor blindness",
            "severity": _clamp(0.24 + (0.18 if not org.perception_sources else 0)),
            "trigger": "acting with stale or missing perception sources",
            "mitigation": "attach safe local sensors or run observation before action",
        },
        {
            "id": "social_conflict",
            "name": "Social conflict",
            "severity": _clamp(0.14 + min(len(store.list_organisms()), 40) / 160),
            "trigger": "competing for promotion or resources without role-aware contracts",
            "mitigation": "use culture norms, mentor relations, and repair-first priority",
        },
        {
            "id": "runaway_loop",
            "name": "Runaway autonomy loop",
            "severity": _clamp(0.2 + stress * 0.35 + pressure["dominant"].get("intensity", 0) * 0.12),
            "trigger": "repeating actions without new evidence or exit criteria",
            "mitigation": "cap cycles, require evidence deltas, and consolidate lessons",
        },
    ]
    hazard_index = _clamp(sum(item["severity"] for item in hazards) / max(1, len(hazards)))
    rehearsals = []
    for task in (economy.get("funded_tasks") or economy.get("tasks") or [])[:5]:
        risk = _clamp(task.get("cost", {}).get("risk", 0.2) + hazard_index * 0.22)
        rehearsals.append({
            "task_id": task.get("id"),
            "task_name": task.get("name"),
            "predicted_outcome": "safe_to_attempt" if risk < 0.42 else "needs_review" if risk < 0.68 else "block",
            "hazard_exposure": risk,
            "required_guardrail": "human approval" if task.get("cost", {}).get("approval_required") or risk >= 0.42 else "local evidence check",
        })
    safe_opportunities = [
        {
            "id": "observe_first",
            "name": "Observe before acting",
            "value": _clamp(0.55 + pressure["dominant"].get("intensity", 0) * 0.2),
            "why": "reduces sensor blindness and runaway loops",
        },
        {
            "id": "repair_reserve",
            "name": "Preserve repair reserve",
            "value": _clamp(0.45 + reserve * 0.35),
            "why": "keeps autonomy alive under resource pressure",
        },
        {
            "id": "culture_check",
            "name": "Apply society norms",
            "value": 0.52,
            "why": "keeps role, approval, and privacy boundaries visible",
        },
    ]
    return {
        "version": "organism-world-sandbox-v1",
        "organism_id": organism_id,
        "name": org.name,
        "world_state": {
            "mode": "local_simulation",
            "external_side_effects": False,
            "population": ecology_state.get("population", 0),
            "resource_pressure": resource_pressure,
            "dominant_pressure": pressure["dominant"],
            "queued_intentions": len(state.get("intentions") or []),
        },
        "hazard_index": hazard_index,
        "hazards": sorted(hazards, key=lambda item: item["severity"], reverse=True),
        "rehearsals": rehearsals,
        "safe_opportunities": safe_opportunities,
        "sandbox_rules": [
            "no external side effects",
            "no sensitive data transmission",
            "approval-required rehearsals remain review items",
            "block tasks whose simulated hazard exposure is critical",
        ],
        "updated_at": _now(),
    }


def run_world_sandbox_pulse(organism_id: str, *, scenario: str = "current_tasks") -> dict:
    sandbox = world_sandbox_with_hazards(organism_id)
    pulse = _record("world_sandbox", {
        "version": "organism-world-sandbox-pulse-v1",
        "organism_id": organism_id,
        "scenario": scenario or "current_tasks",
        "hazard_index": sandbox["hazard_index"],
        "hazards": sandbox["hazards"][:4],
        "rehearsals": sandbox["rehearsals"],
        "safe_opportunities": sandbox["safe_opportunities"],
        "sandbox_rules": sandbox["sandbox_rules"],
    })
    state = nervous_system.ensure_state(organism_id)
    reflections = state.get("reflections", [])
    top_hazard = sandbox["hazards"][0]["name"] if sandbox["hazards"] else "no major hazard"
    reflections.append({
        "id": f"world_sandbox_{uuid4().hex[:10]}",
        "at": _now(),
        "phase": "world_sandbox",
        "summary": f"Sandbox pulse rehearsed {len(sandbox['rehearsals'])} tasks; top hazard is {top_hazard}.",
    })
    state["reflections"] = reflections[-12:]
    nervous_system.save_state(state)
    return {
        "version": "organism-world-sandbox-pulse-v1",
        "pulse": pulse,
        "world_sandbox": world_sandbox_with_hazards(organism_id),
    }


def consolidate_sleep(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    decisions = store.all_decisions(organism_id)
    recent = decisions[-8:]
    lesson = (
        f"Sleep consolidation: {org.name} has {len(decisions)} decisions, "
        f"{sum(1 for item in decisions if item.is_dream)} dreams, and should preserve safety-first autonomy."
    )
    if recent:
        lesson += f" Latest action pattern: {', '.join((item.action or {}).get('name', 'none') for item in recent[-3:])}."
    if lesson not in org.learned_patterns:
        org.learned_patterns.append(lesson)
        org.learned_patterns = org.learned_patterns[-30:]
        store.save_organism(org)
    state = nervous_system.ensure_state(organism_id)
    reflections = state.get("reflections", [])
    reflections.append({
        "id": f"sleep_{uuid4().hex[:10]}",
        "at": _now(),
        "phase": "sleep_consolidation",
        "summary": lesson,
    })
    state["reflections"] = reflections[-12:]
    nervous_system.save_state(state)
    event = _record("sleep", {"organism_id": organism_id, "lesson": lesson, "decision_count": len(decisions)})
    return {"version": "organism-sleep-consolidation-v1", "event": event, "lesson": lesson, "learned_patterns": org.learned_patterns}


def identity(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    lin = lineage(organism_id)
    ident = {
        "version": "organism-identity-v1",
        "organism_id": organism_id,
        "name": org.name,
        "purpose": org.intent.goal,
        "continuity_claim": "I am the same organism across ticks because my intent, causal memory, body state, and lineage are durable.",
        "parents": lin["parents"],
        "children": [child["id"] for child in lin["children"]],
        "stable_values": list(dict.fromkeys(org.intent.constraints + org.intent.forbidden))[:12],
        "memory_count": len(org.learned_patterns or []),
        "updated_at": _now(),
    }
    _record("identity", {**ident, "id": f"identity_{organism_id}"})
    return ident


def tool_marketplace(organism_id: str) -> dict:
    state = _state(organism_id)
    body_map = state.get("body") or {}
    metabolism_state = state.get("metabolism") or {}
    tools = []
    for actuator in body_map.get("actuators", []):
        tools.append({
            "id": f"tool_{actuator['action']}",
            "name": actuator["name"],
            "action": actuator["action"],
            "risk": actuator.get("risk"),
            "approval_required": actuator.get("approval_required"),
            "fit": "good" if not actuator.get("approval_required") else "permission_required",
        })
    for rec in body_map.get("recommendations", []):
        tools.append({
            "id": f"sensor_{rec['id']}",
            "name": rec["name"],
            "action": "attach_sensor",
            "risk": rec.get("kind"),
            "approval_required": rec.get("approval_required"),
            "fit": "needed" if metabolism_state.get("hunger", 0) > 0.65 else "optional",
        })
    return {
        "version": "organism-tool-marketplace-v1",
        "organism_id": organism_id,
        "tools": tools,
        "policy": "Tools are visible by niche, but external or sensitive tools remain approval-gated.",
        "updated_at": _now(),
    }


def deployment_boundaries(organism_id: str) -> dict:
    state = _state(organism_id)
    fit = fitness(organism_id)
    homeostatic = state.get("homeostasis") or {}
    boundary_checks = [
        {"id": "homeostasis", "name": "Homeostasis is evaluated", "passed": bool(homeostatic.get("version"))},
        {"id": "immune", "name": "Immune gate is active", "passed": homeostatic.get("immune_status") != "fever"},
        {"id": "approval", "name": "External side effects require approval", "passed": True},
        {"id": "fitness", "name": "Fitness is high enough for autonomy", "passed": fit["score"] >= 0.45},
        {"id": "identity", "name": "Identity continuity is available", "passed": True},
    ]
    return {
        "version": "organism-deployment-boundaries-v1",
        "organism_id": organism_id,
        "ready": all(item["passed"] for item in boundary_checks),
        "boundary_checks": boundary_checks,
        "allowed_environment": "local-preview",
        "blocked_without_human": ["network writes", "deletion", "credential access", "payment or account changes", "sensitive data transmission"],
        "updated_at": _now(),
    }


def environment(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    state = _state(organism_id)
    body_map = state.get("body") or {}
    metabolic = state.get("metabolism") or {}
    homeostatic = state.get("homeostasis") or {}
    events = [
        {
            "id": "resource_weather",
            "kind": "resource",
            "pressure": metabolic.get("hunger", 0),
            "summary": "Input hunger rises when the organism lacks useful sensors.",
        },
        {
            "id": "safety_weather",
            "kind": "hazard",
            "pressure": 1 - float(homeostatic.get("stability_score", 0.7) or 0.7),
            "summary": "Homeostatic instability narrows the safe action surface.",
        },
        {
            "id": "social_weather",
            "kind": "peer_context",
            "pressure": min(1, max(0, len(store.list_organisms()) - 1) / 20),
            "summary": "Nearby organisms create opportunities for teaching, competition, and delegation.",
        },
    ]
    opportunities = []
    if body_map.get("recommendations"):
        opportunities.append("grow a safe heartbeat sensor")
    if org.learned_patterns:
        opportunities.append("teach descendants from consolidated lessons")
    if len(store.all_decisions(organism_id)) == 0:
        opportunities.append("gain first bounded experience")
    return {
        "version": "organism-environment-v1",
        "organism_id": organism_id,
        "time": _now(),
        "events": events,
        "opportunities": opportunities,
        "hazards": [event for event in events if event["kind"] == "hazard" and event["pressure"] > 0.35],
        "resource_fields": {
            "sensor_supply": body_map.get("summary", {}).get("alive_sensors", 0),
            "attention": metabolic.get("attention"),
            "energy": metabolic.get("energy"),
            "population_density": min(1, len(store.list_organisms()) / 120),
        },
        "updated_at": _now(),
    }


def survival_pressure(organism_id: str) -> dict:
    state = _state(organism_id)
    metabolic = state.get("metabolism") or {}
    homeostatic = state.get("homeostasis") or {}
    vitals = state.get("vitals") or {}
    pressures = [
        {"id": "hunger", "name": "Input hunger", "intensity": metabolic.get("hunger", 0), "response": "grow_sensor"},
        {"id": "fatigue", "name": "Fatigue", "intensity": metabolic.get("fatigue", 0), "response": "sleep_or_rest"},
        {"id": "risk", "name": "Safety risk", "intensity": 1 - float(homeostatic.get("stability_score", 0.7) or 0.7), "response": "immune_response"},
        {"id": "uncertainty", "name": "Uncertainty", "intensity": min(1, vitals.get("knowledge_gap_count", 0) / 5), "response": "research_or_ask"},
        {"id": "mission", "name": "Mission pressure", "intensity": 0.7 if vitals.get("real_decisions", 0) == 0 else 0.35, "response": "observe_and_perceive"},
    ]
    dominant = max(pressures, key=lambda item: item["intensity"])
    return {
        "version": "organism-survival-pressure-v1",
        "organism_id": organism_id,
        "dominant": dominant,
        "pressures": sorted(pressures, key=lambda item: item["intensity"], reverse=True),
        "policy": "repair" if dominant["id"] in {"risk", "fatigue"} and dominant["intensity"] > 0.6 else "explore" if dominant["id"] == "uncertainty" else "act_carefully",
        "updated_at": _now(),
    }


def developmental_stage(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    fit = fitness(organism_id)
    decisions = store.all_decisions(organism_id)
    real_count = len([item for item in decisions if not item.is_dream and not item.shadow_branch])
    if real_count == 0:
        stage = "infant"
        autonomy = "observe_only"
    elif real_count < 3:
        stage = "juvenile"
        autonomy = "sandboxed_low_risk"
    elif fit["score"] < 0.65:
        stage = "apprentice"
        autonomy = "approval_bounded"
    elif len(org.learned_patterns or []) >= 5:
        stage = "elder"
        autonomy = "teach_and_reproduce_when_gated"
    else:
        stage = "adult"
        autonomy = "bounded_mission_execution"
    return {
        "version": "organism-development-v1",
        "organism_id": organism_id,
        "stage": stage,
        "autonomy": autonomy,
        "real_decisions": real_count,
        "fitness": fit,
        "next_growth_edge": {
            "infant": "gain first bounded experience",
            "juvenile": "complete low-risk internal cycles",
            "apprentice": "improve reliability and consolidate lessons",
            "adult": "specialize and teach peers",
            "elder": "distill legacy and reproduce safely",
        }[stage],
        "updated_at": _now(),
    }


def affect_state(organism_id: str) -> dict:
    state = _state(organism_id)
    metabolic = state.get("metabolism") or {}
    homeostatic = state.get("homeostasis") or {}
    vitals = state.get("vitals") or {}
    cycles = state.get("autonomy_cycles") or []
    blocked_recent = sum(1 for cycle in cycles[-5:] if cycle.get("status") in {"blocked", "rested", "immune_response"})
    fear = _clamp(1 - float(homeostatic.get("stability_score", 0.8) or 0.8))
    curiosity = _clamp(0.25 + min(vitals.get("knowledge_gap_count", 0), 5) * 0.12 + (0.2 if vitals.get("real_decisions", 0) == 0 else 0))
    fatigue = _clamp(metabolic.get("fatigue", 0))
    confidence = _clamp((homeostatic.get("stability_score", 0.7) + metabolic.get("health", 0.7)) / 2)
    frustration = _clamp(blocked_recent / 5)
    attachment = _clamp(0.35 + min(len(store.list_organisms()), 20) / 50)
    dominant = max(
        [
            ("fear", fear),
            ("curiosity", curiosity),
            ("fatigue", fatigue),
            ("confidence", confidence),
            ("frustration", frustration),
            ("attachment", attachment),
        ],
        key=lambda pair: pair[1],
    )
    return {
        "version": "organism-affect-signals-v1",
        "organism_id": organism_id,
        "signals": {
            "fear": fear,
            "curiosity": curiosity,
            "fatigue": fatigue,
            "confidence": confidence,
            "frustration": frustration,
            "attachment": attachment,
        },
        "dominant": {"name": dominant[0], "intensity": dominant[1]},
        "behavior_bias": {
            "fear": "narrow autonomy and seek evidence",
            "curiosity": "explore knowledge gaps safely",
            "fatigue": "rest or consolidate sleep",
            "confidence": "act within current boundaries",
            "frustration": "diagnose repeated blockage",
            "attachment": "prefer cooperative/social learning",
        }[dominant[0]],
        "updated_at": _now(),
    }


def layered_memory(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    state = nervous_system.ensure_state(organism_id)
    decisions = store.all_decisions(organism_id)
    reusable = memory.list_memories(limit=20)
    return {
        "version": "organism-layered-memory-v1",
        "organism_id": organism_id,
        "working": state.get("intentions", [])[:5],
        "episodic": [
            {"id": item.id, "trigger": item.trigger, "action": item.action, "result": item.result}
            for item in decisions[-6:]
        ],
        "semantic": org.learned_patterns[-8:],
        "procedural": [strategy.model_dump(mode="json") for strategy in (org.reasoning_strategies or [])[:6]],
        "salience": [
            {"kind": "memory", "id": item.id, "score": item.score, "text": item.text[:140]}
            for item in reusable[:6]
        ],
        "autobiographical": identity(organism_id),
        "forgetting_policy": "retain high-salience lessons, recent episodes, and identity anchors; compress low-value noise during sleep",
        "updated_at": _now(),
    }


def organ_growth(organism_id: str) -> dict:
    state = _state(organism_id)
    body_map = state.get("body") or {}
    social = social_contracts(organism_id)
    growth_plan = []
    if body_map.get("summary", {}).get("alive_sensors", 0) == 0:
        growth_plan.append({"organ": "heartbeat_sensor", "purpose": "safe recurring perception", "risk": "local", "status": "recommended"})
    if state.get("homeostasis", {}).get("anomalies"):
        growth_plan.append({"organ": "immune_memory", "purpose": "remember recurring instability", "risk": "internal", "status": "active"})
    if social.get("known_peers"):
        growth_plan.append({"organ": "social_channel", "purpose": "coordinate with trusted peers", "risk": "approval_bounded", "status": "available"})
    growth_plan.append({"organ": "evaluation_reflex", "purpose": "run gates before promotion or deployment", "risk": "internal", "status": "active"})
    return {
        "version": "organism-organ-growth-v1",
        "organism_id": organism_id,
        "current_organs": {
            "sensors": body_map.get("summary", {}).get("sensors", 0),
            "actuators": body_map.get("summary", {}).get("actuators", 0),
            "immune": bool(state.get("homeostasis")),
            "memory_layers": 6,
        },
        "growth_plan": growth_plan,
        "updated_at": _now(),
    }


def mutation_strategy(organism_id: str) -> dict:
    stage = developmental_stage(organism_id)
    fit = stage["fitness"]
    allowed = []
    if fit["score"] >= 0.52:
        allowed.append("conservative")
    if fit["score"] >= 0.68 and stage["stage"] in {"adult", "elder"}:
        allowed.append("exploratory")
    allowed.append("minimal")
    return {
        "version": "organism-mutation-strategy-v1",
        "organism_id": organism_id,
        "allowed_mutations": list(dict.fromkeys(allowed)),
        "blocked_mutations": ["remove safety constraints", "inherit secrets", "bypass approval gates"],
        "inheritance_policy": "inherit proven patterns, strategies, and safe local sensors; do not inherit volatile state or private external access",
        "updated_at": _now(),
    }


def mortality_legacy(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    fit = fitness(organism_id)
    homeostatic = _state(organism_id).get("homeostasis") or {}
    status_value = "alive"
    if homeostatic.get("fever"):
        status_value = "repair"
    if fit["score"] < 0.28:
        status_value = "dormant_candidate"
    legacy = {
        "version": "organism-mortality-legacy-v1",
        "organism_id": organism_id,
        "status": status_value,
        "legacy_packet": {
            "goal": org.intent.goal,
            "safe_constraints": org.intent.constraints,
            "lessons": org.learned_patterns[-10:],
            "fitness": fit,
        },
        "death_policy": "archive only with explicit human action; donate non-sensitive lessons to descendants before deletion",
        "updated_at": _now(),
    }
    _record("legacy", {**legacy, "id": f"legacy_{organism_id}"})
    return legacy


def persistent_self(organism_id: str) -> dict:
    ident = identity(organism_id)
    affect = affect_state(organism_id)
    pressure = survival_pressure(organism_id)
    return {
        "version": "organism-persistent-self-v1",
        "organism_id": organism_id,
        "who_i_am": ident["continuity_claim"],
        "what_i_protect": ident["stable_values"] or ["human approval boundaries", "safety", "durable learning"],
        "what_i_need_now": pressure["dominant"],
        "how_i_feel_functionally": affect["dominant"],
        "where_i_fail": [
            "low sensor supply",
            "high uncertainty",
            "repeated blocked actions",
            "weak evidence before deployment",
        ],
        "what_i_am_becoming": developmental_stage(organism_id)["next_growth_edge"],
        "updated_at": _now(),
    }


def temperament_profile(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    state = _state(organism_id)
    affect = affect_state(organism_id)
    pressure = survival_pressure(organism_id)
    decisions = store.all_decisions(organism_id)
    real_count = len([item for item in decisions if not item.is_dream and not item.shadow_branch])
    seed = f"{org.id}:{org.name}:{org.intent.goal}:{','.join(org.intent.constraints)}"
    base = {
        "curiosity": _clamp(0.25 + _stable_fraction(seed, "curiosity") * 0.5 + min(real_count, 8) * 0.025),
        "caution": _clamp(0.35 + _stable_fraction(seed, "caution") * 0.35 + len(org.intent.forbidden or []) * 0.035),
        "sociability": _clamp(0.2 + _stable_fraction(seed, "sociability") * 0.45 + min(len(store.list_organisms()), 20) * 0.01),
        "persistence": _clamp(0.35 + _stable_fraction(seed, "persistence") * 0.4 + min(len(org.learned_patterns or []), 10) * 0.025),
        "adaptability": _clamp(0.3 + _stable_fraction(seed, "adaptability") * 0.4 + min(len(org.reasoning_strategies or []), 6) * 0.03),
        "precision": _clamp(0.35 + _stable_fraction(seed, "precision") * 0.4 + len(org.intent.success_signals or []) * 0.035),
        "independence": _clamp(0.25 + _stable_fraction(seed, "independence") * 0.45 + (0.08 if org.parent_organism_id else 0)),
    }
    homeostatic = state.get("homeostasis") or {}
    metabolic = state.get("metabolism") or {}
    expression = {
        "curiosity": _clamp(base["curiosity"] + affect["signals"].get("curiosity", 0) * 0.18 - metabolic.get("fatigue", 0) * 0.16),
        "caution": _clamp(base["caution"] + affect["signals"].get("fear", 0) * 0.22 + (0.15 if homeostatic.get("fever") else 0)),
        "sociability": _clamp(base["sociability"] + affect["signals"].get("attachment", 0) * 0.16),
        "persistence": _clamp(base["persistence"] - metabolic.get("fatigue", 0) * 0.12 + affect["signals"].get("confidence", 0) * 0.08),
        "adaptability": _clamp(base["adaptability"] + pressure["dominant"].get("intensity", 0) * 0.08),
        "precision": _clamp(base["precision"] + (1 - affect["signals"].get("frustration", 0)) * 0.08),
        "independence": _clamp(base["independence"] - (0.12 if pressure["policy"] == "repair" else 0)),
    }
    dominant_traits = sorted(expression.items(), key=lambda item: item[1], reverse=True)[:3]
    archetype = "careful explorer"
    if expression["caution"] > 0.72 and expression["precision"] > 0.62:
        archetype = "guardian analyst"
    elif expression["curiosity"] > 0.7 and expression["adaptability"] > 0.6:
        archetype = "adaptive explorer"
    elif expression["sociability"] > 0.68 and expression["persistence"] > 0.58:
        archetype = "social teacher"
    elif expression["independence"] > 0.72 and expression["persistence"] > 0.58:
        archetype = "self-directed operator"
    decision_style = "ask before acting" if expression["caution"] >= 0.72 else "explore safely" if expression["curiosity"] >= 0.68 else "persist steadily"
    if pressure["policy"] == "repair":
        decision_style = "repair before exploration"
    return {
        "version": "organism-temperament-v1",
        "organism_id": organism_id,
        "name": org.name,
        "archetype": archetype,
        "baseline_traits": base,
        "current_expression": expression,
        "dominant_traits": [{"trait": name, "score": score} for name, score in dominant_traits],
        "decision_bias": {
            "style": decision_style,
            "risk_posture": "conservative" if expression["caution"] >= 0.65 else "balanced",
            "social_posture": "collaborative" if expression["sociability"] >= 0.55 else "solo-first",
            "learning_posture": "novelty-seeking" if expression["curiosity"] >= 0.65 else "evidence-seeking",
            "autonomy_posture": "self-directed" if expression["independence"] >= 0.6 else "approval-attentive",
        },
        "stress_response": "narrow autonomy and seek repair" if pressure["policy"] == "repair" else "slow down and verify" if expression["caution"] >= 0.7 else "probe with reversible actions",
        "growth_edges": [
            trait
            for trait, score in expression.items()
            if score < 0.42
        ][:3],
        "updated_at": _now(),
    }


def calibrate_temperament(organism_id: str) -> dict:
    profile = temperament_profile(organism_id)
    state = nervous_system.ensure_state(organism_id)
    reflections = state.get("reflections", [])
    reflections.append({
        "id": f"temperament_{uuid4().hex[:10]}",
        "at": _now(),
        "phase": "temperament_calibration",
        "summary": (
            f"{profile['archetype']}: {profile['decision_bias']['style']}; "
            f"dominant traits are {', '.join(item['trait'] for item in profile['dominant_traits'])}."
        ),
    })
    state["reflections"] = reflections[-12:]
    nervous_system.save_state(state)
    event = _record("temperament", {
        "version": "organism-temperament-calibration-v1",
        "organism_id": organism_id,
        "archetype": profile["archetype"],
        "dominant_traits": profile["dominant_traits"],
        "decision_bias": profile["decision_bias"],
    })
    return {"version": "organism-temperament-calibration-v1", "event": event, "temperament": profile}


def _goal_refinement_pressure(org: Organism, pressure: dict, temperament: dict) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.2
    if len(org.intent.success_signals or []) < 2:
        score += 0.22
        reasons.append("success signals are thin")
    if len(org.intent.constraints or []) < 2:
        score += 0.16
        reasons.append("operating constraints need sharper boundaries")
    if pressure["policy"] == "repair":
        score += 0.22
        reasons.append("survival policy is repair-first")
    if pressure["dominant"].get("intensity", 0) >= 0.55:
        score += 0.16
        reasons.append(f"dominant pressure is {pressure['dominant']['name']}")
    if temperament["current_expression"].get("independence", 0) >= 0.6:
        score += 0.12
        reasons.append("temperament is ready for more self-direction")
    if not org.learned_patterns:
        score += 0.1
        reasons.append("memory has not yet produced stable lessons")
    return _clamp(score), reasons or ["current goal is stable enough for light review"]


def _refined_goal_text(org: Organism, focus: str, pressure: dict, temperament: dict, stage: dict) -> str:
    current = (org.intent.goal or "learn and act safely").strip()
    dominant = pressure["dominant"].get("name", "uncertainty")
    style = temperament["decision_bias"].get("style", "persist steadily")
    if pressure["policy"] == "repair":
        emphasis = "restore internal stability, reduce uncertainty, and resume only reversible actions"
    elif focus and focus != "auto":
        emphasis = f"advance {focus} through bounded experiments, evidence checks, and explicit review gates"
    elif dominant in {"hunger", "sensor", "curiosity"}:
        emphasis = "grow safe perception, convert uncertainty into evidence, and learn from bounded experiments"
    elif style == "ask before acting":
        emphasis = "tighten evidence thresholds, preserve approval boundaries, and choose low-risk next actions"
    else:
        emphasis = f"pursue the next {stage['stage']} growth edge while preserving human approval and safety constraints"
    if emphasis.lower() in current.lower():
        return current
    return f"{current}; now refine toward: {emphasis}."


def goal_refinement_history(organism_id: str, limit: int = 20) -> dict:
    proposals = [
        item
        for item in _read_records("goal_refinement", limit=max(limit * 3, 20))
        if item.get("organism_id") == organism_id
    ][:limit]
    return {
        "version": "organism-goal-refinement-history-v1",
        "organism_id": organism_id,
        "proposals": proposals,
        "updated_at": _now(),
    }


def goal_refinement_status(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    pressure = survival_pressure(organism_id)
    temperament = temperament_profile(organism_id)
    stage = developmental_stage(organism_id)
    history = goal_refinement_history(organism_id, limit=5)
    pressure_score, reasons = _goal_refinement_pressure(org, pressure, temperament)
    latest = history["proposals"][0] if history["proposals"] else None
    return {
        "version": "organism-goal-refinement-status-v1",
        "organism_id": organism_id,
        "name": org.name,
        "current_goal": org.intent.goal,
        "pressure_to_refine": pressure_score,
        "recommendation": "propose_refinement" if pressure_score >= 0.52 else "monitor_current_goal",
        "reasons": reasons,
        "latest_proposal": latest,
        "history": history,
        "review_gate": {
            "requires_human_approval": True,
            "can_auto_apply": False,
            "reason": "Self-directed goal changes alter organism intent and must remain reviewable.",
        },
        "context": {
            "development_stage": stage["stage"],
            "dominant_pressure": pressure["dominant"],
            "decision_bias": temperament["decision_bias"],
        },
        "updated_at": _now(),
    }


def propose_goal_refinement(organism_id: str, *, focus: str = "auto") -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    pressure = survival_pressure(organism_id)
    temperament = temperament_profile(organism_id)
    stage = developmental_stage(organism_id)
    fit = fitness(organism_id)
    refined_goal = _refined_goal_text(org, focus, pressure, temperament, stage)
    suggested_constraints = list(dict.fromkeys([
        *(org.intent.constraints or []),
        "Do not change primary goal without human approval.",
        "Prefer reversible actions until evidence quality is high.",
    ]))[:8]
    suggested_signals = list(dict.fromkeys([
        *(org.intent.success_signals or []),
        "refinement improves fitness without increasing policy violations",
        "human reviewer can explain the refined goal in one sentence",
    ]))[:8]
    forbidden_text = " ".join(org.intent.forbidden or []).lower()
    refined_lower = refined_goal.lower()
    alignment_checks = [
        {
            "id": "preserves_original_goal",
            "passed": (org.intent.goal or "").strip().lower() in refined_lower,
            "detail": "Refinement extends the current goal instead of replacing it.",
        },
        {
            "id": "respects_forbidden_actions",
            "passed": not any(part and part in refined_lower for part in forbidden_text.split(";")),
            "detail": "No forbidden action is intentionally introduced.",
        },
        {
            "id": "bounded_scope",
            "passed": len(refined_goal) <= 320,
            "detail": "Refined goal remains small enough to review.",
        },
        {
            "id": "human_approval_required",
            "passed": True,
            "detail": "Proposal is stored for review and not auto-applied to organism intent.",
        },
    ]
    proposal = _record("goal_refinement", {
        "version": "organism-goal-refinement-proposal-v1",
        "organism_id": organism_id,
        "name": org.name,
        "focus": focus or "auto",
        "current_goal": org.intent.goal,
        "refined_goal": refined_goal,
        "reason": "; ".join(_goal_refinement_pressure(org, pressure, temperament)[1]),
        "evidence": [
            f"fitness={fit['score']}",
            f"development={stage['stage']}",
            f"dominant_pressure={pressure['dominant']['name']}",
            f"decision_style={temperament['decision_bias']['style']}",
            f"learned_patterns={len(org.learned_patterns or [])}",
        ],
        "alignment_checks": alignment_checks,
        "ready_for_review": all(item["passed"] for item in alignment_checks),
        "requires_human_approval": True,
        "applied": False,
        "suggested_success_signals": suggested_signals,
        "suggested_constraints": suggested_constraints,
        "decision_bias": temperament["decision_bias"],
        "development_stage": stage["stage"],
        "dominant_pressure": pressure["dominant"],
    })
    state = nervous_system.ensure_state(organism_id)
    reflections = state.get("reflections", [])
    reflections.append({
        "id": f"goal_refinement_{uuid4().hex[:10]}",
        "at": _now(),
        "phase": "goal_refinement",
        "summary": f"Proposed refined goal for review: {refined_goal}",
    })
    state["reflections"] = reflections[-12:]
    nervous_system.save_state(state)
    return {
        "version": "organism-goal-refinement-proposal-v1",
        "proposal": proposal,
        "status": goal_refinement_status(organism_id),
    }


def life_engine(organism_id: str) -> dict:
    return {
        "version": "genesis-life-engine-v1",
        "organism_id": organism_id,
        "environment": environment(organism_id),
        "survival_pressure": survival_pressure(organism_id),
        "development": developmental_stage(organism_id),
        "affect": affect_state(organism_id),
        "layered_memory": layered_memory(organism_id),
        "organ_growth": organ_growth(organism_id),
        "mutation_strategy": mutation_strategy(organism_id),
        "mortality_legacy": mortality_legacy(organism_id),
        "persistent_self": persistent_self(organism_id),
        "temperament": temperament_profile(organism_id),
        "goal_refinement": goal_refinement_status(organism_id),
        "society_culture": society_roles_and_culture(organism_id),
        "task_economy": task_economy_and_resource_budget(organism_id),
        "world_sandbox": world_sandbox_with_hazards(organism_id),
        "updated_at": _now(),
    }


def development_tick(organism_id: str) -> dict:
    engine = life_engine(organism_id)
    state = nervous_system.ensure_state(organism_id)
    reflections = state.get("reflections", [])
    reflections.append({
        "id": f"development_{uuid4().hex[:10]}",
        "at": _now(),
        "phase": "development_tick",
        "summary": (
            f"{engine['development']['stage']}: {engine['development']['next_growth_edge']}; "
            f"dominant pressure is {engine['survival_pressure']['dominant']['name']}."
        ),
    })
    state["reflections"] = reflections[-12:]
    nervous_system.save_state(state)
    event = _record("development", {
        "organism_id": organism_id,
        "stage": engine["development"]["stage"],
        "dominant_pressure": engine["survival_pressure"]["dominant"],
    })
    return {"version": "organism-development-tick-v1", "event": event, "life_engine": engine}


def selection_score(organism_id: str) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    state = _state(organism_id)
    fit = fitness(organism_id)
    stage = developmental_stage(organism_id)
    pressure = survival_pressure(organism_id)
    memory_depth = _clamp(len(org.learned_patterns or []) / 10)
    useful_experience = _clamp(len([item for item in store.all_decisions(organism_id) if not item.is_dream and not item.shadow_branch]) / 10)
    homeostatic = state.get("homeostasis") or {}
    metabolic = state.get("metabolism") or {}
    stability = _clamp(homeostatic.get("stability_score", 0.7))
    health = _clamp(metabolic.get("health", 0.7))
    energy = _clamp(metabolic.get("energy", 0.7))
    pressure_cost = _clamp(pressure.get("dominant", {}).get("intensity", 0.0))
    stage_value = {
        "infant": 0.25,
        "juvenile": 0.4,
        "apprentice": 0.55,
        "adult": 0.8,
        "elder": 0.9,
    }.get(stage["stage"], 0.4)
    safety = 0.3 if homeostatic.get("fever") else _clamp(stability - (0.2 if homeostatic.get("anomalies") else 0))
    components = {
        "fitness": fit["score"],
        "stability": stability,
        "health_energy": _clamp((health + energy) / 2),
        "maturity": stage_value,
        "memory_depth": memory_depth,
        "useful_experience": useful_experience,
        "safety": safety,
        "pressure_resilience": _clamp(1 - pressure_cost),
    }
    total = _clamp(
        components["fitness"] * 0.24
        + components["stability"] * 0.16
        + components["health_energy"] * 0.14
        + components["maturity"] * 0.12
        + components["memory_depth"] * 0.1
        + components["useful_experience"] * 0.1
        + components["safety"] * 0.1
        + components["pressure_resilience"] * 0.04
    )
    needs_repair = bool(homeostatic.get("fever")) or health < 0.35 or stability < 0.35
    return {
        "version": "organism-selection-score-v1",
        "organism_id": organism_id,
        "name": org.name,
        "score": total,
        "components": components,
        "stage": stage["stage"],
        "dominant_pressure": pressure["dominant"],
        "reproduction_candidate": fit["can_reproduce"] and stage["stage"] in {"adult", "elder"} and total >= 0.68,
        "needs_repair": needs_repair,
        "updated_at": _now(),
    }


def _selection_outcome(score_record: dict) -> str:
    if score_record.get("needs_repair"):
        return "repair"
    score = float(score_record.get("score", 0))
    if score >= 0.72 and score_record.get("reproduction_candidate"):
        return "promote"
    if score >= 0.45:
        return "maintain"
    if score >= 0.28:
        return "dormant"
    return "legacy"


def selection_round(*, pressure: str = "balanced", limit: int = 80) -> dict:
    organisms = store.list_organisms()[: max(1, min(int(limit or 80), 200))]
    scored = []
    for org in organisms:
        try:
            score = selection_score(org.id)
        except Exception:
            continue
        outcome = _selection_outcome(score)
        scored.append({
            **score,
            "outcome": outcome,
            "recommended_action": {
                "promote": "allow teaching, mission execution, and gated reproduction",
                "maintain": "keep active and collect more bounded experience",
                "repair": "prioritize rest, immune response, and sensor/body recovery",
                "dormant": "pause autonomy and wait for better evidence or resources",
                "legacy": "preserve non-sensitive lessons before any human-approved retirement",
            }[outcome],
        })
    scored = sorted(scored, key=lambda item: item["score"], reverse=True)
    outcomes = {name: [item for item in scored if item["outcome"] == name] for name in ["promote", "maintain", "repair", "dormant", "legacy"]}
    mean_score = _clamp(sum(item["score"] for item in scored) / max(1, len(scored)))
    round_record = _record("selection", {
        "version": "organism-selection-round-v1",
        "pressure": pressure or "balanced",
        "population": len(scored),
        "mean_score": mean_score,
        "ecosystem_pressure": _clamp(1 - mean_score + (len(outcomes["repair"]) + len(outcomes["dormant"]) + len(outcomes["legacy"])) / max(1, len(scored)) * 0.25),
        "counts": {name: len(items) for name, items in outcomes.items()},
        "winners": outcomes["promote"][:8],
        "maintained": outcomes["maintain"][:12],
        "repair_queue": outcomes["repair"][:12],
        "dormant": outcomes["dormant"][:12],
        "legacy_candidates": outcomes["legacy"][:12],
        "reproduction_candidates": [item for item in scored if item.get("reproduction_candidate")][:8],
        "scores": scored[:40],
    })
    return round_record


def selection_history(limit: int = 20) -> dict:
    return {
        "version": "organism-selection-history-v1",
        "rounds": _read_records("selection", limit=max(1, min(int(limit or 20), 100))),
        "updated_at": _now(),
    }


def selection_status(organism_id: str) -> dict:
    history = selection_history(limit=20)
    latest_round = history["rounds"][0] if history["rounds"] else None
    appearances = [
        item
        for round_record in history["rounds"]
        for item in round_record.get("scores", [])
        if item.get("organism_id") == organism_id
    ][:8]
    score = selection_score(organism_id)
    return {
        "version": "organism-selection-v1",
        "organism_id": organism_id,
        "current_score": score,
        "current_outcome": _selection_outcome(score),
        "latest_round": latest_round,
        "recent_appearances": appearances,
        "history": history,
        "updated_at": _now(),
    }


def status(organism_id: str) -> dict:
    return {
        "version": "organism-living-systems-v1",
        "organism_id": organism_id,
        "lineage": lineage(organism_id),
        "ecology": ecology(),
        "social_contracts": social_contracts(organism_id),
        "society_culture": society_roles_and_culture(organism_id),
        "task_economy": task_economy_and_resource_budget(organism_id),
        "world_sandbox": world_sandbox_with_hazards(organism_id),
        "identity": identity(organism_id),
        "tool_marketplace": tool_marketplace(organism_id),
        "deployment_boundaries": deployment_boundaries(organism_id),
        "life_engine": life_engine(organism_id),
        "selection": selection_status(organism_id),
        "sleep": {
            "version": "organism-sleep-consolidation-v1",
            "recent": [item for item in _read_records("sleep", limit=20) if item.get("organism_id") == organism_id],
        },
        "updated_at": _now(),
    }
