"""Persistence for organisms + their causal graphs.

Each organism gets a folder under organisms/{id}/:
  - organism.json        — the Organism object
  - decisions/*.json     — one file per Decision, named by id
  - branches/*.json      — counterfactual branches

JSON remains authoritative for runtime organism bodies. In hosted deployments
the long-term database can rehydrate the temporary JSON runtime store after a
restart, then JSON resumes as the hot runtime source.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Iterator, Optional

from .types import CounterfactualBranch, Decision, MetaDecision, Organism, OrganismMessage

logger = logging.getLogger("genesis.store")

_BASE = Path(os.getenv("GENESIS_STORAGE", "organisms")).resolve()


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
    _atomic_write_text(p, org.model_dump_json(indent=2))
    try:
        from . import long_term
        long_term.upsert_organism(org)
    except Exception as e:
        logger.warning("failed to mirror organism %s into long-term database: %s", org.id, e)


def load_organism(organism_id: str) -> Optional[Organism]:
    p = _BASE / organism_id / "organism.json"
    if p.exists():
        try:
            return Organism.model_validate_json(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("failed to load organism %s from %s: %s", organism_id, p, e)
            return None
    return _load_organism_from_long_term(organism_id)


def list_organisms() -> list[Organism]:
    out = []
    seen = set()
    if _BASE.exists():
        for child in _BASE.iterdir():
            if child.is_dir():
                org = load_organism(child.name)
                if org:
                    seen.add(org.id)
                    out.append(org)
    for org in _list_organisms_from_long_term():
        if org.id not in seen:
            seen.add(org.id)
            out.append(org)
    return sorted(out, key=lambda o: o.born_at, reverse=True)


def _load_organism_from_long_term(organism_id: str) -> Optional[Organism]:
    try:
        from . import long_term
        payload = long_term.get_organism_payload(organism_id)
        if not payload:
            return None
        org = Organism.model_validate(payload)
        _atomic_write_text(_organism_dir(org.id) / "organism.json", org.model_dump_json(indent=2))
        _hydrate_decisions_from_long_term(org.id)
        return org
    except Exception as e:
        logger.debug("failed to hydrate organism %s from long-term database: %s", organism_id, e)
        return None


def _list_organisms_from_long_term() -> list[Organism]:
    try:
        from . import long_term
        organisms = []
        for payload in long_term.list_organism_payloads():
            try:
                org = Organism.model_validate(payload)
            except Exception as e:
                logger.warning("failed to parse long-term organism mirror: %s", e)
                continue
            _atomic_write_text(_organism_dir(org.id) / "organism.json", org.model_dump_json(indent=2))
            _hydrate_decisions_from_long_term(org.id)
            organisms.append(org)
        return organisms
    except Exception as e:
        logger.debug("failed to list organisms from long-term database: %s", e)
        return []


def _hydrate_decisions_from_long_term(organism_id: str) -> int:
    try:
        from . import long_term
        count = 0
        for payload in long_term.list_decision_payloads(organism_id):
            try:
                decision = Decision.model_validate(payload)
            except Exception as e:
                logger.warning("failed to parse long-term decision mirror for %s: %s", organism_id, e)
                continue
            p = _organism_dir(organism_id) / "decisions" / f"{decision.id}.json"
            if not p.exists():
                _atomic_write_text(p, decision.model_dump_json(indent=2))
                count += 1
        return count
    except Exception as e:
        logger.debug("failed to hydrate decisions for %s from long-term database: %s", organism_id, e)
        return 0


def reconcile_long_term(*, repair: bool = False) -> dict:
    """Compare the JSON source of truth with the long-term database mirror.

    JSON remains authoritative for now because runtime loading and decision graph
    traversal still depend on the filesystem store. With repair=True, missing
    database mirror rows are recreated from JSON.
    """
    organisms = list_organisms()
    decisions = []
    for org in organisms:
        decisions.extend(all_decisions(org.id))

    report = {
        "version": "genesis-json-authoritative-reconciliation-v1",
        "authority": "json_store",
        "repair": repair,
        "json": {
            "organisms": len(organisms),
            "decisions": len(decisions),
        },
        "database": {
            "engine": None,
            "connected": False,
            "organisms": 0,
            "decisions": 0,
        },
        "sqlite": {
            "connected": False,
            "organisms": 0,
            "decisions": 0,
        },
        "missing_in_database": {
            "organisms": [],
            "decisions": [],
        },
        "missing_in_sqlite": {
            "organisms": [],
            "decisions": [],
        },
        "repaired": {
            "organisms": 0,
            "decisions": 0,
        },
        "summary": {
            "missing_total": 0,
            "repaired_total": 0,
        },
        "ok": False,
    }
    try:
        from . import long_term
        status = long_term.status()
        tables = status.get("database", {}).get("tables", {})
        database_report = {
            "engine": status.get("database", {}).get("engine"),
            "connected": bool(status.get("database", {}).get("connected")),
            "organisms": int(tables.get("organism_records", 0)),
            "decisions": int(tables.get("decision_records", 0)),
        }
        report["database"] = database_report
        report["sqlite"] = {
            "connected": database_report["connected"],
            "organisms": database_report["organisms"],
            "decisions": database_report["decisions"],
        }
        conn = long_term._connect()  # noqa: SLF001 - intentional reconciliation boundary.
        organism_rows = {
            row["id"]
            for row in conn.execute("SELECT id FROM organism_records").fetchall()
        }
        decision_rows = {
            row["id"]
            for row in conn.execute("SELECT id FROM decision_records").fetchall()
        }
        missing_orgs = [org for org in organisms if org.id not in organism_rows]
        missing_decisions = [d for d in decisions if d.id not in decision_rows]
        missing_report = {
            "organisms": [org.id for org in missing_orgs],
            "decisions": [d.id for d in missing_decisions],
        }
        report["missing_in_database"] = missing_report
        report["missing_in_sqlite"] = missing_report
        report["summary"]["missing_total"] = len(missing_orgs) + len(missing_decisions)
        if repair:
            for org in missing_orgs:
                long_term.upsert_organism(org)
                report["repaired"]["organisms"] += 1
            for decision in missing_decisions:
                long_term.upsert_decision(decision)
                report["repaired"]["decisions"] += 1
            status = long_term.status()
            tables = status.get("database", {}).get("tables", {})
            report["database"]["engine"] = status.get("database", {}).get("engine")
            report["database"]["connected"] = bool(status.get("database", {}).get("connected"))
            report["database"]["organisms"] = int(tables.get("organism_records", 0))
            report["database"]["decisions"] = int(tables.get("decision_records", 0))
            report["sqlite"]["organisms"] = report["database"]["organisms"]
            report["sqlite"]["decisions"] = report["database"]["decisions"]
            report["missing_in_database"] = {"organisms": [], "decisions": []}
            report["missing_in_sqlite"] = {"organisms": [], "decisions": []}
            report["summary"]["missing_total"] = 0
            report["summary"]["repaired_total"] = report["repaired"]["organisms"] + report["repaired"]["decisions"]
        report["ok"] = not report["missing_in_database"]["organisms"] and not report["missing_in_database"]["decisions"]
    except Exception as e:
        report["error"] = str(e)
    return report


# ── Decisions ──────────────────────────────────────────────────────────

def save_decision(d: Decision) -> None:
    p = _organism_dir(d.organism_id) / "decisions" / f"{d.id}.json"
    _atomic_write_text(p, d.model_dump_json(indent=2))
    try:
        from . import long_term
        long_term.upsert_decision(d)
    except Exception as e:
        logger.warning("failed to mirror decision %s into long-term database: %s", d.id, e)


def load_decision(organism_id: str, decision_id: str) -> Optional[Decision]:
    p = _BASE / organism_id / "decisions" / f"{decision_id}.json"
    if not p.exists():
        return None
    try:
        return Decision.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("failed to load decision %s/%s: %s", organism_id, decision_id, e)
        return None


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


def load_decisions(organism_id: str, **kw) -> list[Decision]:
    """Compatibility alias for callers that expect a load_* helper."""
    return all_decisions(organism_id, **kw)


# ── Branches (counterfactual timelines) ────────────────────────────────

def save_branch(b: CounterfactualBranch) -> None:
    p = _organism_dir(b.organism_id) / "branches" / f"{b.id}.json"
    _atomic_write_text(p, b.model_dump_json(indent=2))


def load_branch(organism_id: str, branch_id: str) -> Optional[CounterfactualBranch]:
    p = _BASE / organism_id / "branches" / f"{branch_id}.json"
    if not p.exists():
        return None
    try:
        return CounterfactualBranch.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("failed to load branch %s/%s: %s", organism_id, branch_id, e)
        return None


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
    _atomic_write_text(p, md.model_dump_json(indent=2))


def load_meta_decision(organism_id: str, meta_decision_id: str) -> Optional[MetaDecision]:
    p = _BASE / organism_id / "meta_decisions" / f"{meta_decision_id}.json"
    if not p.exists():
        return None
    try:
        return MetaDecision.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("failed to load meta-decision %s/%s: %s", organism_id, meta_decision_id, e)
        return None


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
    _atomic_write_text(p, msg.model_dump_json(indent=2))

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
