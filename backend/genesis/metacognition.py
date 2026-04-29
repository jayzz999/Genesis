"""Phase 5A — Meta-Cognitive Critic: the organism evaluates its own reasoning.

This is the core AGI-adjacent capability. After each real Decision, a critic
pass asks: 'Was my reasoning good? How should I reason differently next time?'

The critic maintains a Reasoning Strategy Library — a set of named approaches
(first-principles, analogical, cautious, exploratory) with tracked success
rates. Over time, the organism learns WHICH strategy works best for WHICH
type of perception, and automatically selects the optimal one.

This creates a genuine self-improvement loop:
  Decision → Critic → Strategy Update → Better Decision → Critic → ...

No other agent framework implements this. It is the difference between an
agent that acts and an agent that genuinely improves at thinking.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from backend.shared.gemini_client import generate_text

from . import store
from .types import Decision, MetaDecision, Organism, ReasoningStrategy

logger = logging.getLogger("genesis.metacognition")


# ── Default reasoning strategies (seeded into every new organism) ──────

DEFAULT_STRATEGIES: list[dict] = [
    {
        "name": "systematic",
        "description": "Step-by-step analysis. Break the problem down, address each part in order.",
        "system_prompt_modifier": (
            "ACTIVE REASONING STRATEGY: SYSTEMATIC\n"
            "Think step-by-step. Enumerate what you know, what you don't know, "
            "and address each sub-problem in logical order before choosing an action. "
            "Prefer thoroughness over speed."
        ),
    },
    {
        "name": "analogical",
        "description": "Reason by analogy. Find similar past situations and adapt what worked.",
        "system_prompt_modifier": (
            "ACTIVE REASONING STRATEGY: ANALOGICAL\n"
            "Before deciding, search your memory for SIMILAR past perceptions. "
            "What action worked then? What failed? Adapt the best past approach "
            "to the current situation rather than reasoning from scratch."
        ),
    },
    {
        "name": "cautious",
        "description": "Risk-averse. Prefer safe, reversible actions. Gather more context first.",
        "system_prompt_modifier": (
            "ACTIVE REASONING STRATEGY: CAUTIOUS\n"
            "Prioritize safety. Before acting, consider what could go wrong. "
            "Prefer reversible actions. If uncertain, choose 'noop' or 'remember' "
            "to gather more context before committing to a consequential action."
        ),
    },
    {
        "name": "exploratory",
        "description": "Try novel approaches. Prioritize learning over immediate success.",
        "system_prompt_modifier": (
            "ACTIVE REASONING STRATEGY: EXPLORATORY\n"
            "Prioritize LEARNING. If you have multiple options, prefer the one "
            "you haven't tried before. Novel actions generate more useful data "
            "than repeating known patterns. Embrace calculated risk."
        ),
    },
    {
        "name": "first_principles",
        "description": "Reason from fundamentals. Strip assumptions, build logic from ground truth.",
        "system_prompt_modifier": (
            "ACTIVE REASONING STRATEGY: FIRST PRINCIPLES\n"
            "Do NOT rely on patterns or analogies. Strip the problem to its "
            "fundamental truths. What is definitely true? What follows logically? "
            "Build your action from these foundations, even if it contradicts past patterns."
        ),
    },
]


def seed_default_strategies(org: Organism) -> list[ReasoningStrategy]:
    """Seed an organism with the default reasoning strategy library.
    Called at organism birth. Returns the strategies added.
    """
    if org.reasoning_strategies:
        return org.reasoning_strategies

    strategies = []
    for s in DEFAULT_STRATEGIES:
        strategy = ReasoningStrategy(
            name=s["name"],
            description=s["description"],
            system_prompt_modifier=s["system_prompt_modifier"],
        )
        strategies.append(strategy)

    org.reasoning_strategies = strategies
    # Default to systematic
    org.active_strategy_id = strategies[0].id
    return strategies


def get_active_strategy(org: Organism) -> Optional[ReasoningStrategy]:
    """Get the currently active reasoning strategy, if any."""
    if not org.active_strategy_id or not org.reasoning_strategies:
        return None
    for s in org.reasoning_strategies:
        if s.id == org.active_strategy_id:
            return s
    return None


def get_strategy_prompt_modifier(org: Organism) -> str:
    """Get the system prompt modifier for the active strategy.
    Returns empty string if no strategy is active.
    """
    strategy = get_active_strategy(org)
    if not strategy:
        return ""
    return f"\n\n{strategy.system_prompt_modifier}\n"


# ── Critic system prompt ───────────────────────────────────────────────

CRITIC_SYSTEM = """You are the meta-cognitive critic of a living digital organism.
Your job is NOT to decide what action to take. That already happened.
Your job is to EVALUATE the quality of the reasoning that led to the action.

