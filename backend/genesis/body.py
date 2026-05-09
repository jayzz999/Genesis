"""Autonomous body and sensors for Genesis organisms.

The nervous system decides what the organism needs. The body defines what the
organism can sense and safely do. It is the contract between inner intention
and embodied action.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from . import store


def _now() -> str:
    return datetime.utcnow().isoformat()


def sensor_registry() -> list[dict]:
    return [
        {
            "kind": "interval",
            "name": "Interval sensor",
            "description": "A local heartbeat perception emitted on a cadence.",
            "risk": "local",
            "approval_required": False,
        },
        {
            "kind": "webhook",
            "name": "Webhook sensor",
            "description": "Receives events from an external system through a generated local endpoint.",
            "risk": "inbound",
            "approval_required": False,
        },
        {
            "kind": "http_poll",
            "name": "API health sensor",
            "description": "Polls an HTTP endpoint and converts the response into perception.",
            "risk": "network",
            "approval_required": True,
        },
        {
            "kind": "project_file",
            "name": "Project file sensor",
            "description": "Watches an allowed local project artifact for changes.",
            "risk": "local_artifact",
            "approval_required": True,
        },
    ]


def actuator_registry() -> list[dict]:
    return [
        {
            "action": "dream",
            "name": "Dream simulation",
            "description": "Run an internal imagined perception without real-world side effects.",
            "risk": "internal",
            "approval_required": False,
        },
        {
            "action": "observe_and_perceive",
            "name": "Self-check perception",
            "description": "Feed a bounded self-check perception into the organism runtime.",
            "risk": "internal",
            "approval_required": False,
        },
        {
            "action": "reflect",
            "name": "Reflect and remember",
            "description": "Write a safe memory/world-model reflection from current needs.",
            "risk": "internal",
            "approval_required": False,
        },
        {
            "action": "request_sensor",
            "name": "Request sensor",
            "description": "Ask for or attach a new perception source.",
            "risk": "body_change",
            "approval_required": True,
        },
        {
            "action": "research_or_ask",
            "name": "Research or ask",
            "description": "Seek missing context through approved external or human channels.",
            "risk": "external",
            "approval_required": True,
        },
        {
            "action": "diagnose",
            "name": "Diagnose failure",
            "description": "Investigate a failed real action before further autonomy.",
            "risk": "review",
            "approval_required": True,
        },
    ]


def _sensor_status(source: dict) -> str:
    kind = source.get("kind")
    if kind == "interval":
        interval_s = int(source.get("interval_s", 0) or 0)
        return "alive" if interval_s >= 5 else "misconfigured"
    if kind == "webhook":
        return "ready" if source.get("token") else "awaiting_token"
    if kind == "http_poll":
        return "armed" if source.get("url") else "misconfigured"
    if kind == "project_file":
        return "armed" if source.get("path") else "misconfigured"
    return "unknown"


def _sensor_view(index: int, source: dict) -> dict:
    kind = source.get("kind", "unknown")
    registry = {item["kind"]: item for item in sensor_registry()}
    spec = registry.get(kind, {"name": kind, "risk": "unknown", "approval_required": True})
    return {
        "id": f"sensor_{index}_{kind}",
        "index": index,
        "kind": kind,
        "name": spec.get("name", kind),
        "status": _sensor_status(source),
        "risk": spec.get("risk", "unknown"),
        "approval_required": bool(spec.get("approval_required")),
        "config": source,
    }


def recommend_sensors(organism_id: str, nervous_state: dict | None = None) -> list[dict]:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    sources = org.perception_sources or []
    need_ids = {need.get("id") for need in (nervous_state or {}).get("needs", [])}
    recommendations: list[dict] = []
    if not sources or "attach_sensor" in need_ids:
        recommendations.append({
            "id": "rec_interval_heartbeat",
            "kind": "interval",
            "name": "Local heartbeat sensor",
            "reason": "Gives the organism a recurring safe perception so it can live without manual pokes.",
            "source": {
                "kind": "interval",
                "type": "autonomous_heartbeat",
                "interval_s": 60,
                "payload": {"source": "recommended_body_sensor"},
            },
            "approval_required": False,
        })
    if any(need.get("id") == "resolve_knowledge_gaps" for need in (nervous_state or {}).get("needs", [])):
        recommendations.append({
            "id": "rec_context_webhook",
            "kind": "webhook",
            "name": "Context webhook",
            "reason": "Allows approved external systems to send context into the organism.",
            "source": {"kind": "webhook", "type": "context_event"},
            "approval_required": False,
        })
    return recommendations


def attach_recommended_sensor(organism_id: str, recommendation_id: str = "rec_interval_heartbeat") -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    recommendations = recommend_sensors(organism_id)
    rec = next((item for item in recommendations if item["id"] == recommendation_id), None)
    if not rec:
        raise ValueError(f"recommendation {recommendation_id} not available")
    if rec.get("approval_required"):
        raise PermissionError("recommendation requires approval")
    source = dict(rec["source"])
    org.perception_sources.append(source)
    store.save_organism(org)
    return {
        "version": "organism-body-v1",
        "organism_id": organism_id,
        "attached_sensor": _sensor_view(len(org.perception_sources) - 1, source),
        "created_at": _now(),
    }


def build_body_map(organism_id: str, nervous_state: dict | None = None) -> dict:
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    sensors = [_sensor_view(i, src) for i, src in enumerate(org.perception_sources or [])]
    actuators = actuator_registry()
    safe_actuators = [item for item in actuators if not item.get("approval_required")]
    return {
        "version": "organism-body-v1",
        "organism_id": organism_id,
        "organism_name": org.name,
        "sensors": sensors,
        "actuators": actuators,
        "recommendations": recommend_sensors(organism_id, nervous_state=nervous_state),
        "summary": {
            "sensors": len(sensors),
            "alive_sensors": sum(1 for sensor in sensors if sensor["status"] in {"alive", "ready", "armed"}),
            "actuators": len(actuators),
            "safe_actuators": len(safe_actuators),
            "approval_gated_actuators": len(actuators) - len(safe_actuators),
        },
        "updated_at": _now(),
    }


async def execute_intention(organism_id: str, intention: dict, *, event_callback=None) -> dict:
    action = intention.get("action")
    org = store.load_organism(organism_id)
    if not org:
        raise ValueError(f"organism {organism_id} not found")
    actuators = {item["action"]: item for item in actuator_registry()}
    actuator = actuators.get(action)
    if not actuator:
        return {
            "ok": True,
            "executed": "noop",
            "body_version": "organism-body-v1",
            "summary": f"No body actuator is registered for action {action!r}.",
        }
    if actuator.get("approval_required") or intention.get("approval_required"):
        return {
            "ok": False,
            "blocked": True,
            "body_version": "organism-body-v1",
            "actuator": actuator,
            "reason": "body actuator requires approval before autonomous execution",
        }

    if action == "dream":
        from . import dreams

        imagined = await dreams.imagine(organism_id, n=1, event_callback=event_callback)
        return {
            "ok": True,
            "executed": "dream",
            "body_version": "organism-body-v1",
            "actuator": actuator,
            "imagined_count": len(imagined),
            "summary": "Body ran one safe internal dream simulation.",
        }

    if action == "observe_and_perceive":
        from . import runtime

        decision = await runtime.perceive(
            organism_id,
            {
                "type": "autonomous_self_check",
                "payload": {
                    "goal": org.intent.goal,
                    "need_id": intention.get("need_id"),
                    "body_map": "organism-body-v1",
                    "source": "embodied_autonomy_loop",
                },
            },
            event_callback=event_callback,
        )
        return {
            "ok": True,
            "executed": "observe_and_perceive",
            "body_version": "organism-body-v1",
            "actuator": actuator,
            "decision_id": decision.id,
            "summary": "Body fed a bounded self-check perception into the organism runtime.",
        }

    if action == "reflect":
        from . import memory, world_model

        text = (
            f"Organism {org.name} reflected through its body map on need "
            f"{intention.get('need_id')}: {intention.get('reason')}"
        )
        memory_item = memory.remember(
            text,
            kind="body_reflection",
            scope="organism",
            tags=["body", "autonomy", intention.get("drive", "unknown")],
            organism_id=organism_id,
            score=0.68,
        )
        evidence = world_model.attach_evidence(
            source=organism_id,
            kind="body_autonomy_cycle",
            summary=text,
            payload={"intention": intention, "actuator": actuator},
        )
        return {
            "ok": True,
            "executed": "reflect",
            "body_version": "organism-body-v1",
            "actuator": actuator,
            "memory_id": memory_item.id if memory_item else None,
            "evidence_id": evidence["id"],
            "summary": "Body recorded a reflection into memory and the world model.",
        }

    return {
        "ok": True,
        "executed": "noop",
        "body_version": "organism-body-v1",
        "actuator": actuator,
        "summary": f"Body has no implementation for action {action!r}.",
    }


def fleet_status() -> dict:
    maps = []
    for org in store.list_organisms():
        maps.append(build_body_map(org.id))
    return {
        "version": "organism-body-v1",
        "organisms": maps,
        "summary": {
            "organisms": len(maps),
            "sensors": sum(item["summary"]["sensors"] for item in maps),
            "alive_sensors": sum(item["summary"]["alive_sensors"] for item in maps),
            "safe_actuators": sum(item["summary"]["safe_actuators"] for item in maps),
        },
    }

