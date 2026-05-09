"""World model and mission learning loop for Genesis."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from . import capabilities, reliability

_BASE = Path(os.getenv("GENESIS_WORLD_MODEL_STORAGE", "world_model")).resolve()


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


def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return value[:48] or "item"


def upsert_entity(*, name: str, entity_type: str = "concept", attributes: Optional[dict] = None) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    entity = {
        "id": f"entity_{_slug(name)}_{uuid4().hex[:8]}",
        "version": "world-entity-v1",
        "name": name[:180],
        "type": (entity_type or "concept")[:80],
        "attributes": attributes or {},
        "created_at": _now(),
    }
    entity["entity_hash"] = _hash(entity)
    return _save("entities", entity)


def record_belief(*, subject: str, claim: str, confidence: float = 0.5, evidence_ids: Optional[list[str]] = None) -> dict:
    if not (claim or "").strip():
        raise ValueError("claim is required")
    confidence = max(0.0, min(float(confidence), 1.0))
    belief = {
        "id": f"belief_{uuid4().hex[:12]}",
        "version": "world-belief-v1",
        "subject": (subject or "general")[:180],
        "claim": claim[:1200],
        "confidence": confidence,
        "evidence_ids": evidence_ids or [],
        "status": "supported" if confidence >= 0.7 else "uncertain",
        "created_at": _now(),
    }
    belief["belief_hash"] = _hash(belief)
    return _save("beliefs", belief)


def attach_evidence(*, source: str, summary: str, kind: str = "observation", payload: Optional[dict] = None) -> dict:
    if not (summary or "").strip():
        raise ValueError("summary is required")
    evidence = {
        "id": f"evidence_{uuid4().hex[:12]}",
        "version": "world-evidence-v1",
        "source": (source or "local")[:180],
        "kind": (kind or "observation")[:80],
        "summary": summary[:1200],
        "payload": payload or {},
        "created_at": _now(),
    }
    evidence["evidence_hash"] = _hash(evidence)
    return _save("evidence", evidence)


def review_mission(*, mission: dict, outcome: str = "planned", notes: Optional[list[str]] = None) -> dict:
    goal = mission.get("goal", "")
    mission_id = mission.get("id", f"mission_{uuid4().hex[:8]}")
    evidence = attach_evidence(
        source=mission_id,
        kind="mission_review",
        summary=f"Mission {outcome}: {goal}",
        payload={"mission_hash": mission.get("mission_hash"), "status": mission.get("status")},
    )
    belief = record_belief(
        subject=mission_id,
        claim="Mission planning quality improves when constraints and approval strategy are explicit.",
        confidence=0.82,
        evidence_ids=[evidence["id"]],
    )
    lesson = {
        "id": f"lesson_{uuid4().hex[:12]}",
        "version": "mission-lesson-v1",
        "mission_id": mission_id,
        "goal": goal[:1200],
        "outcome": outcome[:80],
        "notes": [str(note)[:300] for note in (notes or ["capture constraints before execution", "verify before reporting completion"])],
        "belief_id": belief["id"],
        "evidence_id": evidence["id"],
        "created_at": _now(),
    }
    lesson["lesson_hash"] = _hash(lesson)
    return _save("lessons", lesson)


def suggest_skill(*, lesson: dict, name: str = "") -> dict:
    skill_name = name or f"Reusable workflow for {lesson.get('outcome', 'mission')} missions"
    workflow = [
        "Clarify goal and constraints",
        "Create task graph",
        "Check approval boundaries",
        "Run verification",
        "Record lesson and evidence",
    ]
    compiled = capabilities.compile_skill_v2(name=skill_name, workflow=workflow)
    suggestion = {
        "id": f"skill_suggestion_{uuid4().hex[:12]}",
        "version": "skill-suggestion-v1",
        "lesson_id": lesson["id"],
        "name": skill_name[:180],
        "workflow": workflow,
        "compiled_skill": compiled,
        "status": "suggested",
        "created_at": _now(),
    }
    suggestion["suggestion_hash"] = _hash(suggestion)
    return _save("skill_suggestions", suggestion)


def build_world_snapshot() -> dict:
    entities = _list("entities", "entity", limit=20)
    beliefs = _list("beliefs", "belief", limit=20)
    evidence = _list("evidence", "evidence", limit=20)
    lessons = _list("lessons", "lesson", limit=20)
    suggestions = _list("skill_suggestions", "skill_suggestion", limit=20)
    snapshot = {
        "id": f"world_{uuid4().hex[:12]}",
        "version": "world-model-v1",
        "summary": {
            "entities": len(entities),
            "beliefs": len(beliefs),
            "evidence": len(evidence),
            "lessons": len(lessons),
            "skill_suggestions": len(suggestions),
        },
        "entities": entities[:5],
        "beliefs": beliefs[:5],
        "evidence": evidence[:5],
        "lessons": lessons[:5],
        "skill_suggestions": suggestions[:5],
        "created_at": _now(),
    }
    snapshot["snapshot_hash"] = _hash(snapshot)
    return _save("snapshots", snapshot)


def world_status() -> dict:
    return {
        "version": "world-learning-v1",
        "modules": {
            "entities": "typed objects and concepts",
            "beliefs": "claims with confidence and evidence links",
            "evidence": "mission-grounded observations",
            "lessons": "mission outcome reviews",
            "skill_suggestions": "reusable workflows distilled from lessons",
        },
        "latest_snapshot": _list("snapshots", "world", limit=1)[0] if _list("snapshots", "world", limit=1) else None,
        "latest_lessons": _list("lessons", "lesson", limit=5),
        "latest_suggestions": _list("skill_suggestions", "skill_suggestion", limit=5),
    }


def run_learning_drill(*, goal: str = "Improve Genesis mission planning through grounded learning.") -> dict:
    mission = reliability.mission_runner(
        goal=goal,
        constraints=["no external side effects without approval", "record evidence and lessons"],
    )
    entity = upsert_entity(
        name="Genesis mission planning",
        entity_type="capability",
        attributes={"mission_id": mission["id"], "status": mission["status"]},
    )
    evidence = attach_evidence(
        source=mission["id"],
        summary="Mission was planned with explicit constraints, task graph, and goal contract.",
        kind="mission_artifact",
        payload={"task_graph_id": mission["task_graph"]["id"]},
    )
    belief = record_belief(
        subject=entity["id"],
        claim="Explicit constraints reduce unsafe autonomous execution risk.",
        confidence=0.86,
        evidence_ids=[evidence["id"]],
    )
    lesson = review_mission(
        mission=mission,
        outcome="planned",
        notes=["use mission brief before execution", "promote reusable planning workflow"],
    )
    suggestion = suggest_skill(lesson=lesson, name="Approval-aware mission planning")
    snapshot = build_world_snapshot()
    return {
        "version": "world-learning-v1",
        "mission": mission,
        "entity": entity,
        "evidence": evidence,
        "belief": belief,
        "lesson": lesson,
        "skill_suggestion": suggestion,
        "snapshot": snapshot,
    }
