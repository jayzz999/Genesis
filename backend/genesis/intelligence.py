"""Module 34..43 — product intelligence and release management layer."""

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

from . import approvals, capabilities, connectors, governance

_BASE = Path(os.getenv("GENESIS_INTELLIGENCE_STORAGE", "intelligence")).resolve()

SENSITIVITY_LEVELS = {"public": 10, "internal": 35, "confidential": 70, "restricted": 95}


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


def build_knowledge_graph() -> dict:
    nodes = []
    edges = []
    for request in approvals.list_requests(limit=50):
        nodes.append({"id": request["id"], "type": "approval", "label": request.get("title")})
        grant = (request.get("execution_result") or {}).get("permission_grant")
        if grant:
            nodes.append({"id": grant["id"], "type": "grant", "label": grant.get("action_type")})
            edges.append({"from": request["id"], "to": grant["id"], "type": "minted"})
    cap_status = capabilities.capability_status()
    for graph in cap_status.get("latest_task_graphs", []):
        nodes.append({"id": graph["id"], "type": "task_graph", "label": graph.get("goal")})
        for task in graph.get("tasks", []):
            tid = f"{graph['id']}:{task['id']}"
            nodes.append({"id": tid, "type": "task", "label": task.get("title"), "status": task.get("status")})
            edges.append({"from": graph["id"], "to": tid, "type": "contains"})
    graph = {
        "id": f"kg_{uuid4().hex[:12]}",
        "version": "module-34-v1",
        "created_at": _now(),
        "nodes": nodes,
        "edges": edges,
        "summary": {"nodes": len(nodes), "edges": len(edges)},
    }
    graph["graph_hash"] = _hash(graph)
    return _save("knowledge_graphs", graph)


def create_goal_contract(*, goal: str, success_criteria: Optional[list[str]] = None, constraints: Optional[list[str]] = None, forbidden: Optional[list[str]] = None) -> dict:
    goal = (goal or "").strip()
    if not goal:
        raise ValueError("goal is required")
    contract = {
        "id": f"contract_{uuid4().hex[:12]}",
        "version": "module-35-v1",
        "goal": goal[:1200],
        "success_criteria": [str(item)[:300] for item in (success_criteria or ["tests pass", "browser verification passes"])],
        "constraints": [str(item)[:300] for item in (constraints or ["no unapproved external side effects"])],
        "forbidden": [str(item)[:300] for item in (forbidden or ["credential access", "financial transactions"])],
        "verification_gates": ["unit_or_smoke_tests", "frontend_build", "browser_preview"],
        "created_at": _now(),
    }
    contract["contract_hash"] = _hash(contract)
    return _save("goal_contracts", contract)


def generate_tests(*, target: str, behaviors: Optional[list[str]] = None) -> dict:
    behaviors = behaviors or ["status route responds", "drill route returns versioned artifact"]
    tests = []
    for index, behavior in enumerate(behaviors, start=1):
        tests.append({
            "name": f"test_generated_{index}_{target.replace('-', '_')[:40]}",
            "behavior": behavior,
            "assertion": f"Verify {target} {behavior}.",
        })
    suite = {
        "id": f"testgen_{uuid4().hex[:12]}",
        "version": "module-36-v1",
        "target": target[:160],
        "tests": tests,
        "coverage_evidence": {"count": len(tests), "mode": "generated_spec"},
        "created_at": _now(),
    }
    suite["suite_hash"] = _hash(suite)
    return _save("generated_tests", suite)


def environment_awareness() -> dict:
    env = {
        "id": f"env_{uuid4().hex[:12]}",
        "version": "module-37-v1",
        "cwd": str(Path.cwd()),
        "backend_port": int(os.getenv("PORT", "8002")),
        "environment": settings.GENESIS_ENV,
        "llm_provider": settings.GENESIS_LLM_PROVIDER,
        "api_token_required": settings.GENESIS_REQUIRE_API_TOKEN,
        "files": {
            "dockerfile": Path("Dockerfile").exists(),
            "frontend_package": Path("frontend/package.json").exists(),
            "tests": Path("tests/test_smoke.py").exists(),
        },
        "created_at": _now(),
    }
    env["environment_hash"] = _hash(env)
    return _save("environments", env)


def incident_response(*, title: str, severity: str = "medium", signals: Optional[list[str]] = None) -> dict:
    severity = (severity or "medium").lower()
    signals = [str(signal)[:300] for signal in (signals or [])]
    mitigations = ["capture diagnostics", "pause risky operators", "verify health endpoints"]
    if severity in {"high", "critical"}:
        mitigations.insert(0, "enable lockdown if external side effects are suspected")
    incident = {
        "id": f"inc_{uuid4().hex[:12]}",
        "version": "module-38-v1",
        "title": (title or "Runtime incident")[:180],
        "severity": severity,
        "signals": signals,
        "mitigations": mitigations,
        "postmortem": {
            "status": "draft",
            "sections": ["impact", "timeline", "root cause", "corrective actions"],
        },
        "created_at": _now(),
    }
    incident["incident_hash"] = _hash(incident)
    return _save("incidents", incident)


