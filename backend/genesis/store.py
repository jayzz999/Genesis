"""Persistence for organisms + their causal graphs.

Each organism gets a folder under organisms/{id}/:
  - organism.json        — the Organism object
  - decisions/*.json     — one file per Decision, named by id
  - branches/*.json      — counterfactual branches

Plain JSON for now. Trivially upgradeable to SQLite/Postgres later when we
need queries beyond 'load all by organism_id'.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator, Optional

from .types import CounterfactualBranch, Decision, MetaDecision, Organism, OrganismMessage

_BASE = Path(os.getenv("GENESIS_STORAGE", "organisms")).resolve()


def _organism_dir(organism_id: str) -> Path:
    d = _BASE / organism_id
    (d / "decisions").mkdir(parents=True, exist_ok=True)
    (d / "branches").mkdir(parents=True, exist_ok=True)
    (d / "meta_decisions").mkdir(parents=True, exist_ok=True)
    (d / "messages").mkdir(parents=True, exist_ok=True)
    return d


# ── Organism ───────────────────────────────────────────────────────────

def save_organism(org: Organism) -> None:
    p = _organism_dir(org.id) / "organism.json"
    p.write_text(org.model_dump_json(indent=2))


def load_organism(organism_id: str) -> Optional[Organism]:
    p = _BASE / organism_id / "organism.json"
    if not p.exists():
        return None
    return Organism.model_validate_json(p.read_text())


def list_organisms() -> list[Organism]:
    if not _BASE.exists():
        return []
    out = []
    for child in _BASE.iterdir():
        if child.is_dir():
            org = load_organism(child.name)
            if org:
                out.append(org)
    return sorted(out, key=lambda o: o.born_at, reverse=True)


# ── Decisions ──────────────────────────────────────────────────────────

def save_decision(d: Decision) -> None:
    p = _organism_dir(d.organism_id) / "decisions" / f"{d.id}.json"
    p.write_text(d.model_dump_json(indent=2))


def load_decision(organism_id: str, decision_id: str) -> Optional[Decision]:
    p = _BASE / organism_id / "decisions" / f"{decision_id}.json"
    if not p.exists():
        return None
    return Decision.model_validate_json(p.read_text())


def iter_decisions(
    organism_id: str,
    include_dreams: bool = True,
    include_shadows: bool = False,
) -> Iterator[Decision]:
    d = _BASE / organism_id / "decisions"
    if not d.exists():
        return
    for f in sorted(d.glob("*.json")):
        try:
            dec = Decision.model_validate_json(f.read_text())
        except Exception:
            continue
        if not include_dreams and dec.is_dream:
            continue
        if not include_shadows and dec.shadow_branch:
            continue
        yield dec


def all_decisions(organism_id: str, **kw) -> list[Decision]:
    return sorted(
        iter_decisions(organism_id, **kw),
        key=lambda d: d.timestamp,
    )


# ── Branches (counterfactual timelines) ────────────────────────────────

def save_branch(b: CounterfactualBranch) -> None:
    p = _organism_dir(b.organism_id) / "branches" / f"{b.id}.json"
    p.write_text(b.model_dump_json(indent=2))


def load_branch(organism_id: str, branch_id: str) -> Optional[CounterfactualBranch]:
    p = _BASE / organism_id / "branches" / f"{branch_id}.json"
    if not p.exists():
        return None
    return CounterfactualBranch.model_validate_json(p.read_text())


def list_branches(organism_id: str) -> list[CounterfactualBranch]:
    d = _BASE / organism_id / "branches"
    if not d.exists():
        return []
    out = []
    for f in d.glob("*.json"):
        try:
            out.append(CounterfactualBranch.model_validate_json(f.read_text()))
        except Exception:
            continue
    return sorted(out, key=lambda b: b.created_at, reverse=True)


# ── Meta-Decisions (Phase 5A — metacognitive reflections) ─────────────

def save_meta_decision(md: MetaDecision) -> None:
    p = _organism_dir(md.organism_id) / "meta_decisions" / f"{md.id}.json"
    p.write_text(md.model_dump_json(indent=2))


def load_meta_decision(organism_id: str, meta_decision_id: str) -> Optional[MetaDecision]:
    p = _BASE / organism_id / "meta_decisions" / f"{meta_decision_id}.json"
    if not p.exists():
        return None
    return MetaDecision.model_validate_json(p.read_text())


def load_meta_decisions(organism_id: str, *, limit: int = 20) -> list[MetaDecision]:
    """Load the most recent N meta-decisions for an organism."""
    d = _BASE / organism_id / "meta_decisions"
    if not d.exists():
        return []
    out = []
    for f in d.glob("md_*.json"):
        try:
            out.append(MetaDecision.model_validate_json(f.read_text()))
        except Exception:
            continue
    out.sort(key=lambda m: m.timestamp, reverse=True)
    return out[:limit]


# ── Messages (Phase 5C — Society) ──────────────────────────────────────

def save_message(msg: OrganismMessage) -> None:
    # Save into the recipient's inbox, or a global broadcast inbox?
    # Here we save it into the recipient's dir if directed.
    # Broadcasts (recipient_id=None) are handled differently in society.py.
    # Let's save it directly to the intended organism_id we pass.
    # We will pass the organism_id explicitly or save it based on recipient.
    # Let's add a `save_message_for` function.
    pass

def save_message_for(organism_id: str, msg: OrganismMessage) -> None:
    p = _organism_dir(organism_id) / "messages" / f"{msg.id}.json"
    p.write_text(msg.model_dump_json(indent=2))

def load_messages(organism_id: str, *, unread_only: bool = False) -> list[OrganismMessage]:
    """Load messages for an organism."""
    d = _BASE / organism_id / "messages"
    if not d.exists():
        return []
    out = []
    for f in d.glob("msg_*.json"):
        try:
            msg = OrganismMessage.model_validate_json(f.read_text())
            if unread_only and msg.read:
                continue
            out.append(msg)
        except Exception:
            continue
    out.sort(key=lambda m: m.timestamp)
    return out
