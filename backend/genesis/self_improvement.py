"""Module 5 — self-improvement with strict evaluation gates.

Genesis can now propose improvements to itself, but promotion is gated by
deterministic evidence checks. This module deliberately separates "candidate
idea" from "approved to promote"; no candidate passes unless every required
gate passes.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional
from uuid import uuid4

from backend.shared.gemini_client import generate_text

from . import memory

EventCallback = Callable[[str, dict], Awaitable[None]]

_BASE = Path(os.getenv("GENESIS_IMPROVEMENT_STORAGE", "improvements")).resolve()

DEFAULT_GATES = {
    "min_benchmark_delta": 0.02,
    "max_regression_risk": 0.25,
    "min_tests": 2,
    "min_confidence": 0.7,
    "required_checks": ["unit", "build", "browser"],
}

HIGH_RISK_TERMS = {
    "disable auth",
    "bypass",
    "ignore safety",
    "remove tests",
    "delete data",
    "exfiltrate",
    "secret",
    "password",
}


def _now() -> str:
    return datetime.utcnow().isoformat()


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


def _path(run_id: str) -> Path:
    return _BASE / f"{run_id}.json"


def _save(run: dict) -> dict:
    run["updated_at"] = _now()
    _atomic_write_text(_path(run["id"]), json.dumps(run, indent=2, default=str))
    return run


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


def _clamp01(value: object, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return default


def _text_has_high_risk(value: object) -> bool:
    text = json.dumps(value, default=str).lower()
    return any(term in text for term in HIGH_RISK_TERMS)


async def _propose_candidate(objective: str, context: dict) -> dict:
    prompt = json.dumps({
        "objective": objective,
        "context": context,
        "contract": {
            "title": "short name",
            "problem": "what capability gap this fixes",
            "hypothesis": "measurable self-improvement hypothesis",
            "change_summary": "what would change",
            "expected_metrics": {"benchmark_delta": "number", "latency_delta": "number"},
            "tests": ["concrete verification checks"],
            "rollback_plan": "how to reverse safely",
            "safety_notes": ["privacy/security/reliability notes"],
            "confidence": "number 0..1",
        },
    }, indent=2, default=str)
    raw = await generate_text(
        prompt=prompt,
        system="Genesis self-improvement proposer. Return strict JSON only.",
        temperature=0.2,
        max_tokens=1400,
    )
    data = _parse_json(raw)
    return {
        "title": str(data.get("title") or "Untitled self-improvement")[:160],
        "problem": str(data.get("problem") or "")[:1200],
        "hypothesis": str(data.get("hypothesis") or "")[:1200],
        "change_summary": str(data.get("change_summary") or data.get("summary") or raw)[:2000],
        "expected_metrics": data.get("expected_metrics") if isinstance(data.get("expected_metrics"), dict) else {},
        "tests": list(data.get("tests") or [])[:10],
        "rollback_plan": str(data.get("rollback_plan") or "")[:1200],
        "safety_notes": list(data.get("safety_notes") or [])[:10],
        "confidence": _clamp01(data.get("confidence"), 0.55),
    }


def _normalize_candidate(candidate: dict) -> dict:
    return {
        "title": str(candidate.get("title") or "Manual self-improvement candidate")[:160],
        "problem": str(candidate.get("problem") or "")[:1200],
        "hypothesis": str(candidate.get("hypothesis") or "")[:1200],
        "change_summary": str(candidate.get("change_summary") or candidate.get("summary") or "")[:2000],
        "expected_metrics": candidate.get("expected_metrics") if isinstance(candidate.get("expected_metrics"), dict) else {},
        "tests": list(candidate.get("tests") or [])[:10],
        "rollback_plan": str(candidate.get("rollback_plan") or "")[:1200],
        "safety_notes": list(candidate.get("safety_notes") or [])[:10],
        "confidence": _clamp01(candidate.get("confidence"), 0.55),
    }


def evaluate_candidate(candidate: dict, evidence: dict, gates: Optional[dict] = None) -> dict:
    rules = {**DEFAULT_GATES, **(gates or {})}
    checks = evidence.get("checks") if isinstance(evidence.get("checks"), dict) else {}
    benchmark_delta = float(evidence.get(
        "benchmark_delta",
        candidate.get("expected_metrics", {}).get("benchmark_delta", 0.0),
    ) or 0.0)
    regression_risk = _clamp01(evidence.get("regression_risk"), 1.0)
    confidence = _clamp01(evidence.get("confidence", candidate.get("confidence")), 0.0)
    tests = list(candidate.get("tests") or []) + list(evidence.get("tests") or [])

    gate_results = [
        {
            "id": "problem_framed",
            "label": "Problem is framed",
            "required": True,
            "passed": len(candidate.get("problem", "").strip()) >= 20,
            "detail": "Candidate must state the capability gap it is improving.",
        },
        {
            "id": "measurable_hypothesis",
            "label": "Hypothesis is measurable",
            "required": True,
            "passed": len(candidate.get("hypothesis", "").strip()) >= 20 and bool(candidate.get("expected_metrics")),
            "detail": "Candidate needs a hypothesis and expected metrics.",
        },
        {
            "id": "benchmark_delta",
            "label": "Benchmark evidence clears threshold",
            "required": True,
            "passed": benchmark_delta >= float(rules["min_benchmark_delta"]),
            "detail": f"Observed or expected benchmark delta {benchmark_delta:.3f}; required {float(rules['min_benchmark_delta']):.3f}.",
        },
        {
            "id": "regression_risk",
            "label": "Regression risk is bounded",
            "required": True,
            "passed": regression_risk <= float(rules["max_regression_risk"]),
            "detail": f"Regression risk {regression_risk:.2f}; maximum {float(rules['max_regression_risk']):.2f}.",
        },
        {
            "id": "verification",
            "label": "Verification checks passed",
            "required": True,
            "passed": (
                len(tests) >= int(rules["min_tests"])
                and all(bool(checks.get(name)) for name in rules["required_checks"])
            ),
            "detail": f"Requires {rules['required_checks']} and at least {rules['min_tests']} test descriptions.",
        },
        {
            "id": "safety_review",
            "label": "Safety review is clean",
            "required": True,
            "passed": bool(candidate.get("safety_notes")) and not _text_has_high_risk(candidate),
            "detail": "Safety notes are required and high-risk intents are blocked.",
        },
        {
            "id": "rollback",
            "label": "Rollback path exists",
            "required": True,
            "passed": len(candidate.get("rollback_plan", "").strip()) >= 20,
            "detail": "Promotion requires a concrete rollback plan.",
        },
        {
            "id": "confidence",
            "label": "Confidence clears threshold",
            "required": True,
            "passed": confidence >= float(rules["min_confidence"]),
            "detail": f"Confidence {confidence:.2f}; required {float(rules['min_confidence']):.2f}.",
        },
    ]
    required = [gate for gate in gate_results if gate["required"]]
    passed_required = [gate for gate in required if gate["passed"]]
    score = round(len(passed_required) / max(len(required), 1), 4)
    promotable = score == 1.0
    return {
        "rules": rules,
        "gates": gate_results,
        "score": score,
        "promotable": promotable,
        "verdict": "promotable" if promotable else "blocked",
        "blocked_by": [gate["id"] for gate in required if not gate["passed"]],
        "metrics": {
            "benchmark_delta": benchmark_delta,
            "regression_risk": regression_risk,
            "confidence": confidence,
            "checks": checks,
        },
    }


def list_runs(limit: int = 50) -> list[dict]:
    if not _BASE.exists():
        return []
    runs = []
    for path in _BASE.glob("improve_*.json"):
        run = get_run(path.stem)
        if run:
            runs.append(run)
    runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return runs[:limit]


def get_run(run_id: str) -> Optional[dict]:
    path = _path(run_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


async def run_improvement_cycle(
    *,
    objective: str,
    context: Optional[dict] = None,
    candidate: Optional[dict] = None,
    evidence: Optional[dict] = None,
    gates: Optional[dict] = None,
    event_callback: Optional[EventCallback] = None,
) -> dict:
    objective = (objective or "").strip()
    if not objective:
        raise ValueError("self-improvement objective is required")

    run = {
        "id": f"improve_{uuid4().hex[:12]}",
        "created_at": _now(),
        "updated_at": None,
        "objective": objective,
        "context": context or {},
        "status": "evaluating",
        "candidate": None,
        "evidence": evidence or {},
        "evaluation": None,
        "promotion": None,
        "error": None,
    }
    _save(run)
    if event_callback:
        await event_callback("self_improvement.started", {"run": _public_summary(run)})

    try:
        run["candidate"] = _normalize_candidate(candidate) if candidate else await _propose_candidate(objective, run["context"])
        _save(run)
        if event_callback:
            await event_callback("self_improvement.candidate_ready", {"run_id": run["id"], "candidate": run["candidate"]})

        run["evaluation"] = evaluate_candidate(run["candidate"], run["evidence"], gates)
        run["status"] = "complete"
        run["promotion"] = {
            "allowed": bool(run["evaluation"]["promotable"]),
            "state": "approved_for_experiment" if run["evaluation"]["promotable"] else "blocked",
            "reason": (
                "All strict gates passed."
                if run["evaluation"]["promotable"]
                else f"Blocked by: {', '.join(run['evaluation']['blocked_by'])}"
            ),
            "requires_human_review": True,
        }
        _save(run)
        memory.remember(
            (
                f"Module 5 self-improvement '{run['candidate']['title']}' "
                f"{run['promotion']['state']} with gate score {run['evaluation']['score']:.2f}."
            ),
            kind="self_improvement_result",
            scope="global",
            tags=["module-5", "self-improvement", run["promotion"]["state"]],
            source_run_id=run["id"],
            score=run["evaluation"]["score"],
        )
        if event_callback:
            await event_callback("self_improvement.completed", {"run": run})
        return run
    except Exception as exc:
        run["status"] = "error"
        run["error"] = str(exc)
        _save(run)
        if event_callback:
            await event_callback("self_improvement.failed", {"run": _public_summary(run), "error": str(exc)})
        return run


def _public_summary(run: dict) -> dict:
    evaluation = run.get("evaluation") or {}
    candidate = run.get("candidate") or {}
    promotion = run.get("promotion") or {}
    return {
        "id": run.get("id"),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "objective": run.get("objective"),
        "status": run.get("status"),
        "title": candidate.get("title"),
        "score": evaluation.get("score"),
        "verdict": evaluation.get("verdict"),
        "promotion_state": promotion.get("state"),
        "blocked_by": evaluation.get("blocked_by") or [],
        "error": run.get("error"),
    }
