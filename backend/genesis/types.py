"""Core data types for digital organisms.

The whole system revolves around these. Everything else is plumbing.

Key insight: there is NO `Workflow` type. There is only `Organism` (a living
thing with intent + memory + body) and `Decision` (an event in its causal
history). Workflows don't exist in Genesis — they were never the right
abstraction.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ── Lifecycle ──────────────────────────────────────────────────────────

class OrganismState(str, Enum):
    SEEDED = "seeded"        # Intent received, hasn't perceived anything yet
    PERCEIVING = "perceiving"  # Watching for events, idle in between
    ACTING = "acting"          # Currently reasoning + executing
    DREAMING = "dreaming"      # Imagining hypothetical futures
    DYING = "dying"            # Intent satisfied or revoked
    DEAD = "dead"              # DNA donated to gene pool


# ── Intent ─────────────────────────────────────────────────────────────

class Intent(BaseModel):
    """The mind of the organism. Immutable goal, always interpreted."""
    goal: str = Field(..., description="Natural-language statement of purpose.")
    constraints: list[str] = Field(default_factory=list, description="Hard rules.")
    success_signals: list[str] = Field(
        default_factory=list,
        description="Implicit telemetry that means we're doing well."
    )
    forbidden: list[str] = Field(default_factory=list, description="Hard rules of what NOT to do.")
    edited_at: datetime = Field(default_factory=datetime.utcnow)


# ── MCP server specification ───────────────────────────────────────────

class MCPServerSpec(BaseModel):
    """Describes one MCP server an organism can connect to."""
    name: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    transport: str = "stdio"  # "stdio" | "sse"


# ── Reasoning Strategy (cognitive DNA) ─────────────────────────────────

class ReasoningStrategy(BaseModel):
    """A named approach to reasoning. Organisms learn which works best.

    Over time the meta-cognitive critic updates success_rate per strategy
    and maps perception types to strategies. This is how organisms learn
    to THINK DIFFERENTLY — not just act differently.
    """
    id: str = Field(default_factory=lambda: f"rs_{uuid4().hex[:8]}")
    name: str = Field(..., description="e.g. 'first_principles', 'analogical', 'cautious'")
    description: str = ""
    system_prompt_modifier: str = Field(
        "",
        description="Injected into the LLM system prompt when this strategy is active."
    )
    success_rate: float = Field(0.5, description="Rolling success rate, updated by critic.")
    usage_count: int = 0
    best_for: list[str] = Field(
        default_factory=list,
        description="Perception types this strategy excels at."
    )
    worst_for: list[str] = Field(
        default_factory=list,
        description="Perception types this strategy fails at."
    )


# ── Skill reference (DNA pointer) ──────────────────────────────────────

class SkillRef(BaseModel):
    """A pointer into the Genesis skill pool. Lives in organism DNA."""
    skill_id: str
    name: str
    inherited_at: datetime


# ── Decision (the atom of causality) ───────────────────────────────────

class Decision(BaseModel):
    """A single moment of organism reasoning. Atom of causal history.

    Every decision answers: 'given what I knew, what did I choose to do, and why?'
    Decisions form a directed graph (parent_ids → this) capturing causality.
    Edits to past decisions propagate via the graph.
    """
    id: str = Field(default_factory=lambda: f"d_{uuid4().hex[:12]}")
    organism_id: str
    parent_ids: list[str] = Field(
        default_factory=list,
        description="Causally upstream decisions whose outputs this depends on."
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # What the organism perceived (input)
    trigger: dict = Field(default_factory=dict, description="Event that prompted this decision.")
    context_snapshot: dict = Field(
        default_factory=dict,
        description="What the organism knew at decision time (for replay)."
    )

    # What it reasoned (LLM output)
    reasoning: str = Field("", description="Natural-language justification from the LLM.")

    # What it did (action)
    action: dict = Field(
        default_factory=dict,
        description="Tool/function invoked: {name, args}. Empty if pure reasoning."
    )
    result: dict = Field(default_factory=dict, description="Action outcome.")

    # Counterfactual material
    alternatives_considered: list[dict] = Field(
        default_factory=list,
        description="Other actions the LLM weighed but didn't choose. Used for what-ifs."
    )

    # Provenance
    is_dream: bool = Field(False, description="True if this happened in imagination, not reality.")
    edited: bool = Field(False, description="True if a user retroactively edited this.")
    edited_from: Optional[str] = Field(None, description="If edited, the original decision id.")
    shadow_branch: Optional[str] = Field(
        None,
        description="If part of a counterfactual timeline, the branch name."
    )
    strategy_used: Optional[str] = Field(
        None,
        description="ID of the ReasoningStrategy active when this decision was made."
    )


# ── SubGoal (Phase 5B — Goal Decomposition) ────────────────────────────

class SubGoal(BaseModel):
    """A decomposed piece of the parent intent."""
    id: str = Field(default_factory=lambda: f"sg_{uuid4().hex[:8]}")
    goal: str = Field(..., description="The specific sub-objective")
    priority: int = 0
    status: str = "pending"  # pending | active | completed | failed
    child_organism_id: Optional[str] = None
    result: Optional[dict] = None


# ── OrganismMessage (Phase 5C — Society) ───────────────────────────────

class OrganismMessage(BaseModel):
    """A message sent between organisms."""
    id: str = Field(default_factory=lambda: f"msg_{uuid4().hex[:8]}")
    sender_id: str
    recipient_id: Optional[str] = None  # None = broadcast
    message_type: str = "inform"  # inform | request | delegate | result
    content: dict
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    read: bool = False


# ── Organism ───────────────────────────────────────────────────────────

class Organism(BaseModel):
    """A living digital entity. Has intent, memory, body, state.

    The organism IS its causal graph + intent + state. There is no compiled
    program — the runtime interprets the intent against new perceptions
    every time, using the causal graph as memory.
    """
    id: str = Field(default_factory=lambda: f"o_{uuid4().hex[:12]}")
    name: str = "unnamed"
    intent: Intent
    state: OrganismState = OrganismState.SEEDED
    born_at: datetime = Field(default_factory=datetime.utcnow)

    # Body — currently always 'interpreted'. Future: 'lora' | 'wasm' | 'native'.
    body_substrate: str = "interpreted"

    # Sensors — what the organism is watching. Stub for now.
    perception_sources: list[dict] = Field(default_factory=list)

    # Learned patterns distilled from experience (real + dreamt).
    # Each pattern is a natural-language summary the LLM can read.
    learned_patterns: list[str] = Field(default_factory=list)

    # Phase 1 — substrate
    mcp_servers: list[MCPServerSpec] = Field(default_factory=list)
    inherited_skills: list[SkillRef] = Field(default_factory=list)
    parent_organisms: list[str] = Field(default_factory=list)
    fitness_score: float = 0.0
    distilled_skill_id: Optional[str] = None

    # Phase 5A — Meta-Cognition: reasoning strategy library
    reasoning_strategies: list[ReasoningStrategy] = Field(default_factory=list)
    active_strategy_id: Optional[str] = Field(
        None,
        description="Currently active reasoning strategy. Updated by meta-critic."
    )
    meta_cognition_enabled: bool = Field(
        True,
        description="Whether the meta-cognitive critic runs after each decision."
    )

    # Phase 5B — Goal Decomposition
    sub_goals: list[SubGoal] = Field(default_factory=list)
    parent_organism_id: Optional[str] = None

    # Phase 5E — Curiosity
    knowledge_gaps: list[str] = Field(default_factory=list)
    hypotheses: list[dict] = Field(default_factory=list)
    surprise_log: list[dict] = Field(default_factory=list)

    # Configurable runtime knobs
    dream_budget_per_cycle: int = 1  # dreams per idle cycle (set GENESIS_DREAMING=0 to disable entirely)
    reasoning_model: str = "gemini-2.5-flash"  # ignored when GENESIS_LLM_PROVIDER=groq


# ── Counterfactual Branch ──────────────────────────────────────────────

class CounterfactualBranch(BaseModel):
    """A shadow timeline created by editing a past decision.

    The branch contains the edited decision plus speculative re-executions
    of all causally downstream decisions. The user can then PROMOTE the
    branch to reality (replacing the canonical timeline from the edit point).
    """
    id: str = Field(default_factory=lambda: f"b_{uuid4().hex[:12]}")
    organism_id: str
    edited_decision_id: str
    edited_decision: Decision
    downstream_replays: list[Decision] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    summary: str = ""  # LLM-written summary of how this timeline differs

    promoted: bool = False  # True if user promoted this to canonical reality


# ── Meta-Decision (the organism thinking about its thinking) ───────────

class MetaDecision(BaseModel):
    """A reflection on a Decision. The organism evaluating its own reasoning.

    This is the atom of meta-cognition. After each real Decision, the critic
    asks: 'Was my reasoning sound? What should I do differently next time?'
    MetaDecisions are linked to Decisions and accumulate into a meta-cognitive
    history that drives reasoning strategy selection.
    """
    id: str = Field(default_factory=lambda: f"md_{uuid4().hex[:12]}")
    decision_id: str = Field(..., description="The Decision being evaluated.")
    organism_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Critic evaluation
    reasoning_quality: float = Field(
        0.5, description="0.0–1.0 how logically sound the reasoning was."
    )
    attention_gaps: list[str] = Field(
        default_factory=list,
        description="Context the organism should have noticed but didn't."
    )
    action_efficiency: float = Field(
        0.5, description="0.0–1.0 was there a better tool/action available?"
    )
    repeated_mistake: bool = Field(
        False, description="True if this matches a pattern from past failures."
    )

    # Meta-learning output
    lesson: str = Field("", description="Natural-language insight about reasoning.")
    recommended_strategy: Optional[str] = Field(
        None, description="ReasoningStrategy name to try next for similar perceptions."
    )
    strategy_used: Optional[str] = Field(
        None, description="ReasoningStrategy ID that was active during the decision."
    )
    strategy_performance_delta: float = Field(
        0.0, description="-1.0 to 1.0: how much this strategy helped vs. baseline."
    )
    confidence: float = Field(0.5, description="Critic confidence in its evaluation.")


# ── Long-Term Memory (Module 2) ──────────────────────────────────────────

class LongTermMemory(BaseModel):
    """A durable memory shared across organisms and benchmark runs.

    Learned patterns live inside one organism. LongTermMemory is the next
    layer: reusable experience that future organisms can retrieve before
    reasoning, even if they were born later.
    """
    id: str = Field(default_factory=lambda: f"mem_{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    scope: str = "global"  # global | organism | benchmark | curriculum
    kind: str = "lesson"   # lesson | pattern | benchmark_result | failure | curriculum
    text: str
    tags: list[str] = Field(default_factory=list)
    organism_id: Optional[str] = None
    benchmark_id: Optional[str] = None
    source_decision_id: Optional[str] = None
    source_meta_decision_id: Optional[str] = None
    source_run_id: Optional[str] = None
    score: float = 0.5
    use_count: int = 0
    last_used_at: Optional[datetime] = None
