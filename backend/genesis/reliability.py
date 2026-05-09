"""Module 44..53 — reliability and mission execution layer."""

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

from . import approvals, capabilities, governance, intelligence

_BASE = Path(os.getenv("GENESIS_RELIABILITY_STORAGE", "reliability")).resolve()


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


def create_benchmark_pack(*, name: str = "Reliability pack", focus: Optional[list[str]] = None) -> dict:
    focus = focus or ["planning", "memory", "tool_use", "approvals", "release_readiness"]
    cases = [
        {"id": f"bench_{index}", "skill": skill, "expected": "passes_with_evidence", "max_risk": "medium"}
        for index, skill in enumerate(focus, start=1)
    ]
    pack = {
        "id": f"benchpack_{uuid4().hex[:12]}",
        "version": "module-44-v1",
        "name": (name or "Reliability pack")[:160],
        "cases": cases,
        "gates": ["deterministic_assertions", "approval_policy_check", "release_readiness_check"],
        "created_at": _now(),
    }
    pack["pack_hash"] = _hash(pack)
    return _save("benchmark_packs", pack)


def simulate_scenario(*, mission: str, failure_modes: Optional[list[str]] = None) -> dict:
    failure_modes = failure_modes or ["missing_information", "tool_failure", "approval_required"]
    steps = [
        {"step": "clarify_goal", "response": "ask_or_infer_missing_constraints"},
        {"step": "plan", "response": "create_dependency_graph"},
        {"step": "execute_safe_work", "response": "use_configured_or_development_tools"},
        {"step": "verify", "response": "run_tests_and_collect_evidence"},
    ]
    scenario = {
        "id": f"scenario_{uuid4().hex[:12]}",
        "version": "module-45-v1",
        "mission": (mission or "Reliability mission")[:1000],
        "failure_modes": [str(mode)[:160] for mode in failure_modes],
        "steps": steps,
        "success_condition": "mission_report_contains_evidence_and_open_risks",
        "created_at": _now(),
    }
    scenario["scenario_hash"] = _hash(scenario)
    return _save("scenarios", scenario)


