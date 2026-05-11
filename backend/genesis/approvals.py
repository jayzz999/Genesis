"""Module 7/8/11/12/13 — human approval and permission layer.

This module is the explicit safety valve for actions with external or risky
side effects. Agents can request permission, but execution is blocked until a
human approves the durable request. Real connectors must present scoped grants;
unconfigured connectors fail closed instead of returning artificial success.

Module 8 extends the approval into scoped, expiring permission grants. Future tools
must present a grant and pass validation before their protected action can run.

Module 11 adds deterministic policy review packets and strict execution
confirmation. A reviewer can bind a confirmation phrase to the request evidence
hash before execution, giving Genesis a replayable record of what exactly was
approved.

Module 12 makes approval and grant records tamper-evident. Each durable record is
stamped with a deterministic integrity hash, and verification endpoints can
recompute that hash to detect out-of-band edits.

Module 13 adds operational governance: quorum rules, distinct human reviewers,
duplicate-review prevention, and tightly bounded emergency break-glass grants.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

_BASE = Path(os.getenv("GENESIS_APPROVAL_STORAGE", "approvals")).resolve()

RISK_LEVELS = {"low", "medium", "high", "critical"}
TERMINAL_STATUSES = {"rejected", "expired", "executed", "break_glass"}
APPROVAL_REQUIRED_RISKS = {"medium", "high", "critical"}
KNOWN_PERMISSIONS = {
    "browser_submit",
    "credential_access",
    "delete_data",
    "deploy_change",
    "external_api",
    "file_upload",
    "human_approval",
    "purchase",
    "send_message",
}
HANDOFF_REQUIRED_PERMISSIONS = {"credential_access"}
STRICT_CONFIRMATION_PERMISSIONS = {
    "browser_submit",
    "delete_data",
    "deploy_change",
    "external_api",
    "file_upload",
    "purchase",
    "send_message",
}
DEFAULT_APPROVAL_QUORUM = {
    "low": 1,
    "medium": 1,
    "high": 1,
    "critical": 2,
}
BREAK_GLASS_RISKS = {"high", "critical"}


def _required_approval_count(risk_level: str, requested: int | None = None) -> int:
    baseline = DEFAULT_APPROVAL_QUORUM.get((risk_level or "high").lower(), 1)
    if requested is None:
        return baseline
    return max(baseline, min(int(requested), 5))


def _canonical_json(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _integrity_payload(record: dict) -> dict:
    return {
        key: value
        for key, value in record.items()
        if key not in {"integrity", "integrity_verified"}
    }


def _integrity_hash(record: dict) -> str:
    return hashlib.sha256(_canonical_json(_integrity_payload(record)).encode("utf-8")).hexdigest()


def _stamp_integrity(record: dict, *, record_type: str) -> dict:
    record["integrity"] = {
        "version": "module-12-v1",
        "record_type": record_type,
        "hash": _integrity_hash(record),
        "algorithm": "sha256:c14n-json",
        "stamped_at": _now(),
    }
    return record


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


def _path(approval_id: str) -> Path:
    return _BASE / f"{approval_id}.json"


def _grant_path(grant_id: str) -> Path:
    return _BASE / "grants" / f"{grant_id}.json"


def _normalize_permissions(permissions: list[str] | None, action_type: str, risk_level: str) -> list[str]:
    items = {str(p).strip() for p in (permissions or []) if str(p).strip()}
    if risk_level in APPROVAL_REQUIRED_RISKS:
        items.add("human_approval")
    if action_type in KNOWN_PERMISSIONS:
        items.add(action_type)
    return sorted(items)


def _safety_checks(request: dict) -> dict:
    permissions = set(request.get("permissions") or [])
    risk_level = request.get("risk_level")
    return {
        "requires_human_approval": risk_level in APPROVAL_REQUIRED_RISKS,
        "known_permissions": sorted(permissions & KNOWN_PERMISSIONS),
        "unknown_permissions": sorted(permissions - KNOWN_PERMISSIONS),
        "executor_mode": "permission_gated_real_connectors",
        "can_execute_without_approval": risk_level == "low",
    }


def policy_review_packet(request: dict) -> dict:
    """Build a deterministic Module 11 review packet for a request."""
    permissions = set(request.get("permissions") or [])
    payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
    evidence = {
        "title": request.get("title"),
        "action_type": request.get("action_type"),
        "risk_level": request.get("risk_level"),
        "permissions": sorted(permissions),
        "payload": payload,
        "reason": request.get("reason"),
    }
    evidence_hash = hashlib.sha256(_canonical_json(evidence).encode("utf-8")).hexdigest()
    reasons = []
    if request.get("risk_level") in APPROVAL_REQUIRED_RISKS:
        reasons.append("risk_requires_human_review")
    unknown_permissions = sorted(permissions - KNOWN_PERMISSIONS)
    if unknown_permissions:
        reasons.append("unknown_permissions_present")
    if permissions & HANDOFF_REQUIRED_PERMISSIONS:
        reasons.append("handoff_required_permission")
    if permissions & STRICT_CONFIRMATION_PERMISSIONS:
        reasons.append("strict_execution_confirmation_recommended")
    controls = request.get("approval_controls") or {}
    if int(controls.get("required_approvals") or 1) > 1:
        reasons.append("dual_control_required")

    if permissions & HANDOFF_REQUIRED_PERMISSIONS:
        verdict = "handoff_required"
    elif unknown_permissions:
        verdict = "review_required"
    elif request.get("risk_level") == "low":
        verdict = "allowable"
    else:
        verdict = "review_required"

    target = payload.get("target") or payload.get("scope") or payload.get("destination") or payload.get("system") or "*"
    confirmation_phrase = f"CONFIRM {request.get('id')} {evidence_hash[:8]}"
    return {
        "id": f"pol_{request.get('id', 'unknown')}",
        "approval_id": request.get("id"),
        "verdict": verdict,
        "risk_level": request.get("risk_level"),
        "action_type": request.get("action_type"),
        "target": str(target)[:200],
        "evidence_hash": evidence_hash,
        "confirmation_phrase": confirmation_phrase,
        "required_confirmations": [
            "human_review",
            *(
                ["approval_quorum"]
                if int(controls.get("required_approvals") or 1) > 1
                else []
            ),
            *(
                ["strict_execution_confirmation"]
                if permissions & STRICT_CONFIRMATION_PERMISSIONS or request.get("risk_level") in {"high", "critical"}
                else []
            ),
            *(["handoff_to_user"] if permissions & HANDOFF_REQUIRED_PERMISSIONS else []),
        ],
        "reasons": reasons or ["no_policy_flags"],
        "action_summary": (
            f"{request.get('action_type')} on {target} "
            f"with {request.get('risk_level')} risk and {len(permissions)} permission(s)."
        ),
        "evidence": evidence,
        "approval_controls": controls,
    }


def _save(request: dict) -> dict:
    request["updated_at"] = _now()
    request["safety_checks"] = _safety_checks(request)
    request["policy_review"] = policy_review_packet(request)
    _stamp_integrity(request, record_type="approval")
    _atomic_write_text(_path(request["id"]), json.dumps(request, indent=2, default=str))
    return request


def _save_grant(grant: dict) -> dict:
    grant["updated_at"] = _now()
    _stamp_integrity(grant, record_type="permission_grant")
    _atomic_write_text(_grant_path(grant["id"]), json.dumps(grant, indent=2, default=str))
    return grant


def _refresh_expiry(request: dict) -> dict:
    if request.get("status") in TERMINAL_STATUSES:
        return request
    expires_at = _parse_ts(request.get("expires_at"))
    if expires_at and expires_at < datetime.utcnow():
        request["status"] = "expired"
        request.setdefault("audit", []).append({
            "at": _now(),
            "actor": "system",
            "action": "expired",
            "note": "Approval request expired before execution.",
        })
        return _save(request)
    return request


def _refresh_grant(grant: dict) -> dict:
    if grant.get("status") in {"revoked", "expired", "exhausted"}:
        return grant
    expires_at = _parse_ts(grant.get("expires_at"))
    if expires_at and expires_at < datetime.utcnow():
        grant["status"] = "expired"
        grant.setdefault("audit", []).append({
            "at": _now(),
            "actor": "system",
            "action": "expired",
            "note": "Permission grant expired.",
        })
        return _save_grant(grant)
    if int(grant.get("uses", 0)) >= int(grant.get("max_uses", 1)):
        grant["status"] = "exhausted"
        grant.setdefault("audit", []).append({
            "at": _now(),
            "actor": "system",
            "action": "exhausted",
            "note": "Permission grant reached its max-use limit.",
        })
        return _save_grant(grant)
    return grant


def _grant_scope(request: dict) -> str:
    payload = request.get("payload") or {}
    for key in ("scope", "target", "destination", "system"):
        value = payload.get(key)
        if value:
            return str(value)[:160]
    return "*"


def create_request(
    *,
    title: str,
    action_type: str,
    reason: str,
    requested_by: str = "genesis",
    source: str = "manual",
    risk_level: str = "high",
    payload: Optional[dict] = None,
    permissions: Optional[list[str]] = None,
    expires_in_minutes: int = 1440,
    required_approvals: int | None = None,
) -> dict:
    title = (title or "").strip()
    reason = (reason or "").strip()
    action_type = (action_type or "external_action").strip()
    risk_level = (risk_level or "high").strip().lower()
    if not title:
        raise ValueError("approval title is required")
    if not reason:
        raise ValueError("approval reason is required")
    if risk_level not in RISK_LEVELS:
        raise ValueError(f"risk_level must be one of {sorted(RISK_LEVELS)}")

    now = _now()
    expires_at = (
        datetime.utcnow() + timedelta(minutes=max(1, min(int(expires_in_minutes), 43200)))
    ).isoformat()
    required_count = _required_approval_count(risk_level, required_approvals)
    request = {
        "id": f"apr_{uuid4().hex[:12]}",
        "title": title[:180],
        "action_type": action_type[:80],
        "reason": reason[:2000],
        "requested_by": (requested_by or "genesis")[:120],
        "source": (source or "manual")[:120],
        "risk_level": risk_level,
        "status": "pending",
        "payload": payload if isinstance(payload, dict) else {},
        "permissions": _normalize_permissions(permissions, action_type, risk_level),
        "safety_checks": {},
        "reviewed_by": None,
        "reviewed_at": None,
        "review_note": None,
        "approval_reviews": [],
        "approval_controls": {
            "version": "module-13-v1",
            "required_approvals": required_count,
            "received_approvals": 0,
            "remaining_approvals": required_count,
            "distinct_reviewers": True,
            "break_glass_allowed": risk_level in BREAK_GLASS_RISKS,
            "quorum_satisfied": False,
        },
        "execution_confirmation": None,
        "execution_result": None,
        "expires_at": expires_at,
        "created_at": now,
        "updated_at": now,
        "audit": [
            {
                "at": now,
                "actor": requested_by or "genesis",
                "action": "requested",
                "note": reason[:300],
            }
        ],
    }
    return _save(request)


def issue_grant(
    request: dict,
    *,
    issued_by: str = "genesis",
    ttl_minutes: int = 60,
    max_uses: int = 10,
    break_glass: dict | None = None,
) -> dict:
    now = _now()
    grant = {
        "id": f"gr_{uuid4().hex[:12]}",
        "approval_id": request["id"],
        "status": "active",
        "action_type": request.get("action_type"),
        "scope": _grant_scope(request),
        "permissions": request.get("permissions") or [],
        "risk_level": request.get("risk_level"),
        "issued_by": (issued_by or "genesis")[:120],
        "issued_at": now,
        "expires_at": (
            datetime.utcnow() + timedelta(minutes=max(1, min(int(ttl_minutes), 10080)))
        ).isoformat(),
        "max_uses": max(1, min(int(max_uses), 1000)),
        "uses": 0,
        "break_glass": break_glass if isinstance(break_glass, dict) else None,
        "created_at": now,
        "updated_at": now,
        "audit": [
            {
                "at": now,
                "actor": issued_by or "genesis",
                "action": "issued",
                "note": f"Grant issued from approval {request['id']}.",
            }
        ],
    }
    return _save_grant(grant)


def _approval_controls(request: dict) -> dict:
    controls = request.get("approval_controls") if isinstance(request.get("approval_controls"), dict) else {}
    required = _required_approval_count(request.get("risk_level"), controls.get("required_approvals"))
    reviewers = {
        str(item.get("reviewed_by"))
        for item in request.get("approval_reviews", [])
        if isinstance(item, dict) and item.get("reviewed_by")
    }
    controls = {
        "version": "module-13-v1",
        "required_approvals": required,
        "received_approvals": len(reviewers),
        "remaining_approvals": max(0, required - len(reviewers)),
        "distinct_reviewers": True,
        "break_glass_allowed": request.get("risk_level") in BREAK_GLASS_RISKS,
        "quorum_satisfied": len(reviewers) >= required,
    }
    request["approval_controls"] = controls
    return controls


def get_request(approval_id: str) -> Optional[dict]:
    path = _path(approval_id)
    if not path.exists():
        return None
    try:
        return _refresh_expiry(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def list_requests(status: str | None = None, limit: int = 50) -> list[dict]:
    if not _BASE.exists():
        return []
    requests = []
    for path in _BASE.glob("apr_*.json"):
        request = get_request(path.stem)
        if request and (not status or request.get("status") == status):
            requests.append(request)
    requests.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return requests[: max(1, min(int(limit), 200))]


def get_grant(grant_id: str) -> Optional[dict]:
    path = _grant_path(grant_id)
    if not path.exists():
        return None
    try:
        return _refresh_grant(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def list_grants(status: str | None = None, limit: int = 50) -> list[dict]:
    grant_dir = _BASE / "grants"
    if not grant_dir.exists():
        return []
    grants = []
    for path in grant_dir.glob("gr_*.json"):
        grant = get_grant(path.stem)
        if grant and (not status or grant.get("status") == status):
            grants.append(grant)
    grants.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return grants[: max(1, min(int(limit), 200))]


def verify_record_integrity(record: dict, *, record_type: str) -> dict:
    stored = record.get("integrity") if isinstance(record.get("integrity"), dict) else {}
    expected = _integrity_hash(record)
    ok = stored.get("hash") == expected and stored.get("record_type") == record_type
    return {
        "ok": ok,
        "record_type": record_type,
        "record_id": record.get("id"),
        "stored_hash": stored.get("hash"),
        "expected_hash": expected,
        "algorithm": stored.get("algorithm") or "sha256:c14n-json",
        "version": stored.get("version") or "missing",
        "stamped_at": stored.get("stamped_at"),
        "reason": "integrity_verified" if ok else "integrity_mismatch",
    }


def verify_approval_integrity(approval_id: str) -> Optional[dict]:
    request = get_request(approval_id)
    if not request:
        return None
    return {
        "approval": request,
        "integrity": verify_record_integrity(request, record_type="approval"),
    }


def verify_grant_integrity(grant_id: str) -> Optional[dict]:
    grant = get_grant(grant_id)
    if not grant:
        return None
    return {
        "grant": grant,
        "integrity": verify_record_integrity(grant, record_type="permission_grant"),
    }


def integrity_report(limit: int = 50) -> dict:
    approvals = []
    grants = []
    for request in list_requests(limit=limit):
        approvals.append(verify_record_integrity(request, record_type="approval"))
    for grant in list_grants(limit=limit):
        grants.append(verify_record_integrity(grant, record_type="permission_grant"))
    failures = [item for item in approvals + grants if not item.get("ok")]
    return {
        "ok": not failures,
        "approvals": approvals,
        "grants": grants,
        "checked": len(approvals) + len(grants),
        "failures": failures,
        "summary": {
            "approvals_checked": len(approvals),
            "grants_checked": len(grants),
            "failure_count": len(failures),
        },
    }


def approve_request(approval_id: str, *, reviewed_by: str = "human", note: str = "") -> Optional[dict]:
    request = get_request(approval_id)
    if not request:
        return None
    if request.get("status") in TERMINAL_STATUSES:
        raise ValueError(f"cannot approve a {request.get('status')} request")
    if (request.get("policy_review") or policy_review_packet(request)).get("verdict") == "handoff_required":
        raise PermissionError("approval requires user hand-off and cannot be approved by Genesis")
    reviewer = (reviewed_by or "human")[:120]
    reviews = request.setdefault("approval_reviews", [])
    if any(item.get("reviewed_by") == reviewer for item in reviews if isinstance(item, dict)):
        raise ValueError("reviewer has already approved this request")
    reviewed_at = _now()
    review_note = (note or "Approved by human reviewer.")[:1200]
    reviews.append({
        "reviewed_by": reviewer,
        "reviewed_at": reviewed_at,
        "note": review_note,
    })
    controls = _approval_controls(request)
    request["status"] = "approved" if controls["quorum_satisfied"] else "pending"
    request["reviewed_by"] = reviewer
    request["reviewed_at"] = reviewed_at
    request["review_note"] = review_note
    request.setdefault("audit", []).append({
        "at": reviewed_at,
        "actor": reviewer,
        "action": "approved" if controls["quorum_satisfied"] else "approval_reviewed",
        "note": (
            f"{review_note} "
            f"Quorum {controls['received_approvals']}/{controls['required_approvals']}."
        ).strip(),
    })
    return _save(request)


def reject_request(approval_id: str, *, reviewed_by: str = "human", note: str = "") -> Optional[dict]:
    request = get_request(approval_id)
    if not request:
        return None
    if request.get("status") in TERMINAL_STATUSES:
        raise ValueError(f"cannot reject a {request.get('status')} request")
    request["status"] = "rejected"
    request["reviewed_by"] = (reviewed_by or "human")[:120]
    request["reviewed_at"] = _now()
    request["review_note"] = (note or "Rejected by human reviewer.")[:1200]
    request.setdefault("audit", []).append({
        "at": request["reviewed_at"],
        "actor": request["reviewed_by"],
        "action": "rejected",
        "note": request["review_note"],
    })
    return _save(request)


def confirm_execution(
    approval_id: str,
    *,
    confirmed_by: str = "human",
    confirmation_phrase: str = "",
    note: str = "",
) -> Optional[dict]:
    request = get_request(approval_id)
    if not request:
        return None
    if request.get("status") not in {"pending", "approved"}:
        raise PermissionError("only pending or approved requests can receive execution confirmation")
    packet = policy_review_packet(request)
    if packet.get("verdict") == "handoff_required":
        raise PermissionError("this action must be handed off to the user")
    if (confirmation_phrase or "").strip() != packet["confirmation_phrase"]:
        raise PermissionError("confirmation phrase does not match the current approval evidence")
    now = _now()
    request["execution_confirmation"] = {
        "confirmed_by": (confirmed_by or "human")[:120],
        "confirmed_at": now,
        "note": (note or "Execution confirmed by human reviewer.")[:1200],
        "evidence_hash": packet["evidence_hash"],
        "confirmation_phrase": packet["confirmation_phrase"],
    }
    request.setdefault("audit", []).append({
        "at": now,
        "actor": request["execution_confirmation"]["confirmed_by"],
        "action": "execution_confirmed",
        "note": request["execution_confirmation"]["note"],
    })
    return _save(request)


def execute_request(
    approval_id: str,
    *,
    executed_by: str = "genesis",
    grant_ttl_minutes: int = 60,
    grant_max_uses: int = 10,
    require_confirmation: bool = False,
) -> Optional[dict]:
    request = get_request(approval_id)
    if not request:
        return None
    if request.get("status") != "approved":
        raise PermissionError("approval request must be approved before execution")
    controls = _approval_controls(request)
    if not controls.get("quorum_satisfied"):
        raise PermissionError("approval quorum is not satisfied")
    packet = policy_review_packet(request)
    if packet.get("verdict") == "handoff_required":
        raise PermissionError("this action must be handed off to the user")
    if require_confirmation:
        confirmation = request.get("execution_confirmation") or {}
        if confirmation.get("evidence_hash") != packet["evidence_hash"]:
            raise PermissionError("strict execution confirmation is required before execution")

    grant = issue_grant(
        request,
        issued_by=executed_by,
        ttl_minutes=grant_ttl_minutes,
        max_uses=grant_max_uses,
    )
    result = {
        "ok": True,
        "simulated": True,
        "executor_mode": "simulation_only",
        "action_type": request.get("action_type"),
        "permissions": request.get("permissions") or [],
        "permission_grant": grant,
        "policy_review": packet,
        "execution_confirmation": request.get("execution_confirmation"),
        "payload_preview": request.get("payload") or {},
        "message": "Execution is gated and simulated; a scoped permission grant was minted.",
    }
    request["status"] = "executed"
    request["execution_result"] = result
    request.setdefault("audit", []).append({
        "at": _now(),
        "actor": (executed_by or "genesis")[:120],
        "action": "executed",
        "note": result["message"],
    })
    return _save(request)


def break_glass_request(
    approval_id: str,
    *,
    invoked_by: str = "human",
    justification: str = "",
    grant_ttl_minutes: int = 15,
) -> Optional[dict]:
    request = get_request(approval_id)
    if not request:
        return None
    if request.get("status") in TERMINAL_STATUSES:
        raise ValueError(f"cannot break-glass a {request.get('status')} request")
    if request.get("risk_level") not in BREAK_GLASS_RISKS:
        raise PermissionError("break-glass is only available for high or critical requests")
    justification = (justification or "").strip()
    if len(justification) < 20:
        raise ValueError("break-glass justification must be at least 20 characters")
    packet = policy_review_packet(request)
    if packet.get("verdict") == "handoff_required":
        raise PermissionError("handoff-required requests cannot use break-glass")
    now = _now()
    break_glass = {
        "active": True,
        "version": "module-13-v1",
        "invoked_by": (invoked_by or "human")[:120],
        "invoked_at": now,
        "justification": justification[:1200],
        "controls_overridden": request.get("approval_controls") or {},
        "ttl_minutes": max(1, min(int(grant_ttl_minutes), 15)),
        "max_uses": 1,
    }
    grant = issue_grant(
        request,
        issued_by=break_glass["invoked_by"],
        ttl_minutes=break_glass["ttl_minutes"],
        max_uses=1,
        break_glass=break_glass,
    )
    result = {
        "ok": True,
        "simulated": True,
        "executor_mode": "simulation_only",
        "action_type": request.get("action_type"),
        "permissions": request.get("permissions") or [],
        "permission_grant": grant,
        "policy_review": packet,
        "break_glass": break_glass,
        "message": "Emergency break-glass grant minted with one use and a maximum 15 minute TTL.",
    }
    request["status"] = "break_glass"
    request["execution_result"] = result
    request.setdefault("audit", []).append({
        "at": now,
        "actor": break_glass["invoked_by"],
        "action": "break_glass",
        "note": result["message"],
    })
    _approval_controls(request)
    return _save(request)


def revoke_grant(grant_id: str, *, revoked_by: str = "human", note: str = "") -> Optional[dict]:
    grant = get_grant(grant_id)
    if not grant:
        return None
    if grant.get("status") in {"revoked", "expired", "exhausted"}:
        return grant
    grant["status"] = "revoked"
    grant.setdefault("audit", []).append({
        "at": _now(),
        "actor": (revoked_by or "human")[:120],
        "action": "revoked",
        "note": (note or "Permission grant revoked.")[:1200],
    })
    return _save_grant(grant)


def validate_grant(
    grant_id: str,
    *,
    permission: str,
    action_type: str | None = None,
    scope: str | None = None,
    consume: bool = False,
    actor: str = "genesis",
) -> dict:
    grant = get_grant(grant_id)
    if not grant:
        return {"ok": False, "reason": "grant_not_found", "grant": None}
    if grant.get("status") != "active":
        return {"ok": False, "reason": f"grant_{grant.get('status')}", "grant": grant}
    if permission not in set(grant.get("permissions") or []):
        return {"ok": False, "reason": "permission_not_granted", "grant": grant}
    if action_type and grant.get("action_type") != action_type:
        return {"ok": False, "reason": "action_type_mismatch", "grant": grant}
    grant_scope = grant.get("scope") or "*"
    if scope and grant_scope not in {"*", scope}:
        return {"ok": False, "reason": "scope_mismatch", "grant": grant}

    if consume:
        grant["uses"] = int(grant.get("uses", 0)) + 1
        grant.setdefault("audit", []).append({
            "at": _now(),
            "actor": (actor or "genesis")[:120],
            "action": "consumed",
            "note": f"Consumed permission {permission}.",
        })
        grant = _save_grant(grant)
        grant = _refresh_grant(grant)
    return {"ok": True, "reason": "allowed", "grant": grant}


def simulate_protected_action(
    *,
    grant_id: str,
    permission: str,
    action_type: str,
    scope: str,
    actor: str = "genesis",
    payload: Optional[dict] = None,
) -> dict:
    check = validate_grant(
        grant_id,
        permission=permission,
        action_type=action_type,
        scope=scope,
        consume=True,
        actor=actor,
    )
    if not check["ok"]:
        return {
            "ok": False,
            "blocked": True,
            "reason": check["reason"],
            "grant": check["grant"],
            "message": "Protected action blocked by Module 8 permission gate.",
        }
    return {
        "ok": True,
        "blocked": False,
        "simulated": True,
        "permission": permission,
        "action_type": action_type,
        "scope": scope,
        "actor": actor,
        "payload_preview": payload or {},
        "grant": check["grant"],
        "message": "Protected action passed Module 8 permission validation; no external side effect was performed.",
    }


def summary() -> dict:
    requests = list_requests(limit=200)
    grants = list_grants(limit=200)
    counts = {}
    for request in requests:
        counts[request.get("status", "unknown")] = counts.get(request.get("status", "unknown"), 0) + 1
    grant_counts = {}
    for grant in grants:
        grant_counts[grant.get("status", "unknown")] = grant_counts.get(grant.get("status", "unknown"), 0) + 1
    return {
        "total": len(requests),
        "pending": counts.get("pending", 0),
        "approved": counts.get("approved", 0),
        "executed": counts.get("executed", 0),
        "rejected": counts.get("rejected", 0),
        "expired": counts.get("expired", 0),
        "grants": {
            "total": len(grants),
            "active": grant_counts.get("active", 0),
            "revoked": grant_counts.get("revoked", 0),
            "expired": grant_counts.get("expired", 0),
            "exhausted": grant_counts.get("exhausted", 0),
        },
        "executor_mode": "simulation_only",
        "known_permissions": sorted(KNOWN_PERMISSIONS),
        "policy": {
            "handoff_required_permissions": sorted(HANDOFF_REQUIRED_PERMISSIONS),
            "strict_confirmation_permissions": sorted(STRICT_CONFIRMATION_PERMISSIONS),
        },
        "governance": {
            "version": "module-13-v1",
            "default_quorum": DEFAULT_APPROVAL_QUORUM,
            "break_glass_risks": sorted(BREAK_GLASS_RISKS),
            "break_glass_max_ttl_minutes": 15,
            "break_glass_max_uses": 1,
        },
        "integrity": integrity_report(limit=200)["summary"],
    }
