"""Homeostasis and immune responses for Genesis organisms.

Homeostasis watches the organism's body, metabolism, and autonomy history. It
turns instability into concrete protective responses before autonomy continues.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4


def _now() -> str:
    return datetime.utcnow().isoformat()


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, round(float(value), 3)))


def default_state() -> dict:
    return {
        "version": "organism-homeostasis-v1",
        "stability_score": 0.86,
        "immune_status": "stable",
        "fever": False,
        "anomalies": [],
        "recommended_responses": [],
        "quarantined_sensors": [],
        "blocked_actuators": [],
        "immune_audit": [],
        "last_reason": "Homeostasis initialized.",
        "updated_at": _now(),
    }


def ensure(state: dict) -> dict:
    homeostasis = state.get("homeostasis") or default_state()
    for key, value in default_state().items():
        homeostasis.setdefault(key, value)
    state["homeostasis"] = homeostasis
    return homeostasis


def _anomaly(kind: str, severity: float, response: str, reason: str, payload: dict | None = None) -> dict:
    return {
        "id": f"anom_{uuid4().hex[:10]}",
        "kind": kind,
        "severity": _clamp(severity),
        "response": response,
        "reason": reason,
        "payload": payload or {},
        "detected_at": _now(),
    }


def _recent_failures(cycles: list[dict]) -> int:
    recent = cycles[-6:]
    return sum(
        1
        for cycle in recent
        if cycle.get("status") in {"blocked", "rested", "immune_response"}
        or cycle.get("result", {}).get("ok") is False
        or cycle.get("result", {}).get("blocked") is True
    )


def _runaway_action(cycles: list[dict]) -> str | None:
    recent_actions = [cycle.get("action") for cycle in cycles[-5:] if cycle.get("action") and cycle.get("action") != "none"]
    if len(recent_actions) >= 4 and len(set(recent_actions[-4:])) == 1:
        return recent_actions[-1]
    return None


def evaluate(state: dict, *, body_map: dict | None = None, vitals: dict | None = None) -> dict:
    homeostasis = ensure(state)
    metabolism = state.get("metabolism") or {}
    body_map = body_map or state.get("body") or {}
    vitals = vitals or state.get("vitals") or {}
    cycles = state.get("autonomy_cycles") or []
    intentions = state.get("intentions") or []
    summary = body_map.get("summary") or {}
    sensors = body_map.get("sensors") or []

    anomalies: list[dict] = []
    sensor_count = int(summary.get("sensors", vitals.get("sensor_count", 0)) or 0)
    alive_sensors = int(summary.get("alive_sensors", 0) or 0)
    if sensor_count == 0:
        anomalies.append(_anomaly(
            "sensor_silence",
            0.66,
            "request_sensor",
            "The organism has no active perception source, so autonomy is operating without fresh inputs.",
        ))
    elif alive_sensors == 0:
        anomalies.append(_anomaly(
            "sensor_failure",
            0.78,
            "quarantine_sensor",
            "Sensors exist but none are alive, ready, or armed.",
            {"sensor_count": sensor_count},
        ))

    misconfigured = [sensor for sensor in sensors if sensor.get("status") not in {"alive", "ready", "armed"}]
    if misconfigured:
        anomalies.append(_anomaly(
            "misconfigured_sensor",
            0.52,
            "quarantine_sensor",
            "One or more sensors are present but not healthy enough for autonomous trust.",
            {"sensor_ids": [sensor.get("id") for sensor in misconfigured]},
        ))

    energy = float(metabolism.get("energy", state.get("energy", 0.7)) or 0)
    attention = float(metabolism.get("attention", state.get("attention", 0.7)) or 0)
    fatigue = float(metabolism.get("fatigue", 0.0) or 0)
    health = float(metabolism.get("health", 0.86) or 0)
    stress = float(state.get("stress", 0.0) or 0)
    if energy < 0.22:
        anomalies.append(_anomaly("energy_low", 0.74, "rest", "Energy is below the safe autonomy threshold."))
    if attention < 0.2:
        anomalies.append(_anomaly("attention_low", 0.68, "rest", "Attention is too low for reliable action selection."))
    if fatigue > 0.76:
        anomalies.append(_anomaly("fatigue_high", 0.72, "rest", "Fatigue is high enough to raise execution risk."))
    if health < 0.45:
        anomalies.append(_anomaly("health_low", 0.84, "repair", "Organism health is low; repair should outrank normal work."))
    if stress > 0.72:
        anomalies.append(_anomaly("stress_high", 0.56, "conserve", "Stress is high; autonomy should narrow its action surface."))

    failure_count = _recent_failures(cycles)
    if failure_count >= 3:
        anomalies.append(_anomaly(
            "repeated_failures",
            0.82,
            "block_actuator",
            "Recent autonomy cycles show repeated blocked or failed outcomes.",
            {"recent_failure_count": failure_count},
        ))

    repeated_action = _runaway_action(cycles)
    if repeated_action:
        anomalies.append(_anomaly(
            "runaway_cycle",
            0.8,
            "block_actuator",
            "The same action is repeating without enough variation.",
            {"action": repeated_action},
        ))

    approval_backlog = [item for item in intentions if item.get("status") == "queued" and item.get("approval_required")]
    if len(approval_backlog) >= 4:
        anomalies.append(_anomaly(
            "approval_backlog",
            0.46,
            "prune_intentions",
            "Approval-gated intentions are accumulating faster than they can be resolved.",
            {"queued_approval_required": len(approval_backlog)},
        ))

    severity_load = sum(item["severity"] for item in anomalies)
    stability_score = _clamp(1.0 - min(0.86, severity_load * 0.18))
    fever = stability_score < 0.55 or any(item["severity"] >= 0.8 for item in anomalies)
    immune_status = "fever" if fever else "watching" if anomalies else "stable"
    responses = []
    for item in anomalies:
        if item["response"] not in responses:
            responses.append(item["response"])

    homeostasis.update({
        "version": "organism-homeostasis-v1",
        "stability_score": stability_score,
        "immune_status": immune_status,
        "fever": fever,
        "anomalies": anomalies,
        "recommended_responses": responses,
        "last_reason": "Anomalies detected." if anomalies else "All monitored signals are inside homeostatic range.",
        "updated_at": _now(),
    })
    return homeostasis


def gate_action(state: dict, action: str) -> tuple[bool, dict]:
    homeostasis = evaluate(state)
    blocked_actuators = set(homeostasis.get("blocked_actuators") or [])
    if action in blocked_actuators:
        return False, {
            "reason": f"Immune system blocked actuator {action!r}.",
            "immune_status": homeostasis.get("immune_status"),
            "stability_score": homeostasis.get("stability_score"),
        }
    if homeostasis.get("fever") and action not in {"reflect", "diagnose", "dream"}:
        return False, {
            "reason": "Homeostatic fever is active; only internal repair, reflection, or simulation may run.",
            "immune_status": homeostasis.get("immune_status"),
            "stability_score": homeostasis.get("stability_score"),
        }
    return True, {
        "reason": "Homeostasis permits action.",
        "immune_status": homeostasis.get("immune_status"),
        "stability_score": homeostasis.get("stability_score"),
    }


def run_immune_response(state: dict, *, action: str = "auto") -> dict:
    homeostasis = evaluate(state)
    responses = homeostasis.get("recommended_responses") or []
    selected = responses[0] if action == "auto" and responses else action
    result: dict[str, Any] = {"ok": True, "selected_response": selected}

    if selected in {"rest", "repair", "conserve"}:
        from . import metabolism

        depth = "rest" if selected in {"rest", "repair"} else "idle"
        result["metabolism"] = metabolism.recover(state, depth=depth)
        result["summary"] = f"Immune response applied metabolic {depth}."
    elif selected == "quarantine_sensor":
        sensors = (state.get("body") or {}).get("sensors") or []
        quarantined = {
            sensor.get("id")
            for sensor in sensors
            if sensor.get("status") not in {"alive", "ready", "armed"}
        }
        homeostasis["quarantined_sensors"] = sorted(
            set(homeostasis.get("quarantined_sensors") or []) | quarantined
        )
        result["quarantined_sensors"] = homeostasis["quarantined_sensors"]
        result["summary"] = "Immune response quarantined unhealthy sensors."
    elif selected == "block_actuator":
        repeated = next(
            (item.get("payload", {}).get("action") for item in homeostasis.get("anomalies", []) if item.get("kind") == "runaway_cycle"),
            None,
        )
        actuator = repeated or "research_or_ask"
        homeostasis["blocked_actuators"] = sorted(set(homeostasis.get("blocked_actuators") or []) | {actuator})
        result["blocked_actuators"] = homeostasis["blocked_actuators"]
        result["summary"] = f"Immune response blocked actuator {actuator!r}."
    elif selected == "prune_intentions":
        seen = set()
        kept = []
        pruned = []
        for intention in state.get("intentions", []):
            key = (intention.get("need_id"), intention.get("action"), intention.get("approval_required"))
            if intention.get("status") == "queued" and key in seen:
                intention["status"] = "pruned"
                intention["completed_at"] = _now()
                pruned.append(intention)
            else:
                kept.append(intention)
                if intention.get("status") == "queued":
                    seen.add(key)
        state["intentions"] = kept + pruned[-3:]
        result["pruned_intentions"] = len(pruned)
        result["summary"] = "Immune response pruned duplicate queued intentions."
    elif selected == "request_sensor":
        result["summary"] = "Immune response recommends attaching a safe heartbeat sensor."
    else:
        result["ok"] = False
        result["summary"] = "No immune response was needed."

    audit = {
        "id": f"immune_{uuid4().hex[:12]}",
        "version": "immune-response-v1",
        "action": selected,
        "result": result,
        "anomaly_kinds": [item.get("kind") for item in homeostasis.get("anomalies", [])],
        "created_at": _now(),
    }
    audit_log = homeostasis.get("immune_audit") or []
    audit_log.append(audit)
    homeostasis["immune_audit"] = audit_log[-30:]
    state["homeostasis"] = homeostasis
    return {"response": audit, "homeostasis": evaluate(state)}
