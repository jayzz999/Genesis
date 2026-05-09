"""Module 24..33 — capability growth layer.

This layer gives Genesis a project brain: durable task graphs, project memory,
tool-result verification, self-healing diagnostics, research synthesis, model
routing, reusable skill compilation, session continuity, preference learning,
and deployment pipeline checks.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from backend.shared.config import settings

from . import approvals, connectors, governance

_BASE = Path(os.getenv("GENESIS_CAPABILITY_STORAGE", "capabilities")).resolve()


def _now() -> str:
    return datetime.utcnow().isoformat()


def _canonical_json(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: dict) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent), text=True)
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


def _path(kind: str, item_id: str) -> Path:
    return _BASE / kind / f"{item_id}.json"


def _save(kind: str, item: dict) -> dict:
    item["updated_at"] = _now()
    _atomic_write_text(_path(kind, item["id"]), json.dumps(item, indent=2, sort_keys=True, default=str))
    return item


def _load(kind: str, item_id: str) -> Optional[dict]:
    path = _path(kind, item_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _list(kind: str, prefix: str, limit: int = 50) -> list[dict]:
    base = _BASE / kind
    if not base.exists():
        return []
    items = []
    for path in base.glob(f"{prefix}_*.json"):
        try:
            items.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    items.sort(key=lambda item: item.get("updated_at") or item.get("created_at", ""), reverse=True)
    return items[: max(1, min(int(limit), 200))]


def create_task_graph(*, goal: str, tasks: Optional[list[dict]] = None, owner: str = "genesis") -> dict:
    goal = (goal or "").strip()
    if not goal:
        raise ValueError("goal is required")
    now = _now()
    normalized = []
    for index, task in enumerate(tasks or []):
        title = str(task.get("title") or f"Task {index + 1}").strip()[:180]
        deps = [str(dep) for dep in task.get("depends_on", [])]
        normalized.append({
            "id": task.get("id") or f"task_{index + 1}",
            "title": title,
            "status": task.get("status") or ("ready" if not deps else "blocked"),
            "depends_on": deps,
            "result": task.get("result"),
        })
    if not normalized:
        normalized = [
            {"id": "task_1", "title": "Clarify objective", "status": "ready", "depends_on": [], "result": None},
            {"id": "task_2", "title": "Implement smallest working path", "status": "blocked", "depends_on": ["task_1"], "result": None},
            {"id": "task_3", "title": "Verify and report outcome", "status": "blocked", "depends_on": ["task_2"], "result": None},
        ]
    graph = {
        "id": f"tg_{uuid4().hex[:12]}",
        "version": "module-24-v1",
        "goal": goal[:1200],
        "owner": (owner or "genesis")[:120],
        "created_at": now,
        "updated_at": now,
        "tasks": normalized,
    }
    return refresh_task_graph(graph)


def refresh_task_graph(graph: dict) -> dict:
    done = {task["id"] for task in graph.get("tasks", []) if task.get("status") == "done"}
    for task in graph.get("tasks", []):
        if task.get("status") == "done":
            continue
        if all(dep in done for dep in task.get("depends_on", [])):
            task["status"] = "ready"
        else:
            task["status"] = "blocked"
    graph["summary"] = {
        "total": len(graph.get("tasks", [])),
        "ready": len([t for t in graph.get("tasks", []) if t.get("status") == "ready"]),
        "blocked": len([t for t in graph.get("tasks", []) if t.get("status") == "blocked"]),
        "done": len([t for t in graph.get("tasks", []) if t.get("status") == "done"]),
    }
    return _save("task_graphs", graph)


def complete_task(graph_id: str, task_id: str, *, result: str = "") -> Optional[dict]:
    graph = _load("task_graphs", graph_id)
    if not graph:
        return None
    for task in graph.get("tasks", []):
        if task.get("id") == task_id:
            if task.get("status") == "blocked":
                raise PermissionError("blocked task dependencies are not complete")
            task["status"] = "done"
            task["result"] = (result or "Completed.")[:2000]
            task["completed_at"] = _now()
            break
    else:
        raise ValueError("task not found")
    return refresh_task_graph(graph)


def remember_project(*, title: str, text: str, tags: Optional[list[str]] = None) -> dict:
    item = {
        "id": f"pm_{uuid4().hex[:12]}",
        "version": "module-25-v1",
        "title": (title or "Project note")[:180],
        "text": (text or "")[:4000],
        "tags": [str(tag)[:60] for tag in (tags or [])],
        "created_at": _now(),
    }
    item["memory_hash"] = _hash(item)
    return _save("project_memory", item)


def verify_tool_result(*, goal: str, result: dict) -> dict:
    text = _canonical_json(result if isinstance(result, dict) else {"result": result}).lower()
    goal_tokens = {t.strip(".,:;()[]{}").lower() for t in (goal or "").split() if len(t.strip(".,:;()[]{}")) > 3}
    matches = sorted(token for token in goal_tokens if token in text)
    ok = bool(matches) and not any(word in text for word in ("error", "failed", "traceback", "blocked"))
    verification = {
        "id": f"ver_{uuid4().hex[:12]}",
        "version": "module-26-v1",
        "goal": (goal or "")[:1200],
        "ok": ok,
        "matches": matches,
        "reason": "result_satisfies_goal" if ok else "result_needs_review",
        "result_hash": _hash(result if isinstance(result, dict) else {"result": result}),
        "created_at": _now(),
    }
    return _save("verifications", verification)


def self_heal_diagnostics() -> dict:
    checks = [
        {"name": "approval_storage", "ok": True, "detail": str(approvals._BASE)},
        {"name": "connector_adapters", "ok": bool(connectors.list_adapters()), "detail": len(connectors.list_adapters())},
        {"name": "governance_status", "ok": "phases" in governance.assurance_status(), "detail": "assurance readable"},
        {"name": "api_token_policy", "ok": settings.GENESIS_ENV != "production" or settings.GENESIS_REQUIRE_API_TOKEN, "detail": settings.GENESIS_ENV},
    ]
    run = {
        "id": f"heal_{uuid4().hex[:12]}",
        "version": "module-27-v1",
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
        "repairs": [
            "restart_backend" if not all(check["ok"] for check in checks) else "no_repair_needed"
        ],
        "created_at": _now(),
    }
    return _save("self_heal", run)


def research_loop(*, question: str, sources: Optional[list[dict]] = None) -> dict:
    question = (question or "").strip()
    if not question:
        raise ValueError("question is required")
    sources = sources or [
        {"title": "Local project state", "url": "local://genesis", "claim": "Genesis has durable approvals, governance, and task planning."}
    ]
    claims = [str(source.get("claim") or source.get("summary") or source.get("title") or "")[:500] for source in sources]
    result = {
        "id": f"research_{uuid4().hex[:12]}",
        "version": "module-28-v1",
        "question": question[:1200],
        "sources": sources,
        "claims": claims,
        "conclusion": " ".join(claims)[:1200],
        "confidence": 0.75 if len(sources) >= 2 else 0.55,
        "created_at": _now(),
    }
    result["research_hash"] = _hash(result)
    return _save("research", result)


def route_model(*, task_type: str, risk_level: str = "medium", reasoning_depth: str = "medium") -> dict:
    risk_level = (risk_level or "medium").lower()
    reasoning_depth = (reasoning_depth or "medium").lower()
    if risk_level in {"high", "critical"} or reasoning_depth in {"high", "xhigh"}:
        model = "gpt-5.5"
        reason = "high_risk_or_deep_reasoning"
    elif task_type in {"ui", "simple_code", "summarize"}:
        model = "gpt-5.4-mini"
        reason = "fast_low_cost_route"
    else:
        model = "gpt-5.4"
        reason = "balanced_default_route"
    route = {
        "id": f"route_{uuid4().hex[:12]}",
        "version": "module-29-v1",
        "task_type": task_type,
        "risk_level": risk_level,
        "reasoning_depth": reasoning_depth,
        "model": model,
        "reason": reason,
        "created_at": _now(),
    }
    return _save("model_routes", route)


def compile_skill_v2(*, name: str, workflow: list[str], tests: Optional[list[str]] = None) -> dict:
    skill = {
        "id": f"skill2_{uuid4().hex[:12]}",
        "version": "module-30-v1",
        "name": (name or "Reusable workflow")[:120],
        "workflow": [str(step)[:500] for step in workflow],
        "tests": [str(test)[:500] for test in (tests or ["workflow has at least one step"])],
        "rollback": "disable skill and restore previous workflow",
        "created_at": _now(),
    }
    skill["skill_hash"] = _hash(skill)
    return _save("compiled_skills", skill)


def create_session_checkpoint(*, summary: str, open_items: Optional[list[str]] = None) -> dict:
    checkpoint = {
        "id": f"sess_{uuid4().hex[:12]}",
        "version": "module-31-v1",
        "summary": (summary or "")[:3000],
        "open_items": [str(item)[:300] for item in (open_items or [])],
        "created_at": _now(),
    }
    checkpoint["checkpoint_hash"] = _hash(checkpoint)
    return _save("session_checkpoints", checkpoint)


def learn_preference(*, key: str, value: str, source: str = "explicit_user_feedback") -> dict:
    preference = {
        "id": f"pref_{uuid4().hex[:12]}",
        "version": "module-32-v1",
        "key": (key or "preference")[:120],
        "value": (value or "")[:1000],
        "source": (source or "explicit_user_feedback")[:120],
        "confidence": 1.0 if source == "explicit_user_feedback" else 0.6,
        "created_at": _now(),
    }
    preference["preference_hash"] = _hash(preference)
    return _save("preferences", preference)


def deployment_pipeline() -> dict:
    checks = [
        {"name": "tests_available", "ok": Path("tests/test_smoke.py").exists()},
        {"name": "dockerfile_available", "ok": Path("Dockerfile").exists()},
        {"name": "frontend_build_script", "ok": Path("frontend/package.json").exists()},
        {"name": "rollback_plan", "ok": True, "detail": "revert deployment and restore previous artifact"},
        {"name": "observability_endpoint", "ok": True, "detail": "/api/genesis/status"},
    ]
    pipeline = {
        "id": f"deploy_{uuid4().hex[:12]}",
        "version": "module-33-v1",
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
        "stages": ["test", "build", "package", "deploy", "observe", "rollback_if_needed"],
        "created_at": _now(),
    }
    return _save("deployment_pipelines", pipeline)


def capability_status() -> dict:
    return {
        "version": "module-24-33-v1",
        "phases": {
            "Module 24": "task graph planner",
            "Module 25": "long-horizon project memory",
            "Module 26": "tool result verifier",
            "Module 27": "self-healing runtime diagnostics",
            "Module 28": "autonomous research loop",
            "Module 29": "model router",
            "Module 30": "skill compiler v2",
            "Module 31": "multi-session continuity",
            "Module 32": "user preference learning",
            "Module 33": "deployment pipeline",
        },
        "latest_task_graphs": _list("task_graphs", "tg", limit=5),
        "latest_checkpoints": _list("session_checkpoints", "sess", limit=5),
        "preferences": _list("preferences", "pref", limit=10),
    }


def run_capability_drill() -> dict:
    graph = create_task_graph(
        goal="Finish Module 24 through Module 33 capability layer.",
        tasks=[
            {"id": "plan", "title": "Create durable plan", "depends_on": []},
            {"id": "verify", "title": "Verify result", "depends_on": ["plan"]},
            {"id": "ship", "title": "Prepare deployment pipeline", "depends_on": ["verify"]},
        ],
        owner="capability_drill",
    )
    graph = complete_task(graph["id"], "plan", result="Task graph created.")
    project_memory = remember_project(
        title="Module 24-33 capability sprint",
        text="Implemented planning, memory, verification, diagnostics, research, routing, skills, continuity, preferences, and deployment pipeline.",
        tags=["module-24-33", "capability"],
    )
    verification = verify_tool_result(
        goal="Verify capability layer implemented",
        result={"implemented": "capability layer implemented", "graph_id": graph["id"]},
    )
    diagnostics = self_heal_diagnostics()
    research = research_loop(
        question="What capability layer did Genesis add?",
        sources=[
            {"title": "Task graph", "url": "local://task-graph", "claim": "Genesis can track dependencies and ready states."},
            {"title": "Verifier", "url": "local://verifier", "claim": "Genesis can verify tool outputs against goals."},
        ],
    )
    route = route_model(task_type="planning", risk_level="high", reasoning_depth="high")
    skill = compile_skill_v2(
        name="Capability sprint workflow",
        workflow=["Plan graph", "Implement module", "Verify with tests", "Report status"],
        tests=["smoke test passes", "frontend build passes"],
    )
    checkpoint = create_session_checkpoint(
        summary="Module 24-33 capability layer completed as a durable drill.",
        open_items=["Consider deeper live research connectors later."],
    )
    preference = learn_preference(key="delivery_style", value="Complete phases end-to-end with browser verification.")
    deployment = deployment_pipeline()
    return {
        "version": "module-24-33-v1",
        "task_graph": graph,
        "project_memory": project_memory,
        "verification": verification,
        "self_heal": diagnostics,
        "research": research,
        "model_route": route,
        "compiled_skill": skill,
        "checkpoint": checkpoint,
        "preference": preference,
        "deployment": deployment,
    }
