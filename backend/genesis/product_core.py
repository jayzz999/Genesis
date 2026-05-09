"""Production-core registry for Genesis.

This module draws a bright line between the subsystems that must be reliable for
production operation and the research/product-exploration modules that can evolve
behind an explicit experimental label.
"""

from __future__ import annotations

PRODUCTION_CORE = [
    {
        "id": "organism_runtime",
        "name": "Organism runtime and causal memory",
        "why": "Creates organisms, processes perceptions, records decisions, dreams, branches, and skill inheritance.",
        "modules": ["runtime", "pipeline", "store", "causality", "dreams", "skills"],
    },
    {
        "id": "auth_control_plane",
        "name": "Auth and production configuration",
        "why": "Protects mutating routes, validates startup safety, and manages operator sessions.",
        "modules": ["long_term", "shared.config", "main"],
    },
    {
        "id": "approval_permissions",
        "name": "Approval and permission gates",
        "why": "Blocks risky work until scoped grants, quorum, confirmation, and audit records exist.",
        "modules": ["approvals", "governance"],
    },
    {
        "id": "connector_execution",
        "name": "Permission-gated connectors",
        "why": "Performs real side effects only through configured, allowlisted adapters.",
        "modules": ["connectors", "mcp.client", "mcp.catalog"],
    },
    {
        "id": "operator_lifecycle",
        "name": "Lifecycle and operator supervision",
        "why": "Runs durable autonomous loops, webhooks, polling, and pause/resume controls.",
        "modules": ["lifecycle", "autonomous_operator", "events"],
    },
    {
        "id": "observable_ui",
        "name": "Operational UI",
        "why": "Lets a human inspect state, approve actions, manage connectors, and verify runtime health.",
        "modules": ["frontend.genesis_core"],
    },
    {
        "id": "verification",
        "name": "Smoke, security, and deployment verification",
        "why": "Prevents unsafe production settings and catches permission-boundary regressions.",
        "modules": ["tests", "scripts.production_preflight"],
    },
]

EXPERIMENTAL_SUBSYSTEMS = [
    {
        "id": "living_systems",
        "name": "Living systems simulation",
        "why": "Useful product language and research surface, not required for safe production operation.",
        "modules": ["living_systems", "body", "metabolism", "homeostasis", "nervous_system"],
    },
    {
        "id": "capability_growth",
        "name": "Capability growth and self-improvement",
        "why": "Promising, but should remain behind evidence gates until production outcomes are proven.",
        "modules": ["capabilities", "self_improvement", "intelligence"],
    },
    {
        "id": "collaboration_debate",
        "name": "Multi-organism collaboration and debate",
        "why": "Helpful for analysis workflows, but not part of the minimum governed-operations core.",
        "modules": ["collaboration", "society", "metacognition"],
    },
    {
        "id": "world_model",
        "name": "World model and reliability missions",
        "why": "Valuable observability and learning layer that can mature independently from the core runtime.",
        "modules": ["world_model", "reliability"],
    },
    {
        "id": "population_evolution",
        "name": "Population evolution",
        "why": "Research/benchmark mechanism; not necessary to run a single governed autonomous worker.",
        "modules": ["population"],
    },
]


def status() -> dict:
    return {
        "version": "genesis-production-core-v1",
        "core_count": len(PRODUCTION_CORE),
        "experimental_count": len(EXPERIMENTAL_SUBSYSTEMS),
        "production_core": PRODUCTION_CORE,
        "experimental": EXPERIMENTAL_SUBSYSTEMS,
    }
