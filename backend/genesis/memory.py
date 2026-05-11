"""Module 2 — durable memory and curriculum learning.

This layer sits above per-organism learned_patterns. It stores reusable
lessons, retrieves relevant memories before reasoning, and keeps a small
curriculum state for benchmark-driven training.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Optional

from .types import Decision, LongTermMemory, MetaDecision, Organism

_BASE = Path(os.getenv("GENESIS_MEMORY_STORAGE", "memories")).resolve()
_MEMORY_DIR = _BASE / "items"
_CURRICULUM_PATH = _BASE / "curriculum.json"


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


def _tokens(value: object) -> set[str]:
    text = json.dumps(value, default=str).lower() if not isinstance(value, str) else value.lower()
    return {
        token
        for token in re.findall(r"[a-z0-9_]{3,}", text)
        if token not in {"the", "and", "for", "with", "that", "this", "from", "into", "json"}
    }


def _memory_path(memory_id: str) -> Path:
    return _MEMORY_DIR / f"{memory_id}.json"


def save(item: LongTermMemory) -> LongTermMemory:
    item.updated_at = datetime.utcnow()
    _atomic_write_text(_memory_path(item.id), item.model_dump_json(indent=2))
    return item


def load(memory_id: str) -> Optional[LongTermMemory]:
    path = _memory_path(memory_id)
    if not path.exists():
        return None
    try:
        return LongTermMemory.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_memories(
    *,
    limit: int = 100,
    scope: Optional[str] = None,
    benchmark_id: Optional[str] = None,
) -> list[LongTermMemory]:
    if not _MEMORY_DIR.exists():
        return []
    items = []
    for path in _MEMORY_DIR.glob("mem_*.json"):
        item = load(path.stem)
        if not item:
            continue
        if scope and item.scope != scope:
            continue
        if benchmark_id and item.benchmark_id != benchmark_id:
            continue
        items.append(item)
    items.sort(key=lambda m: (m.score, m.updated_at), reverse=True)
    return items[:limit]


def remember(
    text: str,
    *,
    kind: str = "lesson",
    scope: str = "global",
    tags: Optional[list[str]] = None,
    organism_id: Optional[str] = None,
    benchmark_id: Optional[str] = None,
    source_decision_id: Optional[str] = None,
    source_meta_decision_id: Optional[str] = None,
    source_run_id: Optional[str] = None,
    score: float = 0.5,
) -> Optional[LongTermMemory]:
    text = (text or "").strip()
    if not text:
        return None

    normalized = " ".join(text.lower().split())
    for item in list_memories(limit=500, benchmark_id=benchmark_id):
        if " ".join(item.text.lower().split()) == normalized:
            item.score = max(item.score, score)
            item.tags = sorted(set(item.tags + (tags or [])))
            if organism_id and not item.organism_id:
                item.organism_id = organism_id
            if source_run_id and not item.source_run_id:
                item.source_run_id = source_run_id
            return save(item)

    return save(LongTermMemory(
        scope=scope,
        kind=kind,
        text=text[:1200],
        tags=sorted(set(tags or [])),
        organism_id=organism_id,
        benchmark_id=benchmark_id,
        source_decision_id=source_decision_id,
        source_meta_decision_id=source_meta_decision_id,
        source_run_id=source_run_id,
        score=max(0.0, min(1.0, score)),
    ))


def retrieve(
    organism: Organism,
    perception: dict,
    *,
    limit: int = 5,
) -> list[LongTermMemory]:
    query_tokens = _tokens({
        "goal": organism.intent.goal,
        "constraints": organism.intent.constraints,
        "perception": perception,
    })
    benchmark_id = perception.get("benchmark_id") if isinstance(perception, dict) else None
    candidates = list_memories(limit=500)
    scored = []
    for item in candidates:
        item_tokens = _tokens({"text": item.text, "tags": item.tags, "benchmark": item.benchmark_id})
        overlap = len(query_tokens & item_tokens)
        benchmark_bonus = 2 if benchmark_id and item.benchmark_id == benchmark_id else 0
        organism_bonus = 1 if item.organism_id == organism.id else 0
        relevance = overlap + benchmark_bonus + organism_bonus + item.score
        if relevance > 0:
            scored.append((relevance, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    selected = [item for _, item in scored[:limit]]
    for item in selected:
        item.use_count += 1
        item.last_used_at = datetime.utcnow()
        save(item)
    return selected


def write_from_remember_action(org: Organism, decision: Decision, pattern: str) -> Optional[LongTermMemory]:
    benchmark_id = decision.trigger.get("benchmark_id") if isinstance(decision.trigger, dict) else None
    return remember(
        pattern,
        kind="pattern",
        scope="benchmark" if benchmark_id else "global",
        tags=["remember", decision.trigger.get("type", "unknown")],
        organism_id=org.id,
        benchmark_id=benchmark_id,
        source_decision_id=decision.id,
        score=0.7,
    )


def write_from_meta(org: Organism, decision: Decision, meta: MetaDecision) -> Optional[LongTermMemory]:
    if meta.confidence < 0.65 or not meta.lesson:
        return None
    benchmark_id = decision.trigger.get("benchmark_id") if isinstance(decision.trigger, dict) else None
    score = mean([meta.confidence, meta.reasoning_quality, meta.action_efficiency])
    return remember(
        meta.lesson,
        kind="lesson",
        scope="benchmark" if benchmark_id else "global",
        tags=["meta", decision.trigger.get("type", "unknown")],
        organism_id=org.id,
        benchmark_id=benchmark_id,
        source_decision_id=decision.id,
        source_meta_decision_id=meta.id,
        score=round(score, 4),
    )


def _load_curriculum() -> dict:
    if not _CURRICULUM_PATH.exists():
        return {"benchmarks": {}, "updated_at": None, "recommended_next": None}
    try:
        return json.loads(_CURRICULUM_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"benchmarks": {}, "updated_at": None, "recommended_next": None}


def _save_curriculum(curriculum: dict) -> dict:
    curriculum["updated_at"] = datetime.utcnow().isoformat()
    _atomic_write_text(_CURRICULUM_PATH, json.dumps(curriculum, indent=2, default=str))
    return curriculum


def update_curriculum_from_run(run: dict) -> dict:
    benchmark_id = run.get("benchmark_id")
    if not benchmark_id:
        return _load_curriculum()
    generations = run.get("generations", [])
    best = max((g.get("best_fitness", 0.0) for g in generations), default=0.0)
    latest_mean = generations[-1].get("mean_fitness", 0.0) if generations else 0.0
    status = run.get("status")
    curriculum = _load_curriculum()
    entry = curriculum.setdefault("benchmarks", {}).setdefault(benchmark_id, {
        "attempts": 0,
        "best_fitness": 0.0,
        "latest_mean_fitness": 0.0,
        "mastery": 0.0,
        "last_run_id": None,
    })
    entry["attempts"] += 1 if status in {"complete", "stopped", "error"} else 0
    entry["best_fitness"] = max(entry.get("best_fitness", 0.0), best)
    entry["latest_mean_fitness"] = latest_mean
    entry["mastery"] = round((entry["best_fitness"] * 0.7) + (latest_mean * 0.3), 4)
    entry["last_run_id"] = run.get("id")
    entry["status"] = status

    recommended = None
    if curriculum["benchmarks"]:
        recommended = min(
            curriculum["benchmarks"].items(),
            key=lambda pair: (pair[1].get("mastery", 0.0), pair[1].get("attempts", 0)),
        )[0]
    curriculum["recommended_next"] = recommended

    remember(
        f"Benchmark {benchmark_id} reached best fitness {best:.2f} and latest mean {latest_mean:.2f}.",
        kind="benchmark_result",
        scope="benchmark",
        tags=["benchmark", status or "unknown"],
        benchmark_id=benchmark_id,
        source_run_id=run.get("id"),
        score=max(best, latest_mean, 0.1),
    )
    return _save_curriculum(curriculum)


def curriculum() -> dict:
    data = _load_curriculum()
    items = []
    for benchmark_id, entry in data.get("benchmarks", {}).items():
        items.append({
            "benchmark_id": benchmark_id,
            **entry,
            "weakness": round(1.0 - entry.get("mastery", 0.0), 4),
        })
    items.sort(key=lambda item: item["weakness"], reverse=True)
    return {
        **data,
        "items": items,
        "memory_count": len(list_memories(limit=10000)),
    }
