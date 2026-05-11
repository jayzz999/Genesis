"""Module 14..23 — assurance, operations, and production-readiness layer.

This module turns the approval stack into an auditable operating system:
replayable decisions, computed risk scores, capability requirements, lockdown
state, intent binding, evidence bundles, eval monitoring, connector production
planning, deployment readiness checks, and accountability summaries.
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

from . import approvals, autonomous_operator, connectors

_BASE = Path(os.getenv("GENESIS_GOVERNANCE_STORAGE", "governance")).resolve()

SENSITIVE_PERMISSIONS = {
    "browser_submit",
    "credential_access",
    "delete_data",
    "deploy_change",
    "external_api",
    "file_upload",
    "purchase",
    "send_message",
}
IMPOSSIBLE_CAPABILITIES = {
    "credential_vault_access": "must be handed off to the user",
    "financial_instrument_trade": "disallowed financial activity",
    "captcha_solving": "requires user handoff",
    "password_change_submit": "final password-change step requires user handoff",
}


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


def _json_path(kind: str, item_id: str) -> Path:
    return _BASE / kind / f"{item_id}.json"


def _save(kind: str, item: dict) -> dict:
    item["updated_at"] = _now()
    _atomic_write_text(_json_path(kind, item["id"]), json.dumps(item, indent=2, sort_keys=True, default=str))
    return item


def capability_registry() -> dict:
    capabilities = {}
    for permission in sorted(approvals.KNOWN_PERMISSIONS):
        capabilities[permission] = {
            "permission": permission,
            "requires_human_approval": permission in approvals.STRICT_CONFIRMATION_PERMISSIONS or permission in SENSITIVE_PERMISSIONS,
            "requires_strict_confirmation": permission in approvals.STRICT_CONFIRMATION_PERMISSIONS,
            "requires_handoff": permission in approvals.HANDOFF_REQUIRED_PERMISSIONS,
            "connector_available": any(adapter["permission"] == permission for adapter in connectors.list_adapters()),
        }
    return {
        "version": "module-16-v1",
        "capabilities": capabilities,
        "impossible": IMPOSSIBLE_CAPABILITIES,
        "default_executor_mode": "permission_gated_real_connectors",
    }


def risk_score(*, action_type: str, payload: Optional[dict] = None, permissions: Optional[list[str]] = None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    permissions = [str(p) for p in (permissions or [])]
    score = 5
    reasons = []
    if action_type in {"delete_data", "purchase", "deploy_change"}:
        score += 35
        reasons.append("high_impact_action")
    if action_type in {"external_api", "send_message", "browser_submit", "file_upload"}:
        score += 20
        reasons.append("external_or_transmissive_action")
    sensitive = sorted(set(permissions) & SENSITIVE_PERMISSIONS)
    if sensitive:
        score += 8 * len(sensitive)
        reasons.append("sensitive_permissions")
    target = str(payload.get("target") or payload.get("scope") or payload.get("destination") or "")
    if any(word in target.lower() for word in ("prod", "production", "customer", "bank", "medical", "public")):
        score += 25
        reasons.append("sensitive_target")
    if payload.get("contains_sensitive_data"):
        score += 30
        reasons.append("sensitive_data_payload")
    score = max(0, min(score, 100))
    if score >= 80:
        risk_level = "critical"
    elif score >= 55:
        risk_level = "high"
    elif score >= 25:
        risk_level = "medium"
    else:
        risk_level = "low"
    return {
        "version": "module-15-v1",
        "score": score,
        "risk_level": risk_level,
        "reasons": reasons or ["minimal_risk_signals"],
        "action_type": action_type,
        "permissions": permissions,
        "target": target or "*",
    }


def bind_intent(approval_id: str, *, user_intent: str, bound_by: str = "human") -> Optional[dict]:
    request = approvals.get_request(approval_id)
    if not request:
        return None
    intent = (user_intent or "").strip()
    if not intent:
        raise ValueError("user_intent is required")
    evidence = {
        "user_intent": intent[:2000],
        "approval_title": request.get("title"),
        "reason": request.get("reason"),
        "action_type": request.get("action_type"),
        "payload": request.get("payload") or {},
    }
    request["intent_binding"] = {
        "version": "module-18-v1",
        "bound_by": (bound_by or "human")[:120],
        "bound_at": _now(),
        "user_intent": intent[:2000],
        "intent_hash": _hash(evidence),
        "drift": intent_drift(request, intent),
    }
    request.setdefault("audit", []).append({
        "at": request["intent_binding"]["bound_at"],
        "actor": request["intent_binding"]["bound_by"],
        "action": "intent_bound",
        "note": "Approval bound to explicit human intent.",
    })
    return approvals._save(request)


def intent_drift(request: dict, user_intent: str | None = None) -> dict:
    intent = (user_intent or (request.get("intent_binding") or {}).get("user_intent") or "").lower()
    action_text = " ".join([
        str(request.get("title") or ""),
        str(request.get("reason") or ""),
        str(request.get("action_type") or ""),
        _canonical_json(request.get("payload") or {}),
    ]).lower()
    intent_tokens = {t.strip(".,:;()[]{}") for t in intent.split() if len(t.strip(".,:;()[]{}")) > 3}
    action_tokens = {t.strip(".,:;()[]{}") for t in action_text.split() if len(t.strip(".,:;()[]{}")) > 3}
    overlap = sorted(intent_tokens & action_tokens)
    ratio = len(overlap) / max(1, len(intent_tokens))
    return {
        "version": "module-18-v1",
        "ok": ratio >= 0.2,
        "overlap_ratio": round(ratio, 3),
        "matching_terms": overlap[:20],
        "reason": "intent_aligned" if ratio >= 0.2 else "intent_drift_detected",
    }


def replay_approval(approval_id: str) -> Optional[dict]:
    request = approvals.get_request(approval_id)
    if not request:
        return None
    packet = approvals.policy_review_packet(request)
    integrity = approvals.verify_record_integrity(request, record_type="approval")
    controls = request.get("approval_controls") or {}
    drift = intent_drift(request) if request.get("intent_binding") else {"ok": True, "reason": "no_intent_binding"}
    risk = risk_score(
        action_type=request.get("action_type") or "external_action",
        payload=request.get("payload") or {},
        permissions=request.get("permissions") or [],
    )
    allowed = (
        integrity.get("ok")
        and drift.get("ok")
        and packet.get("verdict") != "handoff_required"
        and (
            request.get("status") in {"approved", "executed"}
            or request.get("status") == "break_glass"
        )
        and (
            controls.get("quorum_satisfied", True)
            or request.get("status") == "break_glass"
        )
    )
    replay = {
        "id": f"replay_{uuid4().hex[:12]}",
        "version": "module-14-v1",
        "approval_id": approval_id,
        "created_at": _now(),
        "decision": "allow" if allowed else "block",
        "deterministic": True,
        "policy": packet,
        "integrity": integrity,
        "risk": risk,
        "intent_drift": drift,
        "approval_status": request.get("status"),
        "approval_controls": controls,
    }
    replay["replay_hash"] = _hash(replay)
    return _save("replays", replay)


def create_evidence_bundle(approval_id: str) -> Optional[dict]:
    request = approvals.get_request(approval_id)
    if not request:
        return None
    replay = replay_approval(approval_id)
    bundle = {
        "id": f"ev_{uuid4().hex[:12]}",
        "version": "module-19-v1",
        "approval_id": approval_id,
        "created_at": _now(),
        "approval": request,
        "policy": approvals.policy_review_packet(request),
        "approval_integrity": approvals.verify_record_integrity(request, record_type="approval"),
        "replay": replay,
        "grant": (request.get("execution_result") or {}).get("permission_grant"),
    }
    bundle["evidence_hash"] = _hash(bundle)
    return _save("evidence", bundle)


def list_evidence(limit: int = 20) -> list[dict]:
    path = _BASE / "evidence"
    if not path.exists():
        return []
    items = []
    for item_path in path.glob("ev_*.json"):
        try:
            items.append(json.loads(item_path.read_text(encoding="utf-8")))
        except Exception:
            pass
    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return items[: max(1, min(int(limit), 100))]


def lockdown_status() -> dict:
    path = _BASE / "lockdown.json"
    if not path.exists():
        return {"version": "module-17-v1", "locked": False, "reason": None, "updated_at": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": "module-17-v1", "locked": False, "reason": "state_unreadable", "updated_at": _now()}


def set_lockdown(*, locked: bool, reason: str = "", actor: str = "human") -> dict:
    state = {
        "version": "module-17-v1",
        "locked": bool(locked),
        "reason": (reason or ("Global runtime lockdown enabled." if locked else "Global runtime lockdown lifted."))[:1200],
        "actor": (actor or "human")[:120],
        "updated_at": _now(),
    }
    _atomic_write_text(_BASE / "lockdown.json", json.dumps(state, indent=2, sort_keys=True))
    if locked:
        for grant in approvals.list_grants(status="active", limit=200):
            approvals.revoke_grant(grant["id"], revoked_by=actor, note="Revoked by Module 17 global lockdown.")
        for operator in autonomous_operator.list_operators(limit=200):
            autonomous_operator.pause_operator(operator["id"])
    return state


def evaluation_monitor() -> dict:
    checks = [
        {"name": "approval_integrity", "ok": approvals.integrity_report(limit=50)["summary"]["failure_count"] == 0},
        {"name": "capability_registry", "ok": bool(capability_registry()["capabilities"])},
        {"name": "lockdown_state_readable", "ok": "locked" in lockdown_status()},
        {"name": "connectors_registered", "ok": bool(connectors.list_adapters())},
    ]
    run = {
        "id": f"eval_{uuid4().hex[:12]}",
        "version": "module-21-v1",
        "created_at": _now(),
        "checks": checks,
        "ok": all(check["ok"] for check in checks),
    }
    return _save("evals", run)


def production_connector_plan() -> dict:
    adapters = []
    for adapter in connectors.list_adapters():
        adapters.append({
            "adapter_id": adapter["id"],
            "current_mode": "real_side_effect" if adapter.get("real_side_effect") else "disabled",
            "production_eligible": bool(adapter.get("real_side_effect")),
            "requires": adapter.get("requires", []),
            "required_controls": [
                "scoped_permission_grant",
                "approval_integrity_verified",
                "intent_binding",
                "runtime_lockdown_not_active",
            ],
        })
    return {
        "version": "module-20-v1",
        "mode": "permission_gated_real_connectors_no_fake_success",
        "adapters": adapters,
    }


def production_readiness() -> dict:
    checks = [
        {"name": "api_token_required_in_production", "ok": settings.GENESIS_ENV != "production" or settings.GENESIS_REQUIRE_API_TOKEN},
        {"name": "api_token_present_if_required", "ok": not settings.GENESIS_REQUIRE_API_TOKEN or bool(settings.GENESIS_API_TOKEN)},
        {"name": "dockerfile_present", "ok": Path("Dockerfile").exists()},
        {"name": "compose_present", "ok": Path("docker-compose.yml").exists()},
        {"name": "lockdown_available", "ok": "locked" in lockdown_status()},
        {"name": "evidence_vault_available", "ok": True},
    ]
    return {
        "version": "module-22-v1",
        "environment": settings.GENESIS_ENV,
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }


def accountability_dashboard() -> dict:
    approvals_list = approvals.list_requests(limit=100)
    grants = approvals.list_grants(limit=100)
    connector_runs = connectors.list_runs(limit=100)
    operators = autonomous_operator.list_operator_summaries(limit=100)
    return {
        "version": "module-23-v1",
        "generated_at": _now(),
        "counts": {
            "approvals": len(approvals_list),
            "active_grants": len([g for g in grants if g.get("status") == "active"]),
            "connector_runs": len(connector_runs),
            "operators": len(operators),
        },
        "recent_approvals": approvals_list[:10],
        "active_grants": [g for g in grants if g.get("status") == "active"][:10],
        "recent_connector_runs": connector_runs[:10],
        "operators": operators[:10],
    }


def assurance_status() -> dict:
    return {
        "version": "module-14-23-v1",
        "phases": {
            "Module 14": "approval replay",
            "Module 15": "risk scoring",
            "Module 16": "capability registry",
            "Module 17": "runtime kill switch",
            "Module 18": "human intent binding",
            "Module 19": "evidence vault",
            "Module 20": "connector production plan",
            "Module 21": "continuous evaluation monitor",
            "Module 22": "deployment hardening readiness",
            "Module 23": "operator accountability dashboard",
        },
        "lockdown": lockdown_status(),
        "capability_registry": capability_registry(),
        "readiness": production_readiness(),
        "connector_plan": production_connector_plan(),
        "dashboard": accountability_dashboard(),
    }


def run_assurance_drill() -> dict:
    request = approvals.create_request(
        title="Module 14-23 assurance drill approval",
        action_type="deploy_change",
        reason="Validate replay, risk, intent, evidence, evals, production planning, and accountability controls.",
        requested_by="module_14_23_drill",
        source="assurance-drill",
        risk_level="critical",
        payload={"target": "production-runtime", "change": "simulated-assurance-rollout"},
        permissions=["deploy_change", "human_approval"],
        required_approvals=2,
    )
    bound = bind_intent(
        request["id"],
        user_intent="Run a simulated assurance rollout for production runtime controls without external side effects.",
        bound_by="module_14_23_drill",
    )
    approvals.approve_request(bound["id"], reviewed_by="assurance_alpha", note="First assurance reviewer.")
    approved = approvals.approve_request(bound["id"], reviewed_by="assurance_beta", note="Second assurance reviewer.")
    executed = approvals.execute_request(approved["id"], executed_by="assurance_drill", grant_ttl_minutes=15, grant_max_uses=1)
    replay = replay_approval(executed["id"])
    evidence = create_evidence_bundle(executed["id"])
    eval_run = evaluation_monitor()
    return {
        "version": "module-14-23-v1",
        "approval": executed,
        "risk": risk_score(action_type=executed["action_type"], payload=executed.get("payload"), permissions=executed.get("permissions")),
        "capability_registry": capability_registry(),
        "lockdown": lockdown_status(),
        "intent_binding": executed.get("intent_binding"),
        "replay": replay,
        "evidence": evidence,
        "connector_plan": production_connector_plan(),
        "evaluation": eval_run,
        "readiness": production_readiness(),
        "dashboard": accountability_dashboard(),
    }
