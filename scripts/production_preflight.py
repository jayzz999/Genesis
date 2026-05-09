#!/usr/bin/env python3
"""Production deployment preflight for Genesis.

Fails fast when environment, static assets, persistence, or health checks are
not deployment-ready. It does not contact external services.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR_ENV = [
    "GENESIS_STORAGE",
    "GENESIS_POPULATION_STORAGE",
    "GENESIS_MEMORY_STORAGE",
    "GENESIS_TOOL_SANDBOX_STORAGE",
    "GENESIS_COLLAB_STORAGE",
    "GENESIS_IMPROVEMENT_STORAGE",
    "GENESIS_OPERATOR_STORAGE",
    "GENESIS_APPROVAL_STORAGE",
    "GENESIS_CONNECTOR_STORAGE",
    "GENESIS_GOVERNANCE_STORAGE",
    "GENESIS_CAPABILITY_STORAGE",
    "GENESIS_INTELLIGENCE_STORAGE",
    "GENESIS_RELIABILITY_STORAGE",
    "GENESIS_WORLD_MODEL_STORAGE",
    "GENESIS_LIVING_SYSTEMS_STORAGE",
    "GENESIS_NERVOUS_SYSTEM_STORAGE",
]
RUNTIME_DEFAULTS = {
    "GENESIS_STORAGE": "organisms",
    "GENESIS_POPULATION_STORAGE": "populations",
    "GENESIS_MEMORY_STORAGE": "memories",
    "GENESIS_TOOL_SANDBOX_STORAGE": "tool_runs",
    "GENESIS_COLLAB_STORAGE": "collaborations",
    "GENESIS_IMPROVEMENT_STORAGE": "improvements",
    "GENESIS_OPERATOR_STORAGE": "operators",
    "GENESIS_APPROVAL_STORAGE": "approvals",
    "GENESIS_CONNECTOR_STORAGE": "connectors",
    "GENESIS_GOVERNANCE_STORAGE": "governance",
    "GENESIS_CAPABILITY_STORAGE": "capabilities",
    "GENESIS_INTELLIGENCE_STORAGE": "intelligence",
    "GENESIS_RELIABILITY_STORAGE": "reliability",
    "GENESIS_WORLD_MODEL_STORAGE": "world_model",
    "GENESIS_LIVING_SYSTEMS_STORAGE": "living_systems",
    "GENESIS_NERVOUS_SYSTEM_STORAGE": "nervous_system",
}


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _runtime_dir(name: str) -> Path:
    return Path(os.getenv(name, ROOT / RUNTIME_DEFAULTS[name])).resolve()


def run(*, allow_missing_frontend: bool = False, create_dirs: bool = False) -> dict:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from backend.genesis import long_term
    from backend.shared.config import settings

    checks: list[dict] = []

    try:
        settings.validate_startup()
        checks.append(_check("production_env_validation", True, settings.GENESIS_ENV))
    except Exception as exc:
        checks.append(_check("production_env_validation", False, str(exc)))

    frontend_dist = Path(os.getenv("GENESIS_FRONTEND_DIST", ROOT / "frontend" / "dist")).resolve()
    checks.append(_check(
        "frontend_dist_present",
        allow_missing_frontend or (frontend_dist / "index.html").exists(),
        str(frontend_dist),
    ))

    if os.getenv("VITE_GENESIS_API_TOKEN"):
        checks.append(_check("no_frontend_baked_token", False, "VITE_GENESIS_API_TOKEN must be empty for public production builds"))
    else:
        checks.append(_check("no_frontend_baked_token", True))

    for env_name in RUNTIME_DIR_ENV:
        path = _runtime_dir(env_name)
        if create_dirs:
            path.mkdir(parents=True, exist_ok=True)
        checks.append(_check(f"{env_name.lower()}_writable", path.exists() and os.access(path, os.W_OK), str(path)))

    db_status = long_term.status()
    checks.append(_check("long_term_database_connected", db_status.get("database", {}).get("connected") is True, db_status.get("database", {}).get("path", "")))

    checks.append(_check("dockerfile_present", (ROOT / "Dockerfile").exists()))
    checks.append(_check("compose_present", (ROOT / "docker-compose.yml").exists()))
    checks.append(_check("render_blueprint_present", (ROOT / "render.yaml").exists()))

    ok = all(item["ok"] for item in checks)
    return {
        "ok": ok,
        "version": "genesis-production-preflight-v1",
        "checks": checks,
        "database": db_status,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Genesis production deployment readiness.")
    parser.add_argument("--allow-missing-frontend", action="store_true")
    parser.add_argument("--create-dirs", action="store_true")
    args = parser.parse_args()
    report = run(
        allow_missing_frontend=args.allow_missing_frontend,
        create_dirs=args.create_dirs,
    )
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