def long_horizon_plan(*, goal: str, horizon_days: int = 14) -> dict:
    goal = (goal or "").strip()
    if not goal:
        raise ValueError("goal is required")
    horizon_days = max(1, min(int(horizon_days), 365))
    milestones = [
        {"id": "m1", "title": "Discovery and constraints", "day": 1, "evidence": "goal_contract"},
        {"id": "m2", "title": "Implementation loop", "day": max(2, horizon_days // 3), "evidence": "merged_task_graph"},
        {"id": "m3", "title": "Evaluation and hardening", "day": max(3, horizon_days * 2 // 3), "evidence": "benchmark_pack"},
        {"id": "m4", "title": "Release decision", "day": horizon_days, "evidence": "release_record"},
    ]
    plan = {
        "id": f"lhp_{uuid4().hex[:12]}",
        "version": "module-46-v1",
        "goal": goal[:1200],
        "horizon_days": horizon_days,
        "milestones": milestones,
        "cadence": "daily_check_in",
        "created_at": _now(),
    }
    plan["plan_hash"] = _hash(plan)
    return _save("long_horizon_plans", plan)


def trust_dashboard() -> dict:
    approval_summary = approvals.summary()
    readiness = governance.production_readiness()
    intel = intelligence.intelligence_status()
    dashboard = {
        "id": f"trust_{uuid4().hex[:12]}",
        "version": "module-47-v1",
        "approvals": approval_summary,
        "readiness": readiness,
        "latest_releases": intel.get("latest_releases", []),
        "risk_posture": "review" if approval_summary.get("pending", 0) else "clear",
        "blocked_actions": approval_summary.get("blocked", 0),
        "created_at": _now(),
    }
    dashboard["dashboard_hash"] = _hash(dashboard)
    return _save("trust_dashboards", dashboard)


def remember_workstyle(*, preference: str, value: str, editable: bool = True) -> dict:
    if not (preference or "").strip():
        raise ValueError("preference is required")
    memory = {
        "id": f"workstyle_{uuid4().hex[:12]}",
        "version": "module-48-v1",
        "preference": preference[:160],
        "value": value[:1000],
        "editable": bool(editable),
        "delete_supported": True,
        "confidence": 0.75,
        "created_at": _now(),
    }
    memory["memory_hash"] = _hash(memory)
    return _save("workstyle_memories", memory)


def environment_manager(*, required_env: Optional[list[str]] = None) -> dict:
    required_env = required_env or ["GENESIS_LLM_PROVIDER", "GENESIS_API_TOKEN", "PORT"]
    checks = []
    for key in required_env:
        present = bool(os.getenv(key))
        checks.append({
            "key": key,
            "present": present,
            "status": "configured" if present else "missing",
            "sensitive": "TOKEN" in key or "KEY" in key or "SECRET" in key,
        })
    manager = {
        "id": f"envmgr_{uuid4().hex[:12]}",
        "version": "module-49-v1",
        "environment": settings.GENESIS_ENV,
        "checks": checks,
        "missing": [check["key"] for check in checks if not check["present"]],
        "health": "ready" if all(check["present"] for check in checks if check["key"] != "GENESIS_API_TOKEN") else "needs_configuration",
        "created_at": _now(),
    }
    manager["environment_manager_hash"] = _hash(manager)
    return _save("environment_managers", manager)


def model_router(*, task_type: str = "general", risk_level: str = "medium", latency_ms: int = 0) -> dict:
    high_reasoning = task_type in {"planning", "coding", "release"} or risk_level in {"high", "critical"}
    provider = settings.GENESIS_LLM_PROVIDER
    route = {
        "id": f"router_{uuid4().hex[:12]}",
        "version": "module-50-v1",
        "provider": provider,
        "primary_model": "gpt-5.5" if high_reasoning else "gpt-5.4-mini",
        "fallback_model": "development" if provider == "mock" else "gpt-5.4-mini",
        "task_type": task_type[:80],
        "risk_level": risk_level,
        "estimated_cost_tier": "high" if high_reasoning else "low",
        "latency_budget_ms": max(0, int(latency_ms)) or (30000 if high_reasoning else 8000),
        "created_at": _now(),
    }
    route["router_hash"] = _hash(route)
    return _save("model_routes", route)


def mission_runner(*, goal: str, constraints: Optional[list[str]] = None) -> dict:
    goal = (goal or "").strip()
    if not goal:
        raise ValueError("goal is required")
    constraints = [str(item)[:300] for item in (constraints or ["no external side effects without approval"])]
    graph = capabilities.create_task_graph(
        goal=goal,
        tasks=[
            {"id": "contract", "title": "Write goal contract", "depends_on": []},
            {"id": "plan", "title": "Build execution plan", "depends_on": ["contract"]},
            {"id": "verify", "title": "Run verification gates", "depends_on": ["plan"]},
            {"id": "report", "title": "Prepare mission report", "depends_on": ["verify"]},
        ],
        owner="mission_runner",
    )
    contract = intelligence.create_goal_contract(goal=goal, constraints=constraints)
    mission = {
        "id": f"mission_{uuid4().hex[:12]}",
        "version": "module-51-v1",
        "goal": goal[:1200],
        "constraints": constraints,
        "task_graph": graph,
        "goal_contract": contract,
        "approval_strategy": "request_human_approval_before_external_side_effects",
        "status": "planned",
        "created_at": _now(),
    }
    mission["mission_hash"] = _hash(mission)
    return _save("missions", mission)


def observability_replay(*, run_id: str = "latest") -> dict:
    timeline = [
        {"phase": "input", "event": "goal_received"},
        {"phase": "planning", "event": "task_graph_created"},
        {"phase": "approval", "event": "policy_checked"},
        {"phase": "execution", "event": "safe_steps_completed"},
        {"phase": "verification", "event": "evidence_recorded"},
    ]
    replay = {
        "id": f"replay_{uuid4().hex[:12]}",
        "version": "module-52-v1",
        "run_id": run_id[:160],
        "timeline": timeline,
        "checkpoint": {"replayable": True, "mode": "simulation"},
        "created_at": _now(),
    }
    replay["replay_hash"] = _hash(replay)
    return _save("replays", replay)


def deployment_package(*, target: str = "local-production") -> dict:
    files = {
        "dockerfile": Path("Dockerfile").exists(),
        "compose": Path("docker-compose.yml").exists(),
        "env_example": Path(".env.example").exists(),
        "tests": Path("tests/test_smoke.py").exists(),
        "frontend_package": Path("frontend/package.json").exists(),
    }
    package = {
        "id": f"deploypkg_{uuid4().hex[:12]}",
        "version": "module-53-v1",
        "target": target[:160],
        "files": files,
        "health_checks": ["/api/genesis/status", "/api/genesis/reliability/status"],
        "release_recipe": ["set env", "run tests", "build frontend", "start backend", "verify browser"],
        "ready": all(files.values()),
        "created_at": _now(),
    }
    package["package_hash"] = _hash(package)
    return _save("deployment_packages", package)


def reliability_status() -> dict:
    return {
        "version": "module-44-53-v1",
        "phases": {
            "Module 44": "evaluation benchmark packs",
            "Module 45": "scenario simulator",
            "Module 46": "long-horizon project planner",
            "Module 47": "trust dashboard",
            "Module 48": "user profile and workstyle memory",
            "Module 49": "production secrets and environment manager",
            "Module 50": "real provider model router",
            "Module 51": "end-to-end mission runner",
            "Module 52": "observability and replay studio",
            "Module 53": "production deployment package",
        },
        "latest_missions": _list("missions", "mission", limit=3),
        "latest_replays": _list("replays", "replay", limit=3),
        "latest_packages": _list("deployment_packages", "deploypkg", limit=3),
    }


def run_reliability_drill() -> dict:
    benchmark = create_benchmark_pack(name="Module 44 reliability benchmark")
    scenario = simulate_scenario(mission="Handle a production release with missing information and approval gates.")
    plan = long_horizon_plan(goal="Ship a reliable Genesis mission runner.", horizon_days=21)
    trust = trust_dashboard()
    workstyle = remember_workstyle(preference="delivery_style", value="finish end-to-end with tests and browser proof")
    environment = environment_manager()
    route = model_router(task_type="release", risk_level="high")
    mission = mission_runner(goal="Run a safe end-to-end Genesis mission.")
    replay = observability_replay(run_id=mission["id"])
    package = deployment_package(target="local-preview")
    return {
        "version": "module-44-53-v1",
        "benchmark_pack": benchmark,
        "scenario": scenario,
        "long_horizon_plan": plan,
        "trust_dashboard": trust,
        "workstyle_memory": workstyle,
        "environment_manager": environment,
        "model_router": route,
        "mission_runner": mission,
        "observability_replay": replay,
        "deployment_package": package,
    }
