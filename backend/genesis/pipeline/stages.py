"""5-stage perception pipeline. Phase 1 substrate.

External contract: pipeline.run(...) is called by runtime.perceive() and
returns a fully-populated Decision identical to what the old monolithic
perceive() returned. Each stage is pure-ish (no global state mutation
beyond store calls and event emission).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .. import store
from ..types import Decision, Organism, OrganismState

logger = logging.getLogger("genesis.pipeline")

EventCallback = Optional[Callable[[str, dict], Awaitable[None]]]


@dataclass
class PipelineContext:
    """Carried through every stage. Mutable on purpose — stages append to it."""
    organism_id: str
    perception: dict
    is_dream: bool = False
    shadow_branch: Optional[str] = None
    parent_ids: Optional[list[str]] = None
    event_callback: EventCallback = None
    # Populated by stages
    organism: Optional[Organism] = None
    real_history: list[Decision] = field(default_factory=list)
    dream_history: list[Decision] = field(default_factory=list)
    skills_text: str = ""
    long_term_memory: list[dict] = field(default_factory=list)
    tool_catalog: list[dict] = field(default_factory=list)
    llm_raw: str = ""
    parsed: dict = field(default_factory=dict)
    decision: Optional[Decision] = None


async def gather_context(ctx: PipelineContext) -> None:
    ctx.organism = store.load_organism(ctx.organism_id)
    if not ctx.organism:
        raise ValueError(f"organism {ctx.organism_id} not found")

    # Phase 5A: seed default strategies if this organism has none
    if not ctx.organism.reasoning_strategies and not ctx.is_dream:
        from .. import metacognition
        metacognition.seed_default_strategies(ctx.organism)
        store.save_organism(ctx.organism)

    # Phase 5A: select best strategy for this perception type
    if not ctx.is_dream and ctx.organism.meta_cognition_enabled:
        from .. import metacognition
        best = metacognition.select_strategy_for_perception(ctx.organism, ctx.perception)
        if best and best.id != ctx.organism.active_strategy_id:
            ctx.organism.active_strategy_id = best.id
            store.save_organism(ctx.organism)

    all_decisions = store.all_decisions(ctx.organism_id)
    ctx.real_history = [d for d in all_decisions if not d.is_dream and not d.shadow_branch][-8:]
    ctx.dream_history = [d for d in all_decisions if d.is_dream][-5:]
    from ..skills import inherit
    ctx.skills_text = inherit.load_skills_text(ctx.organism)
    from .. import memory
    ctx.long_term_memory = [
        item.model_dump(mode="json")
        for item in memory.retrieve(ctx.organism, ctx.perception, limit=5)
    ]


async def load_capabilities(ctx: PipelineContext) -> None:
    from .. import runtime
    from ..mcp import client as mcp_client
    catalog = runtime._builtin_tool_catalog()
    if ctx.organism and ctx.organism.mcp_servers:
        await mcp_client.pool.ensure_organism(ctx.organism.id, ctx.organism.mcp_servers)
    mcp_tools = await mcp_client.pool.list_tools(ctx.organism_id) if ctx.organism else []
    builtin_names = {t["name"] for t in catalog}
    catalog.extend(t for t in mcp_tools if t["name"] not in builtin_names)
    ctx.tool_catalog = catalog


async def reason(ctx: PipelineContext) -> None:
    from .. import runtime
    ctx.llm_raw = await runtime._reason_with_llm(ctx)


async def act(ctx: PipelineContext) -> None:
    from .. import runtime
    ctx.parsed = runtime._parse_llm_response(ctx.llm_raw)
    ctx.decision = await runtime._execute_action(ctx)


async def record(ctx: PipelineContext) -> None:
    from .. import runtime
    await runtime._persist_and_emit(ctx)


async def meta_critique(ctx: PipelineContext) -> None:
    """Phase 5A: Run the meta-cognitive critic after a real decision."""
    if ctx.is_dream or ctx.shadow_branch:
        return
    if not ctx.decision:
        return
    try:
        from .. import metacognition
        await metacognition.critique(
            ctx.organism_id,
            ctx.decision,
            event_callback=ctx.event_callback,
        )
    except Exception as e:
        logger.warning(f"[pipeline] meta_critique failed (non-fatal): {e}")


def _is_provider_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "429",
            "quota",
            "rate_limit",
            "rate limit",
            "resource_exhausted",
            "tokens per day",
        )
    )


def _can_record_quota_fallback(ctx: PipelineContext) -> bool:
    return bool(not ctx.is_dream and ctx.organism)


async def record_quota_fallback(ctx: PipelineContext, exc: Exception) -> Decision:
    reasoning = (
        "Autonomous perception was received, but the configured LLM provider "
        "rejected the reasoning call due to quota or rate limits. Recording the "
        "observation and deferring action so causal memory remains honest."
    )
    ctx.decision = Decision(
        organism_id=ctx.organism_id,
        parent_ids=ctx.parent_ids or ([ctx.real_history[-1].id] if ctx.real_history else []),
        trigger=ctx.perception,
        context_snapshot={
            "recent_memory_ids": [d.id for d in ctx.real_history],
            "dream_ids": [d.id for d in ctx.dream_history],
            "long_term_memory_ids": [m.get("id") for m in ctx.long_term_memory],
            "patterns_count": len(ctx.organism.learned_patterns),
            "fallback": "provider_quota",
        },
        reasoning=reasoning,
        action={"name": "noop", "args": {"reason": "provider_quota"}},
        result={
            "ok": False,
            "deferred": True,
            "provider_quota": True,
            "error": str(exc)[:1000],
        },
        alternatives_considered=[
            {
                "name": "retry_later",
                "args": {},
                "why_not": "Provider quota indicated the next successful attempt needs to wait.",
            }
        ],
        strategy_used=ctx.organism.active_strategy_id,
    )
    await record(ctx)
    return ctx.decision


async def run(
    organism_id: str,
    perception: dict,
    *,
    is_dream: bool = False,
    shadow_branch: Optional[str] = None,
    parent_ids: Optional[list[str]] = None,
    event_callback: EventCallback = None,
) -> Decision:
    ctx = PipelineContext(
        organism_id=organism_id,
        perception=perception,
        is_dream=is_dream,
        shadow_branch=shadow_branch,
        parent_ids=parent_ids,
        event_callback=event_callback,
    )
    try:
        await gather_context(ctx)
        await load_capabilities(ctx)
        await reason(ctx)
        await act(ctx)
        await record(ctx)
        await meta_critique(ctx)  # Phase 5A: self-evaluate reasoning quality
        assert ctx.decision is not None
        return ctx.decision
    except Exception as exc:
        if _is_provider_quota_error(exc) and _can_record_quota_fallback(ctx):
            return await record_quota_fallback(ctx, exc)
        if not is_dream:
            org = store.load_organism(organism_id)
            if org and org.state == OrganismState.ACTING:
                org.state = OrganismState.PERCEIVING
                store.save_organism(org)
        raise