You receive:
  - DECISION: the organism's reasoning, action, and result
  - PERCEPTION: what triggered the decision
  - STRATEGY_USED: which reasoning strategy was active
  - AVAILABLE_STRATEGIES: the full strategy library
  - META_HISTORY: the organism's recent self-evaluations (to detect patterns)
  - LEARNED_PATTERNS: what the organism has already learned

Respond with STRICT JSON:
{
  "reasoning_quality": 0.0-1.0,
  "attention_gaps": ["things the organism should have noticed but didn't"],
  "action_efficiency": 0.0-1.0,
  "repeated_mistake": true/false,
  "lesson": "one-sentence insight about how to reason better next time",
  "knowledge_gaps": ["specific questions or unknowns identified during this reasoning that should be explored later"],
  "recommended_strategy": "strategy_name for next similar perception",
  "strategy_performance_delta": -1.0 to 1.0,
  "confidence": 0.0-1.0
}

RULES:
  - Be HONEST. Do not inflate scores. A failed action with bad reasoning = low scores.
  - A successful action with lucky reasoning should still note the reasoning gaps.
  - recommended_strategy should be one of the AVAILABLE_STRATEGIES names.
  - strategy_performance_delta: positive means the current strategy HELPED,
    negative means it HURT, zero means neutral.
  - lesson should be SPECIFIC and ACTIONABLE, not generic advice.
  - attention_gaps should only list things that were ACTUALLY available in
    the perception/context but were ignored.
