"""Autonomous metabolism for Genesis organisms.

Metabolism gives autonomy resource pressure: energy is spent, attention is
limited, fatigue accumulates, rest recovers, and survival policy gates action.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _now() -> str:
    return datetime.utcnow().isoformat()


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, round(float(value), 3)))


ACTION_COSTS = {
    "dream": {"energy": 0.06, "attention": 0.04, "fatigue": 0.03},
    "observe_and_perceive": {"energy": 0.09, "attention": 0.08, "fatigue": 0.05},
    "reflect": {"energy": 0.04, "attention": 0.05, "fatigue": 0.02},
    "request_sensor": {"energy": 0.02, "attention": 0.02, "fatigue": 0.01},
    "research_or_ask": {"energy": 0.08, "attention": 0.12, "fatigue": 0.05},
    "diagnose": {"energy": 0.07, "attention": 0.1, "fatigue": 0.05},
    "noop": {"energy": 0.01, "attention": 0.01, "fatigue": 0.0},
}


def default_state() -> dict:
    return {
        "version": "organism-metabolism-v1",
        "energy": 0.78,
        "attention": 0.72,
        "fatigue": 0.12,
        "health": 0.86,
        "hunger": 0.28,
        "recovery_rate": 0.08,
        "survival_status": "stable",
        "policy": "act",
        "last_policy_reason": "Metabolism initialized.",
        "last_action_cost": {},
        "updated_at": _now(),
    }


def ensure(state: dict) -> dict:
    metabolism = state.get("metabolism") or default_state()
    for key, value in default_state().items():
        metabolism.setdefault(key, value)
    state["metabolism"] = metabolism
    return metabolism


def evaluate(state: dict, vitals: dict | None = None, body_map: dict | None = None) -> dict:
    metabolism = ensure(state)
    vitals = vitals or state.get("vitals") or {}
    body_map = body_map or state.get("body") or {}

    sensor_count = int(vitals.get("sensor_count", 0) or body_map.get("summary", {}).get("sensors", 0) or 0)
    failure_count = int(vitals.get("failure_count", 0) or 0)
    cycle_count = len(state.get("autonomy_cycles", []))

    hunger = metabolism.get("hunger", 0.28)
    fatigue = metabolism.get("fatigue", 0.12)
    health = metabolism.get("health", 0.86)
    energy = metabolism.get("energy", state.get("energy", 0.7))
    attention = metabolism.get("attention", state.get("attention", 0.7))

    if sensor_count == 0:
        hunger = _clamp(hunger + 0.06)
        health = _clamp(health - 0.025)
    else:
        hunger = _clamp(hunger - 0.035)
        health = _clamp(health + 0.015)

    if failure_count:
        fatigue = _clamp(fatigue + 0.04)
        health = _clamp(health - 0.04)

    if cycle_count >= 8:
        fatigue = _clamp(fatigue + 0.01)

    policy = "act"
    reason = "Energy and attention are sufficient for bounded autonomous action."
    survival_status = "stable"
    if health < 0.35:
        policy = "repair"
        survival_status = "fragile"
        reason = "Health is low; prioritize repair before normal autonomy."
    elif energy < 0.24 or attention < 0.2 or fatigue > 0.82:
        policy = "rest"
        survival_status = "depleted"
        reason = "Energy or attention is too low, or fatigue is too high."
    elif hunger > 0.75:
        policy = "seek_sensor"
        survival_status = "hungry"
        reason = "Input hunger is high; organism needs a useful sensor before more work."
    elif fatigue > 0.62:
        policy = "conserve"
        survival_status = "tired"
        reason = "Fatigue is rising; only low-cost internal action should run."

    metabolism.update({
        "energy": _clamp(energy),
        "attention": _clamp(attention),
        "fatigue": _clamp(fatigue),
        "health": _clamp(health),
        "hunger": _clamp(hunger),
        "policy": policy,
        "survival_status": survival_status,
        "last_policy_reason": reason,
        "updated_at": _now(),
    })
    state["energy"] = metabolism["energy"]
    state["attention"] = metabolism["attention"]
    return metabolism


def can_execute(state: dict, action: str) -> tuple[bool, dict]:
    metabolism = evaluate(state)
    policy = metabolism.get("policy")
    cost = ACTION_COSTS.get(action, ACTION_COSTS["noop"])
    if policy == "rest":
        return False, {"reason": metabolism["last_policy_reason"], "policy": policy, "cost": cost}
    if policy == "repair" and action not in {"diagnose", "reflect"}:
        return False, {"reason": metabolism["last_policy_reason"], "policy": policy, "cost": cost}
    if policy == "seek_sensor" and action not in {"request_sensor", "reflect", "observe_and_perceive"}:
        return False, {"reason": metabolism["last_policy_reason"], "policy": policy, "cost": cost}
    if policy == "conserve" and cost["energy"] > 0.06:
        return False, {"reason": metabolism["last_policy_reason"], "policy": policy, "cost": cost}
    return True, {"reason": "Metabolism permits action.", "policy": policy, "cost": cost}


def spend(state: dict, action: str, *, ok: bool = True) -> dict:
    metabolism = ensure(state)
    cost = ACTION_COSTS.get(action, ACTION_COSTS["noop"])
    metabolism["energy"] = _clamp(metabolism.get("energy", 0.7) - cost["energy"])
    metabolism["attention"] = _clamp(metabolism.get("attention", 0.7) - cost["attention"])
    metabolism["fatigue"] = _clamp(metabolism.get("fatigue", 0.1) + cost["fatigue"] + (0.04 if not ok else 0.0))
    metabolism["health"] = _clamp(metabolism.get("health", 0.8) - (0.035 if not ok else 0.0))
    metabolism["last_action_cost"] = cost
    return evaluate(state)


def recover(state: dict, *, depth: str = "rest") -> dict:
    metabolism = ensure(state)
    factor = 1.0 if depth == "rest" else 0.5
    metabolism["energy"] = _clamp(metabolism.get("energy", 0.7) + metabolism.get("recovery_rate", 0.08) * factor)
    metabolism["attention"] = _clamp(metabolism.get("attention", 0.7) + 0.06 * factor)
    metabolism["fatigue"] = _clamp(metabolism.get("fatigue", 0.1) - 0.1 * factor)
    metabolism["health"] = _clamp(metabolism.get("health", 0.8) + 0.025 * factor)
    metabolism["last_action_cost"] = {"recovery": depth}
    return evaluate(state)


def rest_cycle(state: dict, reason: str) -> dict:
    metabolism = recover(state, depth="rest")
    return {
        "ok": True,
        "rested": True,
        "metabolism": metabolism,
        "summary": f"Autonomy paused for metabolic recovery: {reason}",
    }

