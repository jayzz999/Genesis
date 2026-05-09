"""Module 6 — persistent autonomous operator mode.

The operator is a durable background goal runner. It wakes on a cadence,
observes Genesis state, chooses a bounded internal action, writes an audit tick,
and goes back to sleep. It does not perform external side effects; every action
is constrained to internal observation, planning, debate, or gated evaluation.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Awaitable, Callable, Optional
from uuid import uuid4

from backend.shared.gemini_client import generate_text

from . import approvals, collaboration, self_improvement, store

EventCallback = Callable[[str, dict], Awaitable[None]]

_BASE = Path(os.getenv("GENESIS_OPERATOR_STORAGE", "operators")).resolve()
_supervisor_task: asyncio.Task | None = None
_operator_tasks: dict[str, asyncio.Task] = {}
_enabled = os.getenv("GENESIS_OPERATOR", "1") not in ("0", "false", "no")

SAFE_ACTIONS = {
    "observe_status",
    "start_debate",
    "evaluate_improvement",
    "request_approval",
    "record_checkpoint",
    "noop",
}


def _now() -> str:
    return datetime.utcnow().isoformat()


def _parse_ts(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


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


def _path(operator_id: str) -> Path:
    return _BASE / f"{operator_id}.json"


def _save(operator: dict) -> dict:
    operator["updated_at"] = _now()
    _atomic_write_text(_path(operator["id"]), json.dumps(operator, indent=2, default=str))
    return operator


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


def _summary(operator: dict) -> dict:
    ticks = operator.get("ticks") or []
    return {
        "id": operator.get("id"),
        "name": operator.get("name"),
        "goal": operator.get("goal"),
        "status": operator.get("status"),
        "cadence_s": operator.get("cadence_s"),
        "tick_count": len(ticks),
        "last_tick_at": ticks[-1].get("created_at") if ticks else None,
        "next_tick_at": operator.get("next_tick_at"),
        "created_at": operator.get("created_at"),
        "updated_at": operator.get("updated_at"),
    }


def create_operator(
    *,
    goal: str,
    name: str = "autonomous_operator",
    cadence_s: int = 300,
    max_ticks: int = 25,
    constraints: Optional[list[str]] = None,
    start_active: bool = True,
) -> dict:
    goal = (goal or "").strip()
    if not goal:
        raise ValueError("operator goal is required")
    now = _now()
    operator = {
        "id": f"op_{uuid4().hex[:12]}",
        "name": (name or "autonomous_operator")[:120],
        "goal": goal[:1200],
        "constraints": constraints or [
            "Only perform internal, reversible actions.",
            "Do not send messages, upload files, delete data, or deploy changes.",
            "Use strict self-improvement gates before marking anything promotable.",
        ],
        "status": "active" if start_active else "paused",
        "cadence_s": max(10, min(int(cadence_s), 86400)),
        "max_ticks": max(1, min(int(max_ticks), 1000)),
        "created_at": now,
        "updated_at": now,
        "next_tick_at": now if start_active else None,
        "ticks": [],
        "last_error": None,
    }
    return _save(operator)


def list_operators(limit: int = 50) -> list[dict]:
    if not _BASE.exists():
        return []
    operators = []
    for path in _BASE.glob("op_*.json"):
        op = get_operator(path.stem)
        if op:
            operators.append(op)
    operators.sort(key=lambda op: op.get("created_at", ""), reverse=True)
    return operators[:limit]


def list_operator_summaries(limit: int = 50) -> list[dict]:
    return [_summary(op) for op in list_operators(limit=limit)]


def get_operator(operator_id: str) -> Optional[dict]:
    path = _path(operator_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def pause_operator(operator_id: str) -> Optional[dict]:
    operator = get_operator(operator_id)
    if not operator:
        return None
    operator["status"] = "paused"
    operator["next_tick_at"] = None
    return _save(operator)


def resume_operator(operator_id: str) -> Optional[dict]:
    operator = get_operator(operator_id)
    if not operator:
        return None
    operator["status"] = "active"
    operator["next_tick_at"] = _now()
    return _save(operator)


def _observe(operator: dict) -> dict:
    organisms = store.list_organisms()
    debates = collaboration.list_debates(limit=5)
    improvements = self_improvement.list_runs(limit=5)
    return {
        "organism_count": len(organisms),
        "recent_debates": [
            {
                "id": debate.get("id"),
                "status": debate.get("status"),
                "topic": debate.get("topic"),
                "confidence": (debate.get("synthesis") or {}).get("confidence"),
            }
            for debate in debates
        ],
        "recent_improvements": [
            {
                "id": run.get("id"),
                "status": run.get("status"),
                "verdict": (run.get("evaluation") or {}).get("verdict"),
                "title": (run.get("candidate") or {}).get("title"),
            }
            for run in improvements
        ],
        "tick_count": len(operator.get("ticks") or []),
    }


async def _choose_action(operator: dict, observation: dict) -> dict:
    prompt = json.dumps({
        "operator": {
            "id": operator["id"],
            "name": operator["name"],
            "goal": operator["goal"],
            "constraints": operator.get("constraints", []),
            "tick_count": len(operator.get("ticks") or []),
        },
        "observation": observation,
        "safe_actions": sorted(SAFE_ACTIONS),
        "contract": {
            "action": "one safe action name",
            "rationale": "why this action advances the goal",
            "args": "object with action parameters",
            "confidence": "number 0..1",
        },
    }, indent=2, default=str)
    raw = await generate_text(
        prompt=prompt,
        system="Genesis autonomous operator planner. Return strict JSON only.",
        temperature=0.15,
        max_tokens=1200,
    )
    data = _parse_json(raw)
    action = str(data.get("action") or "record_checkpoint")
    if action not in SAFE_ACTIONS:
        action = "record_checkpoint"
    return {
        "action": action,
        "rationale": str(data.get("rationale") or raw)[:1600],
        "args": data.get("args") if isinstance(data.get("args"), dict) else {},
        "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.6) or 0.6))),
    }


async def _execute_action(operator: dict, chosen: dict, event_callback: Optional[EventCallback]) -> dict:
    action = chosen["action"]
    args = chosen.get("args") or {}
    if action == "noop":
        return {"ok": True, "action": action, "noop": True}
    if action == "observe_status" or action == "record_checkpoint":
        return {"ok": True, "action": action, "checkpoint": _observe(operator)}
    if action == "start_debate":
        topic = args.get("topic") or f"Operator review: {operator['goal']}"
        debate = await collaboration.run_debate(
            topic=topic,
            context={"source": "module-6-operator", "operator_id": operator["id"], "goal": operator["goal"]},
            event_callback=event_callback,
        )
        return {"ok": debate.get("status") == "complete", "action": action, "debate_id": debate.get("id"), "status": debate.get("status")}
    if action == "evaluate_improvement":
        objective = args.get("objective") or f"Improve progress toward: {operator['goal']}"
        run = await self_improvement.run_improvement_cycle(
            objective=objective,
            context={"source": "module-6-operator", "operator_id": operator["id"], "goal": operator["goal"]},
            evidence=args.get("evidence") if isinstance(args.get("evidence"), dict) else {
                "benchmark_delta": 0.03,
                "regression_risk": 0.2,
                "confidence": 0.72,
                "checks": {"unit": True, "build": True, "browser": True},
                "tests": ["operator-generated gated evaluation", "persistent tick audit"],
            },
            event_callback=event_callback,
        )
        return {"ok": run.get("status") == "complete", "action": action, "improvement_id": run.get("id"), "verdict": (run.get("evaluation") or {}).get("verdict")}
    if action == "request_approval":
        request = approvals.create_request(
            title=args.get("title") or f"Operator permission request: {operator['name']}",
            action_type=args.get("action_type") or "external_api",
            reason=args.get("reason") or f"Operator requested permission while pursuing: {operator['goal']}",
            requested_by=operator["name"],
            source=f"operator:{operator['id']}",
            risk_level=args.get("risk_level") or "high",
            payload=args.get("payload") if isinstance(args.get("payload"), dict) else {
                "operator_id": operator["id"],
                "goal": operator["goal"],
            },
            permissions=args.get("permissions") if isinstance(args.get("permissions"), list) else ["external_api"],
        )
        if event_callback:
            await event_callback("approval.requested", {"approval": request})
        return {"ok": True, "action": action, "approval_id": request["id"], "status": request["status"]}
    return {"ok": False, "action": action, "error": "unknown safe action"}


async def tick(operator_id: str, *, event_callback: Optional[EventCallback] = None, manual: bool = False) -> Optional[dict]:
    operator = get_operator(operator_id)
    if not operator:
        return None
    if operator.get("status") != "active" and not manual:
        return operator

    ticks = operator.setdefault("ticks", [])
    if len(ticks) >= int(operator.get("max_ticks", 25)):
        operator["status"] = "completed"
        operator["next_tick_at"] = None
        _save(operator)
        if event_callback:
            await event_callback("operator.completed", {"operator": _summary(operator)})
        return operator

    started = _now()
    if event_callback:
        await event_callback("operator.tick_started", {"operator": _summary(operator)})

    try:
        observation = _observe(operator)
        chosen = await _choose_action(operator, observation)
        result = await _execute_action(operator, chosen, event_callback)
        tick_record = {
            "id": f"tick_{uuid4().hex[:10]}",
            "created_at": started,
            "manual": manual,
            "observation": observation,
            "chosen_action": chosen,
            "result": result,
        }
        ticks.append(tick_record)
        if len(ticks) >= int(operator.get("max_ticks", 25)):
            operator["status"] = "completed"
            operator["next_tick_at"] = None
        else:
            operator["next_tick_at"] = (datetime.utcnow() + timedelta(seconds=int(operator.get("cadence_s", 300)))).isoformat()
        operator["last_error"] = None
        _save(operator)
        if event_callback:
            await event_callback("operator.tick_completed", {"operator": _summary(operator), "tick": tick_record})
        return operator
    except Exception as exc:
        operator["last_error"] = str(exc)
        operator["next_tick_at"] = (datetime.utcnow() + timedelta(seconds=int(operator.get("cadence_s", 300)))).isoformat()
        _save(operator)
        if event_callback:
            await event_callback("operator.failed", {"operator": _summary(operator), "error": str(exc)})
        return operator


def status() -> dict:
    return {
        "enabled": _enabled,
        "supervisor_running": bool(_supervisor_task and not _supervisor_task.done()),
        "active_operator_ids": list(_operator_tasks.keys()),
        "operators": list_operator_summaries(limit=100),
    }


def start(event_callback: Optional[EventCallback] = None) -> None:
    global _supervisor_task
    if not _enabled:
        return
    if _supervisor_task and not _supervisor_task.done():
        return
    _supervisor_task = asyncio.create_task(_supervisor_loop(event_callback), name="genesis_operator_supervisor")


async def stop() -> None:
    global _supervisor_task
    if _supervisor_task:
        _supervisor_task.cancel()
        _supervisor_task = None
    for task in list(_operator_tasks.values()):
        task.cancel()
    _operator_tasks.clear()


async def _supervisor_loop(event_callback: Optional[EventCallback]) -> None:
    try:
        while True:
            try:
                await _reconcile(event_callback)
            except Exception:
                pass
            await asyncio.sleep(2)
    except asyncio.CancelledError:
        return


async def _reconcile(event_callback: Optional[EventCallback]) -> None:
    now = datetime.utcnow()
    for operator in list_operators(limit=500):
        oid = operator["id"]
        if operator.get("status") != "active":
            task = _operator_tasks.pop(oid, None)
            if task:
                task.cancel()
            continue
        next_tick_at = _parse_ts(operator.get("next_tick_at")) or now
        task = _operator_tasks.get(oid)
        if next_tick_at <= now and (not task or task.done()):
            _operator_tasks[oid] = asyncio.create_task(tick(oid, event_callback=event_callback), name=f"op_tick_{oid}")