"""


# ── Core critique function ─────────────────────────────────────────────

async def critique(
    organism_id: str,
    decision: Decision,
    *,
    event_callback=None,
) -> Optional[MetaDecision]:
    """Run the meta-cognitive critic on a completed Decision.

    This is the heart of Phase 5A. After the organism acts, the critic
    evaluates the quality of reasoning and updates the strategy library.

    Returns the MetaDecision, or None if meta-cognition is disabled/fails.
    """
    org = store.load_organism(organism_id)
    if not org:
        return None

    # Skip if disabled or if this was a dream/shadow
    if not org.meta_cognition_enabled:
        return None
    if decision.is_dream or decision.shadow_branch:
        return None
    # Skip trivial actions (noop, declare_done) — not enough signal
    action_name = decision.action.get("name", "noop")
    if action_name in ("noop",):
        return None

    # Build critic context
    active_strategy = get_active_strategy(org)
    meta_history = store.load_meta_decisions(organism_id, limit=5)

    critic_payload = {
        "DECISION": {
            "reasoning": decision.reasoning[:1500],
            "action": decision.action,
            "result_ok": decision.result.get("ok") if isinstance(decision.result, dict) else None,
            "result_summary": str(decision.result)[:500],
            "alternatives_considered": decision.alternatives_considered[:3],
        },
        "PERCEPTION": decision.trigger,
        "STRATEGY_USED": {
            "name": active_strategy.name if active_strategy else "none",
            "description": active_strategy.description if active_strategy else "no strategy active",
        },
        "AVAILABLE_STRATEGIES": [
            {"name": s.name, "description": s.description, "success_rate": round(s.success_rate, 2)}
            for s in org.reasoning_strategies
        ],
        "META_HISTORY": [
            {
                "lesson": md.lesson,
                "reasoning_quality": md.reasoning_quality,
                "repeated_mistake": md.repeated_mistake,
                "recommended_strategy": md.recommended_strategy,
            }
            for md in meta_history
        ],
        "LEARNED_PATTERNS": org.learned_patterns[-10:],
    }

    try:
        raw = await generate_text(
            prompt=json.dumps(critic_payload, indent=2, default=str),
            system=CRITIC_SYSTEM,
            temperature=0.2,
            max_tokens=800,
        )
    except Exception as e:
        logger.warning(f"[metacognition] Critic LLM call failed for {organism_id}: {e}")
        return None

    parsed = _parse_critic_json(raw)
    if not parsed:
        logger.warning(f"[metacognition] Critic output unparseable for {organism_id}")
        return None

    # Build MetaDecision
    meta_decision = MetaDecision(
        decision_id=decision.id,
        organism_id=organism_id,
        reasoning_quality=_clamp(float(parsed.get("reasoning_quality", 0.5))),
        attention_gaps=list(parsed.get("attention_gaps", [])),
        action_efficiency=_clamp(float(parsed.get("action_efficiency", 0.5))),
        repeated_mistake=bool(parsed.get("repeated_mistake", False)),
        lesson=str(parsed.get("lesson", ""))[:500],
        recommended_strategy=parsed.get("recommended_strategy"),
        strategy_used=active_strategy.id if active_strategy else None,
        strategy_performance_delta=max(-1.0, min(1.0, float(parsed.get("strategy_performance_delta", 0.0)))),
        confidence=_clamp(float(parsed.get("confidence", 0.5))),
    )

    # Persist the meta-decision
    store.save_meta_decision(meta_decision)

    # Phase 5E: Accumulate knowledge gaps
    new_gaps = list(parsed.get("knowledge_gaps", []))
    if new_gaps:
        org.knowledge_gaps.extend(new_gaps)
        # deduplicate and cap at 20
        org.knowledge_gaps = list(dict.fromkeys(org.knowledge_gaps))[-20:]

    # Update the strategy library based on the critic's feedback
    _update_strategy_library(org, meta_decision, decision)

    # Emit event
    if event_callback:
        await event_callback("organism.meta_critique", {
            "organism_id": organism_id,
            "decision_id": decision.id,
            "meta_decision_id": meta_decision.id,
            "reasoning_quality": meta_decision.reasoning_quality,
            "lesson": meta_decision.lesson,
            "recommended_strategy": meta_decision.recommended_strategy,
            "repeated_mistake": meta_decision.repeated_mistake,
        })

    logger.info(
        f"[metacognition] {organism_id} critique: "
        f"quality={meta_decision.reasoning_quality:.2f} "
        f"efficiency={meta_decision.action_efficiency:.2f} "
        f"lesson={meta_decision.lesson[:60]}"
    )

    return meta_decision


# ── Strategy library updates ──────────────────────────────────────────

def _update_strategy_library(
    org: Organism,
    meta: MetaDecision,
    decision: Decision,
) -> None:
    """Update strategy success rates and switch active strategy if needed.

    Uses exponential moving average for success rates. Switches strategy
    when the critic recommends a different one AND confidence is high enough.
    """
    alpha = 0.3  # EMA smoothing factor — higher = more responsive

    # Update the used strategy's success rate
    if meta.strategy_used:
        for s in org.reasoning_strategies:
            if s.id == meta.strategy_used:
                # Composite score from reasoning quality + action efficiency
                score = (meta.reasoning_quality + meta.action_efficiency) / 2.0
                s.success_rate = alpha * score + (1 - alpha) * s.success_rate
                s.usage_count += 1

                # Track which perception types this strategy is good/bad for
                perception_type = decision.trigger.get("type", "unknown")
                if score >= 0.7 and perception_type not in s.best_for:
                    s.best_for.append(perception_type)
                    s.best_for = s.best_for[-10:]  # cap
                elif score <= 0.3 and perception_type not in s.worst_for:
                    s.worst_for.append(perception_type)
                    s.worst_for = s.worst_for[-10:]  # cap
                break

    # Switch strategy if critic recommends it with enough confidence
    if meta.recommended_strategy and meta.confidence >= 0.6:
        for s in org.reasoning_strategies:
            if s.name == meta.recommended_strategy:
                if s.id != org.active_strategy_id:
                    logger.info(
                        f"[metacognition] {org.id} switching strategy: "
                        f"{_strategy_name(org, org.active_strategy_id)} → {s.name} "
                        f"(confidence={meta.confidence:.2f})"
                    )
                    org.active_strategy_id = s.id
                break

    # Auto-promote lesson to learned_patterns if quality is high and it's novel
    if (meta.confidence >= 0.7
            and meta.lesson
            and meta.lesson not in org.learned_patterns
            and len(org.learned_patterns) < 50):
        org.learned_patterns.append(f"[meta] {meta.lesson}")

    store.save_organism(org)


def _strategy_name(org: Organism, strategy_id: Optional[str]) -> str:
    """Helper to get strategy name from ID."""
    if not strategy_id:
        return "none"
    for s in org.reasoning_strategies:
        if s.id == strategy_id:
            return s.name
    return "unknown"


# ── Select best strategy for a perception type ────────────────────────

def select_strategy_for_perception(
    org: Organism,
    perception: dict,
) -> Optional[ReasoningStrategy]:
    """Select the best strategy for a given perception type.

    Uses a simple heuristic:
    1. If a strategy's best_for includes this perception type → prefer it
    2. If a strategy's worst_for includes this type → avoid it
    3. Otherwise fall back to highest success_rate

    This runs BEFORE reasoning, so the organism uses the best-known
    strategy for the situation.
    """
    if not org.reasoning_strategies:
        return None

    perception_type = perception.get("type", "unknown")
    candidates = list(org.reasoning_strategies)

    # 1. Check for a strategy specifically good at this perception type
    for s in candidates:
        if perception_type in s.best_for:
            return s

    # 2. Filter out strategies known to be bad for this type
    filtered = [s for s in candidates if perception_type not in s.worst_for]
    if not filtered:
        filtered = candidates  # if everything is "worst", use all

    # 3. Pick highest success rate
    return max(filtered, key=lambda s: s.success_rate)


# ── Metacognition summary for API ─────────────────────────────────────

def metacognition_summary(organism_id: str) -> dict:
    """Build a summary of an organism's meta-cognitive state for the API."""
    org = store.load_organism(organism_id)
    if not org:
        return {"error": "organism not found"}

    meta_decisions = store.load_meta_decisions(organism_id, limit=20)
    active_strategy = get_active_strategy(org)

    # Compute aggregate stats
    if meta_decisions:
        avg_quality = sum(m.reasoning_quality for m in meta_decisions) / len(meta_decisions)
        avg_efficiency = sum(m.action_efficiency for m in meta_decisions) / len(meta_decisions)
        repeated_mistakes = sum(1 for m in meta_decisions if m.repeated_mistake)
        lessons = [m.lesson for m in meta_decisions if m.lesson]
    else:
        avg_quality = avg_efficiency = 0.0
        repeated_mistakes = 0
        lessons = []

    return {
        "enabled": org.meta_cognition_enabled,
        "active_strategy": {
            "id": active_strategy.id if active_strategy else None,
            "name": active_strategy.name if active_strategy else None,
            "success_rate": round(active_strategy.success_rate, 3) if active_strategy else None,
            "usage_count": active_strategy.usage_count if active_strategy else 0,
        },
        "strategy_library": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "success_rate": round(s.success_rate, 3),
                "usage_count": s.usage_count,
                "best_for": s.best_for,
                "worst_for": s.worst_for,
                "is_active": s.id == org.active_strategy_id,
            }
            for s in org.reasoning_strategies
        ],
        "meta_history": [
            {
                "id": m.id,
                "decision_id": m.decision_id,
                "timestamp": m.timestamp.isoformat(),
                "reasoning_quality": m.reasoning_quality,
                "action_efficiency": m.action_efficiency,
                "attention_gaps": m.attention_gaps,
                "repeated_mistake": m.repeated_mistake,
                "lesson": m.lesson,
                "recommended_strategy": m.recommended_strategy,
                "strategy_used": m.strategy_used,
                "confidence": m.confidence,
            }
            for m in meta_decisions
        ],
        "aggregate": {
            "total_critiques": len(meta_decisions),
            "avg_reasoning_quality": round(avg_quality, 3),
            "avg_action_efficiency": round(avg_efficiency, 3),
            "repeated_mistakes": repeated_mistakes,
            "unique_lessons": len(set(lessons)),
        },
    }


# ── JSON parsing helpers ──────────────────────────────────────────────

def _parse_critic_json(text: str) -> Optional[dict]:
    """Tolerant JSON extraction from critic LLM output."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.strip().rstrip("`").strip()
    try:
        return json.loads(s)
    except Exception:
        i, j = s.find("{"), s.rfind("}")
        if i != -1 and j != -1:
            try:
                return json.loads(s[i : j + 1])
            except Exception:
                pass
        return None


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))
