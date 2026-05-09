#!/usr/bin/env python3
"""Operational maintenance for Genesis production stores.

Examples:
  python scripts/genesis_maintenance.py status
  python scripts/genesis_maintenance.py snapshot --out backups/pre-demo
  python scripts/genesis_maintenance.py reset --confirm RESET
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORE_ENVS = {
    "organisms": "GENESIS_STORAGE",
    "populations": "GENESIS_POPULATION_STORAGE",
    "memories": "GENESIS_MEMORY_STORAGE",
    "tool_runs": "GENESIS_TOOL_SANDBOX_STORAGE",
    "collaborations": "GENESIS_COLLAB_STORAGE",
    "improvements": "GENESIS_IMPROVEMENT_STORAGE",
    "operators": "GENESIS_OPERATOR_STORAGE",
    "approvals": "GENESIS_APPROVAL_STORAGE",
    "connectors": "GENESIS_CONNECTOR_STORAGE",
    "governance": "GENESIS_GOVERNANCE_STORAGE",
    "capabilities": "GENESIS_CAPABILITY_STORAGE",
    "intelligence": "GENESIS_INTELLIGENCE_STORAGE",
    "reliability": "GENESIS_RELIABILITY_STORAGE",
    "world_model": "GENESIS_WORLD_MODEL_STORAGE",
    "living_systems": "GENESIS_LIVING_SYSTEMS_STORAGE",
    "nervous_system": "GENESIS_NERVOUS_SYSTEM_STORAGE",
}


def _store_paths() -> dict[str, Path]:
    return {
        name: Path(os.getenv(env, ROOT / name)).resolve()
        for name, env in STORE_ENVS.items()
    }


def _database_path() -> Path:
    url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./genesis.db")
    if url.startswith("sqlite+aiosqlite:///"):
        return Path(url.removeprefix("sqlite+aiosqlite:///")).resolve()
    if url.startswith("sqlite:///"):
        return Path(url.removeprefix("sqlite:///")).resolve()
    return ROOT / "genesis.db"


def _count_json(path: Path, pattern: str) -> int:
    return sum(1 for _ in path.glob(pattern)) if path.exists() else 0


def status() -> dict:
    paths = _store_paths()
    organisms = paths["organisms"]
    populations = paths["populations"]
    organism_dirs = [p for p in organisms.iterdir() if p.is_dir()] if organisms.exists() else []
    population_dirs = [p for p in populations.iterdir() if p.is_dir()] if populations.exists() else []
    return {
        "database_path": str(_database_path()),
        "stores": {name: str(path) for name, path in paths.items()},
        "organisms": len(organism_dirs),
        "decisions": sum(_count_json(p / "decisions", "*.json") for p in organism_dirs),
        "meta_decisions": sum(_count_json(p / "meta_decisions", "*.json") for p in organism_dirs),
        "population_runs": sum(1 for p in population_dirs if (p / "run.json").exists()),
        "json_records": {
            name: _count_json(path, "**/*.json")
            for name, path in paths.items()
        },
    }


def snapshot(out: Path) -> dict:
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    target = out / f"genesis-snapshot-{stamp}"
    target.mkdir(parents=True, exist_ok=False)
    for name, path in _store_paths().items():
        if path.exists():
            shutil.copytree(path, target / name)
    db = _database_path()
    for db_path in (db, Path(str(db) + "-wal"), Path(str(db) + "-shm")):
        if db_path.exists():
            shutil.copy2(db_path, target / db_path.name)
    report = status()
    report["snapshot_path"] = str(target)
    (target / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def reset(confirm: str) -> dict:
    if confirm != "RESET":
        raise SystemExit("Refusing reset without --confirm RESET")
    before = status()
    for path in _store_paths().values():
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    return {"before": before, "after": status()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintain Genesis local data stores.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    snapshot_parser = sub.add_parser("snapshot")
    snapshot_parser.add_argument("--out", type=Path, default=ROOT / "backups")
    reset_parser = sub.add_parser("reset")
    reset_parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    if args.command == "status":
        result = status()
    elif args.command == "snapshot":
        result = snapshot(args.out)
    else:
        result = reset(args.confirm)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
