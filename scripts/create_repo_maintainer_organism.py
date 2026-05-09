#!/usr/bin/env python3
"""Create the real GitHub Repo Maintainer organism.

This script refuses to create the organism unless GitHub credentials and the
repo allowlist pass a live read-only probe. It is intentionally not a mock demo.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.genesis import connectors, metacognition, runtime, store


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a real Repo Maintainer organism.")
    parser.add_argument("repo", help="Allowlisted GitHub repository in owner/repo form.")
    parser.add_argument(
        "--name",
        default="Repo Maintainer Organism",
        help="Organism display name.",
    )
    args = parser.parse_args()

    probe = connectors.probe_adapter(
        adapter_id="github_create_issue",
        scope=args.repo,
        live=True,
    )
    if probe["status"] != "pass":
        print(
            json.dumps(
                {
                    "ok": False,
                    "message": "GitHub connector is not ready. Configure GITHUB_TOKEN or GENESIS_GITHUB_TOKEN and GENESIS_GITHUB_REPOSITORIES, then retry.",
                    "probe": probe,
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2

    organism = runtime.seed(
        name=args.name,
        intent_goal=(
            f"Act as a real maintainer assistant for {args.repo}: watch repository signals, "
            "prioritize issues and pull requests, remember maintainer preferences, propose safe fixes, "
            "dream alternative solutions before risky changes, and request human approval before posting comments or creating issues."
        ),
        constraints=[
            "Use only real GitHub connector state; do not invent repository activity.",
            "Never write to GitHub without an explicit scoped permission grant.",
            "Prefer read-only analysis before proposing comments, issues, or code changes.",
            "Explain priority using user impact, maintainer burden, implementation risk, and evidence.",
            "Record every recommendation in causal memory so future triage can improve.",
        ],
        forbidden=[
            "Do not fabricate issues, pull requests, reviews, stars, users, or repository metrics.",
            "Do not post comments, create issues, close issues, merge pull requests, or deploy without human approval.",
            "Do not expose tokens, webhook URLs, private data, or secrets in reasoning or connector payloads.",
        ],
        success_signals=[
            "GitHub connector probes pass before action.",
            "Triage recommendations cite real repository evidence.",
            "Human approvals are requested for every GitHub write.",
            "Maintainer preferences are remembered and reused.",
            "Benchmark fitness improves across repository-maintainer runs.",
        ],
    )
    organism.perception_sources.append(
        {
            "kind": "github_repo",
            "type": "repo_maintainer_signal",
            "repo": args.repo,
            "read_probe": "github_create_issue",
            "write_connectors": ["github_create_issue", "github_issue_comment"],
            "requires_approval": True,
            "no_fake_activity": True,
        }
    )
    metacognition.seed_default_strategies(organism)
    store.save_organism(organism)

    print(
        json.dumps(
            {
                "ok": True,
                "organism": organism.model_dump(mode="json"),
                "probe": probe,
                "message": "Created a real Repo Maintainer organism backed by a live GitHub connector probe.",
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