def classify_data(*, name: str, sample: str = "", declared_level: str = "internal") -> dict:
    text = (sample or "").lower()
    level = declared_level if declared_level in SENSITIVITY_LEVELS else "internal"
    if any(token in text for token in ("password", "secret", "ssn", "medical", "bank", "token")):
        level = "restricted"
    elif any(token in text for token in ("email", "phone", "customer", "address")) and SENSITIVITY_LEVELS[level] < 70:
        level = "confidential"
    classification = {
        "id": f"data_{uuid4().hex[:12]}",
        "version": "module-39-v1",
        "name": (name or "data")[:120],
        "sensitivity": level,
        "score": SENSITIVITY_LEVELS[level],
        "retention": "minimize" if level in {"confidential", "restricted"} else "standard",
        "sharing_rule": "human_approval_required" if level in {"confidential", "restricted"} else "internal_allowed",
        "processing_paths": ["local_only", "approved_connector"] if level != "public" else ["local", "approved_connector", "public_output"],
        "created_at": _now(),
    }
    classification["classification_hash"] = _hash(classification)
    return _save("data_classifications", classification)


def connector_marketplace() -> dict:
    adapters = []
    for adapter in connectors.list_adapters():
        adapters.append({
            "id": adapter["id"],
            "name": adapter["name"],
            "permission": adapter["permission"],
            "enabled": True,
            "test_status": "available",
            "requires_approval": adapter["permission"] in approvals.KNOWN_PERMISSIONS,
        })
    marketplace = {
        "id": f"market_{uuid4().hex[:12]}",
        "version": "module-40-v1",
        "connectors": adapters,
        "summary": {"total": len(adapters), "enabled": len([a for a in adapters if a["enabled"]])},
        "created_at": _now(),
    }
    marketplace["marketplace_hash"] = _hash(marketplace)
    return _save("marketplace", marketplace)


def record_feedback(*, target: str, rating: int, note: str = "") -> dict:
    rating = max(1, min(int(rating), 5))
    feedback = {
        "id": f"fb_{uuid4().hex[:12]}",
        "version": "module-41-v1",
        "target": (target or "general")[:160],
        "rating": rating,
        "note": (note or "")[:1000],
        "learning": "reinforce" if rating >= 4 else "adjust",
        "created_at": _now(),
    }
    feedback["feedback_hash"] = _hash(feedback)
    return _save("feedback", feedback)


def resource_governor(*, model_calls: int = 0, connector_runs: int = 0, storage_mb: float = 0.0) -> dict:
    costs = {
        "model_call_units": max(0, int(model_calls)),
        "connector_run_units": max(0, int(connector_runs)),
        "storage_mb": max(0.0, float(storage_mb)),
    }
    score = costs["model_call_units"] + costs["connector_run_units"] * 2 + int(costs["storage_mb"] / 10)
    governor = {
        "id": f"cost_{uuid4().hex[:12]}",
        "version": "module-42-v1",
        "usage": costs,
        "budget_score": score,
        "throttle": score > 100,
        "recommendation": "throttle_nonessential_work" if score > 100 else "within_budget",
        "created_at": _now(),
    }
    governor["resource_hash"] = _hash(governor)
    return _save("resource_governor", governor)


def release_manager(*, version: str, changes: Optional[list[str]] = None) -> dict:
    readiness = governance.production_readiness()
    deployment = capabilities.deployment_pipeline()
    release = {
        "id": f"rel_{uuid4().hex[:12]}",
        "version": "module-43-v1",
        "release_version": (version or "0.1.0")[:80],
        "changes": [str(change)[:300] for change in (changes or ["Capability and intelligence phases completed"])],
        "verification": {
            "production_readiness": readiness,
            "deployment_pipeline": deployment,
        },
        "rollback_plan": "restore previous build artifact and revoke newly issued grants",
        "readiness_score": 100 if readiness.get("ok") and deployment.get("ok") else 70,
        "created_at": _now(),
    }
    release["release_hash"] = _hash(release)
    return _save("releases", release)


def intelligence_status() -> dict:
    return {
        "version": "module-34-43-v1",
        "phases": {
            "Module 34": "knowledge graph",
            "Module 35": "goal contract system",
            "Module 36": "autonomous test generation",
            "Module 37": "environment awareness",
            "Module 38": "incident response mode",
            "Module 39": "data governance layer",
            "Module 40": "plugin connector marketplace",
            "Module 41": "human feedback training loop",
            "Module 42": "cost and resource governor",
            "Module 43": "release manager",
        },
        "latest_graphs": _list("knowledge_graphs", "kg", limit=3),
        "latest_releases": _list("releases", "rel", limit=3),
        "latest_feedback": _list("feedback", "fb", limit=5),
    }


def run_intelligence_drill() -> dict:
    contract = create_goal_contract(
        goal="Ship Module 34 through Module 43 product intelligence layer.",
        success_criteria=["all smoke tests pass", "browser panel renders all phase artifacts"],
        constraints=["simulation-only external effects"],
    )
    graph = build_knowledge_graph()
    tests = generate_tests(target="module-34-43-intelligence", behaviors=["status route responds", "drill returns release artifact"])
    environment = environment_awareness()
    incident = incident_response(title="Simulated capability regression", severity="high", signals=["test failure", "browser mismatch"])
    data = classify_data(name="approval evidence", sample="approval title and user email may appear in evidence", declared_level="internal")
    marketplace = connector_marketplace()
    feedback = record_feedback(target="module-34-43-drill", rating=5, note="End-to-end module drill completed.")
    resources = resource_governor(model_calls=12, connector_runs=3, storage_mb=42)
    release = release_manager(version="module-43.0", changes=["Added intelligence and release management control plane."])
    return {
        "version": "module-34-43-v1",
        "knowledge_graph": graph,
        "goal_contract": contract,
        "generated_tests": tests,
        "environment": environment,
        "incident": incident,
        "data_governance": data,
        "marketplace": marketplace,
        "feedback": feedback,
        "resource_governor": resources,
        "release": release,
    }
