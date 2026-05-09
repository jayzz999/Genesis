"""Event bridge — Genesis events → external listeners (e.g. WebSocket broadcaster).

Genesis modules emit events via `emit(event_type, payload)`. The web layer
registers a listener with `subscribe(callback)`. This decouples runtime/dreams
from FastAPI.

All Genesis events have shape:
    {
        "type": "organism.<verb>",   # see EVENT_TYPES below
        "organism_id": "o_...",
        "ts": "2026-...",
        ... event-specific fields ...
    }
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Awaitable, Callable

logger = logging.getLogger("genesis.events")

# Event vocabulary — keep tight and meaningful.
EVENT_TYPES = {
    "organism.seeded",          # new organism crystallized
    "organism.perceiving",       # received an event, about to reason
    "organism.reasoning",        # LLM produced reasoning + intended action
    "organism.acted",            # action executed (with result)
    "organism.dreaming_start",   # imagination cycle starting
    "organism.dreamt",           # one dream perception completed
    "organism.dreaming_end",     # imagination cycle complete
    "organism.edited",           # past decision was retroactively edited
    "organism.branch_created",   # counterfactual branch built
    "organism.branch_promoted",  # branch became canonical reality
    "organism.died",             # organism removed
    "organism.distilled",        # organism's life distilled into a Skill
    "organism.meta_critique",    # reasoning quality critique recorded
    "organism.nervous_tick",     # drives, needs, and autonomous intentions updated
    "organism.intention_completed",
    "organism.autonomy_cycle",
    "organism.body_mapped",
    "organism.sensor_attached",
    "organism.metabolism_recovered",
    "organism.homeostasis_checked",
    "organism.immune_response",
    "organism.reproduced",
    "organism.sleep_consolidated",
    "organism.development_tick",
    "organism.selection_round",
    "organism.temperament_calibrated",
    "organism.goal_refinement_proposed",
    "organism.culture_pulse",
    "organism.budget_pulse",
    "organism.world_sandbox_pulse",
    "auth.bootstrap",
    "auth.login",
    "auth.logout",
    "memory.created",            # Module 2 durable memory written
    "curriculum.updated",        # Module 2 curriculum changed after benchmark run
    "tool_sandbox.completed",    # Module 3 sandbox tool run completed
    "collaboration.started",     # Module 4 debate run started
    "collaboration.proposals_ready",
    "collaboration.critiques_ready",
    "collaboration.completed",
    "collaboration.failed",
    "self_improvement.started",  # Module 5 gated self-improvement cycle
    "self_improvement.candidate_ready",
    "self_improvement.completed",
    "self_improvement.failed",
    "operator.created",          # Module 6 persistent autonomous operator
    "operator.paused",
    "operator.resumed",
    "operator.tick_started",
    "operator.tick_completed",
    "operator.completed",
    "operator.failed",
    "approval.requested",        # Module 7 human permission gate requested
    "approval.approved",
    "approval.rejected",
    "approval.confirmed",
    "approval.executed",
    "approval.break_glass",
    "approval.expired",
    "approval.policy_evaluated",
    "approval.integrity_verified",
    "approval.integrity_failed",
    "permission.granted",       # Module 8 scoped permission grants
    "permission.checked",
    "permission.denied",
    "permission.consumed",
    "permission.revoked",
    "connector.started",        # Module 9 permission-gated connector adapters
    "connector.completed",
    "connector.blocked",
    "connector.failed",
    "connector.artifact_written",
    "governance.drill_completed",     # Module 14..23 assurance and operations
    "governance.replay_completed",
    "governance.intent_bound",
    "governance.evidence_created",
    "governance.evaluation_completed",
    "governance.lockdown_changed",
    "capability.drill_completed",     # Module 24..33 capability growth
    "capability.task_graph_created",
    "capability.task_completed",
    "capability.research_completed",
    "intelligence.drill_completed",   # Module 34..43 product intelligence
    "intelligence.knowledge_graph_built",
    "intelligence.goal_contract_created",
    "intelligence.data_classified",
    "intelligence.feedback_recorded",
    "intelligence.release_created",
    "reliability.drill_completed",    # Module 44..53 reliability and mission execution
    "reliability.benchmark_created",
    "reliability.mission_created",
    "reliability.workstyle_recorded",
    "world.learning_completed",
    "world.entity_recorded",
    "world.evidence_recorded",
    "world.belief_recorded",
    "world.snapshot_created",
    "population.generation_start",
    "population.scored",
    "population.generation_complete",
    "population.generation_bred",
    "population.complete",
}


_subscribers: list[Callable[[dict], Awaitable[None]]] = []


def subscribe(callback: Callable[[dict], Awaitable[None]]) -> None:
    """Register an async listener. The web layer calls this once at startup."""
    _subscribers.append(callback)


def unsubscribe(callback: Callable[[dict], Awaitable[None]]) -> None:
    if callback in _subscribers:
        _subscribers.remove(callback)


async def emit(event_type: str, payload: dict | None = None) -> None:
    """Fire an event to all subscribers. Never raises — listener errors are
    caught and logged so they cannot kill the runtime mid-reasoning."""
    if event_type not in EVENT_TYPES:
        logger.warning(f"unknown event type: {event_type}")
    event = {"type": event_type, "ts": datetime.utcnow().isoformat()}
    if payload:
        event.update(payload)
    for cb in list(_subscribers):
        try:
            await cb(event)
        except Exception as e:
            logger.error(f"subscriber {cb} raised on {event_type}: {e}")


def make_callback() -> Callable[[str, dict], Awaitable[None]]:
    """Return an event_callback compatible with runtime/dreams signatures.

    Runtime expects callback(event_type: str, data: dict). We translate that
    into emit() calls so all events flow through the same bus.
    """
    async def cb(event_type: str, data: dict) -> None:
        await emit(event_type, data)
    return cb
