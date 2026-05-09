"""FastAPI routes for Genesis. Mount via:

    from backend.genesis.api import router as genesis_router
    app.include_router(genesis_router)

Endpoints:
  GET    /api/genesis/status                            live runtime health snapshot
  POST   /api/genesis/population/start                  start an evolution run
  GET    /api/genesis/population                        list all runs
  GET    /api/genesis/population/{run_id}               get one run
  POST   /api/genesis/population/{run_id}/stop          stop a running evolution
  DELETE /api/genesis/population/{run_id}               delete a run
  POST   /api/genesis/seed                              create organism from intent
  GET    /api/genesis/organisms                         list all organisms
  GET    /api/genesis/organisms/{id}                    one organism
  DELETE /api/genesis/organisms/{id}                    let it die
  POST   /api/genesis/organisms/{id}/perceive           feed a perception event
  POST   /api/genesis/organisms/{id}/dream              run a dreaming cycle
  GET    /api/genesis/organisms/{id}/causality          full causal graph
  POST   /api/genesis/organisms/{id}/edit/{decision_id} retroactively edit a decision
  POST   /api/genesis/organisms/{id}/branches/{bid}/promote  promote a branch
  GET    /api/genesis/organisms/{id}/branches           list counterfactual branches
"""

from __future__ import annotations

import secrets
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from . import approvals, autonomous_operator, body, capabilities, causality, collaboration, connectors, dreams, events, governance, homeostasis, intelligence, lifecycle, living_systems, long_term, memory, metabolism, metacognition, nervous_system, population, product_core, reliability, runtime, self_improvement, store, tool_sandbox, world_model
from backend.shared.config import settings

router = APIRouter(prefix="/api/genesis", tags=["genesis"])


def _bearer_token(authorization: str) -> str:
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def require_api_token(
    x_genesis_token: str = Header(default=""),
    x_genesis_session: str = Header(default=""),
    authorization: str = Header(default=""),
) -> None:
    if not settings.GENESIS_REQUIRE_API_TOKEN:
        return
    if not settings.GENESIS_API_TOKEN or not secrets.compare_digest(
        x_genesis_token,
        settings.GENESIS_API_TOKEN,
    ):
        session_token = x_genesis_session or _bearer_token(authorization)
        if session_token and long_term.validate_session_token(session_token):
            return
        raise HTTPException(401, "valid X-Genesis-Token or Genesis session required")


# ── Request models ─────────────────────────────────────────────────────

class SeedRequest(BaseModel):
    goal: str = Field(..., description="Natural-language intent.")
    name: str = ""
    constraints: list[str] = []
    forbidden: list[str] = []
    success_signals: list[str] = []
    # Phase 1 additions
    inherit_from: list[str] = []
    inherit_from_organisms: list[str] = []
    max_inherited_skills: int = 5
    mcp_servers: list[dict] = []  # raw dicts → MCPServerSpec at construction


class PerceiveRequest(BaseModel):
    perception: dict[str, Any]


class EditRequest(BaseModel):
    new_action: dict | None = None
    new_trigger: dict | None = None
    new_reasoning: str | None = None


class DreamRequest(BaseModel):
    n: int | None = None


class PerceptionSourceRequest(BaseModel):
    kind: str  # "interval" | "http_poll" | "webhook"
    type: str = "event"
    interval_s: int = 60
    url: str | None = None
    method: str | None = "GET"
    headers: dict | None = None
    payload: dict | None = None


# ── Routes ─────────────────────────────────────────────────────────────

@router.post("/seed", dependencies=[Depends(require_api_token)])
async def seed(req: SeedRequest):
    from .skills import inherit as _inherit
    from .types import MCPServerSpec

    inherited_refs, parent_orgs, compiled_mcp_specs, inherited_strategies = _inherit.resolve_seed_inheritance(
        inherit_from=req.inherit_from or None,
        inherit_from_organisms=req.inherit_from_organisms or None,
        max_inherited_skills=req.max_inherited_skills,
    )
    mcp_specs = [MCPServerSpec(**d) for d in (req.mcp_servers or [])]
    # Phase 4: Merge compiled skill MCP servers
    mcp_specs.extend(compiled_mcp_specs)

    org = runtime.seed(
        intent_goal=req.goal, name=req.name,
        constraints=req.constraints, forbidden=req.forbidden,
        success_signals=req.success_signals,
    )
    org.inherited_skills = inherited_refs
    org.parent_organisms = parent_orgs
    org.mcp_servers = mcp_specs

    # Phase 5A: seed default reasoning strategies
    metacognition.seed_default_strategies(org)

    # Phase 5A: merge inherited strategies from ancestors
    if inherited_strategies:
        existing_names = {s.name for s in org.reasoning_strategies}
        for s in inherited_strategies:
            if s.name not in existing_names:
                org.reasoning_strategies.append(s)
                existing_names.add(s.name)
            else:
                # Merge success rates: take the better one
                for existing in org.reasoning_strategies:
                    if existing.name == s.name:
                        if s.success_rate > existing.success_rate:
                            existing.success_rate = s.success_rate
                            existing.best_for = list(set(existing.best_for + s.best_for))
                        break

    store.save_organism(org)

    await events.emit("organism.seeded", {
        "organism_id": org.id,
        "organism": org.model_dump(mode="json"),
    })
    return {"organism": org.model_dump(mode="json")}


@router.get("/organisms")
async def list_organisms(
    q: str = "",
    limit: int = 100,
    offset: int = 0,
):
    orgs = store.list_organisms()
    if q.strip():
        needle = q.strip().lower()
        orgs = [
            org for org in orgs
            if needle in " ".join([
                org.id,
                org.name or "",
                org.intent.goal,
                " ".join(org.intent.constraints or []),
            ]).lower()
        ]
    total = len(orgs)
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    orgs = orgs[offset:offset + limit]
    return {
        "organisms": [o.model_dump(mode="json") for o in orgs],
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        },
    }


@router.get("/organisms/{organism_id}")
async def get_organism(organism_id: str):
    org = store.load_organism(organism_id)
    if not org:
        raise HTTPException(404, f"organism {organism_id} not found")
    decisions = store.all_decisions(organism_id)
    return {
        "organism": org.model_dump(mode="json"),
        "decision_count": len(decisions),
        "real_decisions": sum(1 for d in decisions if not d.is_dream and not d.shadow_branch),
        "dream_decisions": sum(1 for d in decisions if d.is_dream),
        "shadow_decisions": sum(1 for d in decisions if d.shadow_branch),
    }


@router.delete("/organisms/{organism_id}", dependencies=[Depends(require_api_token)])
async def kill_organism(organism_id: str):
    org = store.load_organism(organism_id)
    if not org:
        raise HTTPException(404, f"organism {organism_id} not found")

    # Phase 1 — distill organism's life into a Skill before death
    from .skills import distill as _distill
    try:
        new_skill_id = await _distill.distill(organism_id)
    except Exception as e:
        import logging
        logging.getLogger("genesis.api").warning(
            f"distillation failed for {organism_id}: {e}"
        )
        new_skill_id = None

    base = Path(store._BASE) / organism_id  # noqa: SLF001
    if base.exists():
        shutil.rmtree(base)
    await events.emit("organism.died", {
        "organism_id": organism_id,
        "patterns_donated": org.learned_patterns,
        "distilled_skill_id": new_skill_id,
    })
    if new_skill_id:
        await events.emit("organism.distilled", {
            "organism_id": organism_id, "skill_id": new_skill_id,
        })
    return {"died": organism_id,
            "patterns_donated": org.learned_patterns,
            "distilled_skill_id": new_skill_id}


@router.post("/organisms/{organism_id}/perceive", dependencies=[Depends(require_api_token)])
async def perceive(organism_id: str, req: PerceiveRequest):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    decision = await runtime.perceive(
        organism_id, req.perception,
        event_callback=events.make_callback(),
    )
    return {"decision": decision.model_dump(mode="json")}


@router.post("/organisms/{organism_id}/dream", dependencies=[Depends(require_api_token)])
async def dream(organism_id: str, req: DreamRequest):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    perceptions = await dreams.imagine(
        organism_id, n=req.n,
        event_callback=events.make_callback(),
    )
    return {"imagined_count": len(perceptions), "perceptions": perceptions}


@router.get("/organisms/{organism_id}/causality")
async def get_causality(organism_id: str, include_dreams: bool = True,
                        include_shadows: bool = True):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return causality.graph_view(
        organism_id,
        include_dreams=include_dreams,
        include_shadows=include_shadows,
    )


@router.post("/organisms/{organism_id}/edit/{decision_id}", dependencies=[Depends(require_api_token)])
async def edit_decision(organism_id: str, decision_id: str, req: EditRequest):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    if not store.load_decision(organism_id, decision_id):
        raise HTTPException(404, f"decision {decision_id} not found")
    await events.emit("organism.edited", {
        "organism_id": organism_id, "decision_id": decision_id,
        "new_action": req.new_action, "new_trigger": req.new_trigger,
    })
    branch = await causality.edit_and_replay(
        organism_id, decision_id,
        new_action=req.new_action, new_trigger=req.new_trigger,
        new_reasoning=req.new_reasoning,
    )
    await events.emit("organism.branch_created", {
        "organism_id": organism_id,
        "branch": branch.model_dump(mode="json"),
    })
    return {"branch": branch.model_dump(mode="json")}


@router.post("/organisms/{organism_id}/branches/{branch_id}/promote", dependencies=[Depends(require_api_token)])
async def promote_branch(organism_id: str, branch_id: str):
    if not store.load_branch(organism_id, branch_id):
        raise HTTPException(404, f"branch {branch_id} not found")
    result = await causality.promote_branch(organism_id, branch_id)
    await events.emit("organism.branch_promoted", {
        "organism_id": organism_id, "branch_id": branch_id, **result,
    })
    return result


@router.get("/lifecycle/status")
async def lifecycle_status():
    return lifecycle.status()


@router.post("/organisms/{organism_id}/sources", dependencies=[Depends(require_api_token)])
async def add_perception_source(organism_id: str, req: PerceptionSourceRequest):
    org = store.load_organism(organism_id)
    if not org:
        raise HTTPException(404, f"organism {organism_id} not found")
    src = req.model_dump(exclude_none=True)
    org.perception_sources.append(src)
    store.save_organism(org)
    # supervisor will mint webhook tokens & spawn polling on next reconcile
    return {"ok": True, "sources": org.perception_sources}


@router.delete("/organisms/{organism_id}/sources/{index}", dependencies=[Depends(require_api_token)])
async def remove_perception_source(organism_id: str, index: int):
    org = store.load_organism(organism_id)
    if not org:
        raise HTTPException(404, f"organism {organism_id} not found")
    if index < 0 or index >= len(org.perception_sources):
        raise HTTPException(404, "source index out of range")
    removed = org.perception_sources.pop(index)
    store.save_organism(org)
    return {"removed": removed, "sources": org.perception_sources}


@router.post("/webhook/{token}")
async def webhook_deliver(token: str, body: dict):
    try:
        return await lifecycle.deliver_webhook(token, body)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.get("/organisms/{organism_id}/branches")
async def list_branches(organism_id: str):
    return {
        "branches": [b.model_dump(mode="json")
                     for b in store.list_branches(organism_id)]
    }


# ── Skill Library ───────────────────────────────────────────────────────

@router.get("/skills")
async def list_skills():
    from .skills import pool as _pool
    return {"skills": _pool.list_summaries()}


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str):
    from .skills import pool as _pool
    s = _pool.load(skill_id)
    if not s:
        raise HTTPException(404, f"skill {skill_id} not found")
    return {
        "skill_id": s.skill_id, "name": s.name, "description": s.description,
        "distilled_at": s.distilled_at.isoformat(),
        "parent_organisms": s.parent_organisms, "parent_skills": s.parent_skills,
        "generation": s.generation, "fitness_at_death": s.fitness_at_death,
        "n_decisions_distilled": s.n_decisions_distilled,
        "trigger_patterns": s.trigger_patterns, "forbidden_patterns": s.forbidden_patterns,
        "body": s.body,
    }


@router.get("/skills/{skill_id}/lineage")
async def get_skill_lineage(skill_id: str):
    from .skills import pool as _pool
    seen: set[str] = set()
    frontier = [skill_id]
    nodes: list[dict] = []
    edges: list[dict] = []
    while frontier:
        sid = frontier.pop()
        if sid in seen:
            continue
        seen.add(sid)
        s = _pool.load(sid)
        if not s:
            continue
        nodes.append({"id": sid, "kind": "skill", "name": s.name,
                      "generation": s.generation,
                      "fitness_at_death": s.fitness_at_death})
        for parent in s.parent_skills:
            edges.append({"source": parent, "target": sid, "kind": "skill_parent"})
            frontier.append(parent)
        for org in s.parent_organisms:
            org_node_id = f"org:{org}"
            if org_node_id not in seen:
                seen.add(org_node_id)
                nodes.append({"id": org_node_id, "kind": "organism", "name": org})
            edges.append({"source": org_node_id, "target": sid, "kind": "distilled_from"})
    return {"nodes": nodes, "edges": edges}


@router.delete("/skills/{skill_id}", dependencies=[Depends(require_api_token)])
async def delete_skill(skill_id: str):
    from .skills import pool as _pool
    if not _pool.delete(skill_id):
        raise HTTPException(404, f"skill {skill_id} not found")
    return {"deleted": skill_id}


# ── MCP endpoints ───────────────────────────────────────────────────────

@router.post("/organisms/{organism_id}/mcp/attach", dependencies=[Depends(require_api_token)])
async def attach_mcp(organism_id: str, spec: dict):
    org = store.load_organism(organism_id)
    if not org:
        raise HTTPException(404, f"organism {organism_id} not found")
    from .types import MCPServerSpec
    parsed = MCPServerSpec(**spec)
    org.mcp_servers = [s for s in org.mcp_servers if s.name != parsed.name] + [parsed]
    store.save_organism(org)
    from .mcp import client as _mc
    await _mc.pool.ensure_organism(organism_id, [parsed])
    return {"ok": True, "mcp_servers": [s.model_dump() for s in org.mcp_servers]}


@router.delete("/organisms/{organism_id}/mcp/{server_name}", dependencies=[Depends(require_api_token)])
async def detach_mcp(organism_id: str, server_name: str):
    org = store.load_organism(organism_id)
    if not org:
        raise HTTPException(404, f"organism {organism_id} not found")
    before = len(org.mcp_servers)
    org.mcp_servers = [s for s in org.mcp_servers if s.name != server_name]
    if len(org.mcp_servers) == before:
        raise HTTPException(404, f"server {server_name} not attached")
    store.save_organism(org)
    return {"ok": True, "remaining": [s.model_dump() for s in org.mcp_servers]}


@router.get("/mcp/global")
async def mcp_global_status():
    from .mcp import client as _mc, catalog as _cat
    return {
        "configured": [s.model_dump() for s in _cat.load_global_specs()],
        "runtime": await _mc.pool.status(),
    }


@router.post("/mcp/global/reload", dependencies=[Depends(require_api_token)])
async def mcp_global_reload():
    from .mcp import client as _mc, catalog as _cat
    specs = _cat.load_global_specs()
    await _mc.pool.ensure_global(specs)
    return {"reloaded": len(specs)}


# ── Phase 4: Embodiment — Compiled Skills ──────────────────────────────

@router.get("/compiled")
async def list_compiled_skills():
    """List all compiled skill MCP servers."""
    from .skills import compiler
    return {"compiled_skills": compiler.list_compiled()}


@router.post("/skills/{skill_id}/compile", dependencies=[Depends(require_api_token)])
async def compile_skill(skill_id: str):
    """Compile a narrative skill into an executable MCP server."""
    from .skills import pool as _pool, compiler
    skill = _pool.load(skill_id)
    if not skill:
        raise HTTPException(404, f"skill {skill_id} not found")
    compiled_path = await compiler.compile_skill(skill)
    if not compiled_path:
        raise HTTPException(500, "compilation failed")
    return {"ok": True, "skill_id": skill_id, "compiled_path": compiled_path}


@router.get("/sandbox/status")
async def sandbox_status():
    """Get health status of all sandboxed compiled skill processes."""
    from .skills.sandbox import sandbox_manager
    return sandbox_manager.status()


@router.post("/sandbox/health-check", dependencies=[Depends(require_api_token)])
async def sandbox_health_check():
    """Run health check on all sandboxed processes, auto-restart if needed."""
    from .skills.sandbox import sandbox_manager
    results = await sandbox_manager.health_check()
    return {"results": results}


# ── Phase 5A: Meta-Cognition ───────────────────────────────────────────

@router.get("/organisms/{organism_id}/metacognition")
async def get_metacognition(organism_id: str):
    """Get the full meta-cognitive state: strategy library, critic history, aggregates."""
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return metacognition.metacognition_summary(organism_id)


class StrategySwitchRequest(BaseModel):
    strategy_name: str = Field(..., description="Name of the strategy to activate.")


@router.post("/organisms/{organism_id}/metacognition/strategy", dependencies=[Depends(require_api_token)])
async def switch_strategy(organism_id: str, req: StrategySwitchRequest):
    """Manually switch the active reasoning strategy."""
    org = store.load_organism(organism_id)
    if not org:
        raise HTTPException(404, f"organism {organism_id} not found")
    for s in org.reasoning_strategies:
        if s.name == req.strategy_name:
            org.active_strategy_id = s.id
            store.save_organism(org)
            return {"ok": True, "active_strategy": s.name, "id": s.id}
    raise HTTPException(404, f"strategy '{req.strategy_name}' not found in organism's library")


class MetaCognitionToggle(BaseModel):
    enabled: bool


@router.post("/organisms/{organism_id}/metacognition/toggle", dependencies=[Depends(require_api_token)])
async def toggle_metacognition(organism_id: str, req: MetaCognitionToggle):
    """Enable or disable meta-cognitive critic for an organism."""
    org = store.load_organism(organism_id)
    if not org:
        raise HTTPException(404, f"organism {organism_id} not found")
    org.meta_cognition_enabled = req.enabled
    store.save_organism(org)
    return {"ok": True, "meta_cognition_enabled": org.meta_cognition_enabled}


# ── Module 2: Memory / Curriculum ───────────────────────────────────────

class MemoryCreateRequest(BaseModel):
    text: str
    kind: str = "lesson"
    scope: str = "global"
    tags: list[str] = []
    organism_id: str | None = None
    benchmark_id: str | None = None
    score: float = Field(0.5, ge=0.0, le=1.0)


@router.get("/memory")
async def list_memory(
    limit: int = 100,
    scope: str | None = None,
    benchmark_id: str | None = None,
):
    """List durable Module 2 memories available to future organisms."""
    return {
        "memories": [
            item.model_dump(mode="json")
            for item in memory.list_memories(
                limit=limit,
                scope=scope,
                benchmark_id=benchmark_id,
            )
        ]
    }


@router.get("/memory/search")
async def search_memory(q: str = "", limit: int = 20):
    """Search durable memories by simple token overlap."""
    query_tokens = set(q.lower().split())
    items = memory.list_memories(limit=500)
    if query_tokens:
        items = [
            item for item in items
            if query_tokens & set((item.text + " " + " ".join(item.tags)).lower().split())
        ]
    return {"memories": [item.model_dump(mode="json") for item in items[:limit]]}


@router.post("/memory", dependencies=[Depends(require_api_token)])
async def create_memory(req: MemoryCreateRequest):
    """Manually add a durable memory for future organisms."""
    item = memory.remember(
        req.text,
        kind=req.kind,
        scope=req.scope,
        tags=req.tags,
        organism_id=req.organism_id,
        benchmark_id=req.benchmark_id,
        score=req.score,
    )
    if not item:
        raise HTTPException(400, "memory text is required")
    await events.emit("memory.created", {"memory": item.model_dump(mode="json")})
    return {"memory": item.model_dump(mode="json")}


@router.get("/curriculum")
async def get_curriculum():
    """Get Module 2 curriculum state and next recommended benchmark."""
    return memory.curriculum()


# ── Module 3: Sandboxed Tool Use ────────────────────────────────────────

class ToolSandboxRunRequest(BaseModel):
    code: str = Field(..., description="Small analysis-only Python program. Assign final output to `result`.")
    input_data: dict[str, Any] = Field(default_factory=dict)
    purpose: str = ""
    organism_id: str | None = None
    timeout_s: int = Field(8, ge=1, le=30)
    memory_mb: int = Field(128, ge=32, le=512)


@router.get("/tools/sandbox/runs")
async def list_tool_sandbox_runs(limit: int = 50):
    """List Module 3 sandbox execution audit records."""
    return {"runs": tool_sandbox.list_runs(limit=limit)}


@router.get("/tools/sandbox/runs/{run_id}")
async def get_tool_sandbox_run(run_id: str):
    run = tool_sandbox.get_run(run_id)
    if not run:
        raise HTTPException(404, f"sandbox run {run_id} not found")
    return run


@router.post("/tools/sandbox/run", dependencies=[Depends(require_api_token)])
async def run_tool_sandbox(req: ToolSandboxRunRequest):
    """Execute bounded Python in the Module 3 sandbox."""
    run = await tool_sandbox.run_python(
        code=req.code,
        input_data=req.input_data,
        organism_id=req.organism_id,
        purpose=req.purpose,
        timeout_s=req.timeout_s,
        memory_mb=req.memory_mb,
    )
    await events.emit("tool_sandbox.completed", {"run": run})
    return {"run": run}


# ── Module 4: Multi-Agent Collaboration ─────────────────────────────────

class DebateAgentRequest(BaseModel):
    id: str
    name: str
    stance: str


class DebateStartRequest(BaseModel):
    topic: str = Field(..., description="Question or decision the agents should debate.")
    context: dict[str, Any] = Field(default_factory=dict)
    agents: list[DebateAgentRequest] | None = None


@router.get("/collaboration/debates")
async def list_collaboration_debates(limit: int = 30):
    """List Module 4 multi-agent debate runs."""
    return {"debates": collaboration.list_debates(limit=limit)}


@router.get("/collaboration/debates/{debate_id}")
async def get_collaboration_debate(debate_id: str):
    debate = collaboration.get_debate(debate_id)
    if not debate:
        raise HTTPException(404, f"debate {debate_id} not found")
    return {"debate": debate}


@router.post("/collaboration/debates", dependencies=[Depends(require_api_token)])
async def start_collaboration_debate(req: DebateStartRequest):
    """Run an auditable Module 4 proposal → critique → synthesis debate."""
    debate = await collaboration.run_debate(
        topic=req.topic,
        context=req.context,
        agents=[a.model_dump() for a in req.agents] if req.agents else None,
        event_callback=events.emit,
    )
    if debate.get("status") == "error":
        raise HTTPException(500, debate.get("error") or "debate failed")
    return {"debate": debate}


# ── Module 5: Strict Self-Improvement Gates ─────────────────────────────

class SelfImprovementRunRequest(BaseModel):
    objective: str = Field(..., description="Capability Genesis should try to improve.")
    context: dict[str, Any] = Field(default_factory=dict)
    candidate: dict[str, Any] | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    gates: dict[str, Any] | None = None


@router.get("/self-improvement/runs")
async def list_self_improvement_runs(limit: int = 30):
    """List Module 5 self-improvement evaluation runs."""
    return {"runs": self_improvement.list_runs(limit=limit)}


@router.get("/self-improvement/runs/{run_id}")
async def get_self_improvement_run(run_id: str):
    run = self_improvement.get_run(run_id)
    if not run:
        raise HTTPException(404, f"self-improvement run {run_id} not found")
    return {"run": run}


@router.post("/self-improvement/runs", dependencies=[Depends(require_api_token)])
async def start_self_improvement_run(req: SelfImprovementRunRequest):
    """Create a self-improvement candidate and evaluate strict promotion gates."""
    run = await self_improvement.run_improvement_cycle(
        objective=req.objective,
        context=req.context,
        candidate=req.candidate,
        evidence=req.evidence,
        gates=req.gates,
        event_callback=events.emit,
    )
    if run.get("status") == "error":
        raise HTTPException(500, run.get("error") or "self-improvement run failed")
    return {"run": run}


# ── Module 6: Persistent Autonomous Operator ────────────────────────────

class OperatorCreateRequest(BaseModel):
    goal: str = Field(..., description="Persistent goal the operator should pursue.")
    name: str = "autonomous_operator"
    cadence_s: int = Field(300, ge=10, le=86400)
    max_ticks: int = Field(25, ge=1, le=1000)
    constraints: list[str] = Field(default_factory=list)
    start_active: bool = True


class NervousTickRequest(BaseModel):
    stimulus: dict[str, Any] = Field(default_factory=dict)


class IntentionCompleteRequest(BaseModel):
    result: dict[str, Any] = Field(default_factory=dict)


class AutonomyCycleRequest(BaseModel):
    stimulus: dict[str, Any] = Field(default_factory=dict)


class BodySensorAttachRequest(BaseModel):
    recommendation_id: str = "rec_interval_heartbeat"


class MetabolismRecoverRequest(BaseModel):
    depth: str = "rest"


class ImmuneResponseRequest(BaseModel):
    action: str = "auto"


class ReproductionRequest(BaseModel):
    mutation: str = "conservative"


class SelectionRoundRequest(BaseModel):
    pressure: str = "balanced"
    limit: int = Field(80, ge=1, le=200)


class GoalRefinementRequest(BaseModel):
    focus: str = "auto"


class CulturePulseRequest(BaseModel):
    focus: str = "norms"


class BudgetPulseRequest(BaseModel):
    focus: str = "balanced"


class WorldSandboxPulseRequest(BaseModel):
    scenario: str = "current_tasks"


class ApprovalCreateRequest(BaseModel):
    title: str = Field(..., description="Human-readable permission request title.")
    action_type: str = Field("external_api", description="Action family being requested.")
    reason: str = Field(..., description="Why the agent believes this action is needed.")
    requested_by: str = "genesis"
    source: str = "manual"
    risk_level: str = Field("high", description="low, medium, high, or critical")
    payload: dict[str, Any] = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=list)
    expires_in_minutes: int = Field(1440, ge=1, le=43200)
    required_approvals: int | None = Field(None, ge=1, le=5)


class ApprovalDecisionRequest(BaseModel):
    reviewed_by: str = "human"
    note: str = ""


class ApprovalExecuteRequest(BaseModel):
    executed_by: str = "genesis"
    grant_ttl_minutes: int = Field(60, ge=1, le=10080)
    grant_max_uses: int = Field(3, ge=1, le=1000)
    require_confirmation: bool = False


class ApprovalConfirmExecutionRequest(BaseModel):
    confirmed_by: str = "human"
    confirmation_phrase: str
    note: str = ""


class ApprovalBreakGlassRequest(BaseModel):
    invoked_by: str = "human"
    justification: str
    grant_ttl_minutes: int = Field(15, ge=1, le=15)


class PermissionCheckRequest(BaseModel):
    grant_id: str
    permission: str
    action_type: str | None = None
    scope: str | None = None
    consume: bool = False
    actor: str = "genesis"


class PermissionSimulateRequest(BaseModel):
    grant_id: str
    permission: str
    action_type: str
    scope: str = "*"
    actor: str = "genesis"
    payload: dict[str, Any] = Field(default_factory=dict)


class PermissionRevokeRequest(BaseModel):
    revoked_by: str = "human"
    note: str = ""


class ConnectorRunRequest(BaseModel):
    adapter_id: str
    grant_id: str
    scope: str | None = None
    actor: str = "genesis_connector"
    payload: dict[str, Any] = Field(default_factory=dict)


class ConnectorProbeRequest(BaseModel):
    adapter_id: str
    scope: str | None = None
    live: bool = False


class GovernanceRiskRequest(BaseModel):
    action_type: str = "external_api"
    payload: dict[str, Any] = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=list)


class IntentBindRequest(BaseModel):
    user_intent: str
    bound_by: str = "human"


class LockdownRequest(BaseModel):
    locked: bool
    reason: str = ""
    actor: str = "human"


class TaskGraphCreateRequest(BaseModel):
    goal: str
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    owner: str = "genesis"


class TaskCompleteRequest(BaseModel):
    result: str = ""


class CapabilityResearchRequest(BaseModel):
    question: str
    sources: list[dict[str, Any]] = Field(default_factory=list)


class GoalContractRequest(BaseModel):
    goal: str
    success_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)


class DataClassifyRequest(BaseModel):
    name: str
    sample: str = ""
    declared_level: str = "internal"


class FeedbackRequest(BaseModel):
    target: str
    rating: int = Field(5, ge=1, le=5)
    note: str = ""


class ReleaseRequest(BaseModel):
    version: str
    changes: list[str] = Field(default_factory=list)


class ReliabilityMissionRequest(BaseModel):
    goal: str
    constraints: list[str] = Field(default_factory=list)


class ReliabilityBenchmarkRequest(BaseModel):
    name: str = "Reliability pack"
    focus: list[str] = Field(default_factory=list)


class WorkstyleMemoryRequest(BaseModel):
    preference: str
    value: str
    editable: bool = True


class WorldEntityRequest(BaseModel):
    name: str
    entity_type: str = "concept"
    attributes: dict[str, Any] = Field(default_factory=dict)


class WorldBeliefRequest(BaseModel):
    subject: str = "general"
    claim: str
    confidence: float = Field(0.5, ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)


class WorldEvidenceRequest(BaseModel):
    source: str = "local"
    summary: str
    kind: str = "observation"
    payload: dict[str, Any] = Field(default_factory=dict)


class WorldLearningDrillRequest(BaseModel):
    goal: str = "Improve Genesis mission planning through grounded learning."


class AuthBootstrapRequest(BaseModel):
    username: str = "owner"
    password: str = Field(..., min_length=10)
    display_name: str = "Genesis Operator"


class AuthLoginRequest(BaseModel):
    username: str
    password: str
    ttl_hours: int = Field(24, ge=1, le=720)


class ReconciliationRepairRequest(BaseModel):
    confirm: bool = False


@router.get("/long-term/status")
async def long_term_status():
    """Phase 6 long-term database/auth readiness."""
    return long_term.status()


@router.get("/long-term/reconciliation")
async def long_term_reconciliation():
    return store.reconcile_long_term(repair=False)


@router.post("/long-term/reconciliation/repair", dependencies=[Depends(require_api_token)])
async def repair_long_term_reconciliation(
    req: ReconciliationRepairRequest = Body(default_factory=ReconciliationRepairRequest),
):
    if not req.confirm:
        raise HTTPException(
            409,
            "Set confirm=true to repair the long-term database mirror from the JSON source of truth.",
        )
    return store.reconcile_long_term(repair=True)


@router.post("/auth/bootstrap")
async def auth_bootstrap(req: AuthBootstrapRequest):
    try:
        user = long_term.bootstrap_user(req.username, req.password, req.display_name)
    except ValueError as exc:
        raise HTTPException(409 if "already exists" in str(exc) else 400, str(exc)) from exc
    await events.emit("auth.bootstrap", {"user": user})
    return {"user": user, "status": long_term.status()}


@router.post("/auth/login")
async def auth_login(req: AuthLoginRequest):
    session = long_term.login(req.username, req.password, ttl_hours=req.ttl_hours)
    if not session:
        raise HTTPException(401, "invalid username or password")
    await events.emit("auth.login", {"user": session["user"], "session": session["session"]})
    return session


@router.get("/auth/me")
async def auth_me(
    x_genesis_session: str = Header(default=""),
    authorization: str = Header(default=""),
):
    token = x_genesis_session or _bearer_token(authorization)
    session = long_term.validate_session_token(token)
    if not session:
        raise HTTPException(401, "valid Genesis session required")
    return session


@router.post("/auth/logout")
async def auth_logout(
    x_genesis_session: str = Header(default=""),
    authorization: str = Header(default=""),
):
    token = x_genesis_session or _bearer_token(authorization)
    if not token:
        raise HTTPException(401, "valid Genesis session required")
    revoked = long_term.revoke_session(token)
    await events.emit("auth.logout", {"revoked": revoked})
    return {"revoked": revoked, "status": long_term.status()}


@router.get("/operators")
async def list_operators(limit: int = 30):
    """List Module 6 persistent autonomous operators."""
    return {
        "operators": autonomous_operator.list_operators(limit=limit),
        "status": autonomous_operator.status(),
    }


@router.get("/operators/{operator_id}")
async def get_operator(operator_id: str):
    operator = autonomous_operator.get_operator(operator_id)
    if not operator:
        raise HTTPException(404, f"operator {operator_id} not found")
    return {"operator": operator}


@router.get("/approvals")
async def list_approvals(status: str | None = None, limit: int = 50):
    """List Module 7 human approval requests and permission gate status."""
    return {
        "approvals": approvals.list_requests(status=status, limit=limit),
        "summary": approvals.summary(),
    }


@router.get("/permissions/grants")
async def list_permission_grants(status: str | None = None, limit: int = 50):
    """List Module 8 scoped permission grants minted from approved requests."""
    return {
        "grants": approvals.list_grants(status=status, limit=limit),
        "summary": approvals.summary(),
    }


@router.get("/connectors/adapters")
async def list_connector_adapters():
    """List Module 9 connector adapters guarded by Module 8 permission grants."""
    return {"adapters": connectors.list_adapters(), "summary": connectors.summary()}


@router.get("/connectors/configuration")
async def connector_configuration():
    """Show which real connectors are configured without exposing secrets."""
    return connectors.connector_configuration()


@router.post("/connectors/probe", dependencies=[Depends(require_api_token)])
async def probe_connector_adapter(req: ConnectorProbeRequest):
    """Run a safe connector preflight without minting a permission grant."""
    try:
        result = connectors.probe_adapter(
            adapter_id=req.adapter_id,
            scope=req.scope,
            live=req.live,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await events.emit("connector.probed", {"probe": result})
    return {"probe": result}


@router.get("/connectors/runs")
async def list_connector_runs(limit: int = 50):
    """List Module 9 permission-gated connector run records."""
    return {"runs": connectors.list_runs(limit=limit), "summary": connectors.summary()}


@router.get("/connectors/runs/{run_id}")
async def get_connector_run(run_id: str):
    run = connectors.get_run(run_id)
    if not run:
        raise HTTPException(404, f"connector run {run_id} not found")
    return {"run": run}


@router.get("/connectors/artifacts")
async def list_connector_artifacts(limit: int = 50):
    """List Module 10 local artifacts written by the permission-gated connector."""
    return {
        "artifacts": connectors.list_artifacts(limit=limit),
        "summary": connectors.summary(),
    }


@router.get("/permissions/grants/{grant_id}")
async def get_permission_grant(grant_id: str):
    grant = approvals.get_grant(grant_id)
    if not grant:
        raise HTTPException(404, f"permission grant {grant_id} not found")
    return {"grant": grant}


@router.get("/permissions/grants/{grant_id}/integrity")
async def verify_permission_grant_integrity(grant_id: str):
    result = approvals.verify_grant_integrity(grant_id)
    if not result:
        raise HTTPException(404, f"permission grant {grant_id} not found")
    await events.emit(
        "approval.integrity_verified" if result["integrity"].get("ok") else "approval.integrity_failed",
        {"integrity": result["integrity"]},
    )
    return result


@router.get("/approvals/integrity")
async def approval_integrity_report(limit: int = 50):
    report = approvals.integrity_report(limit=limit)
    await events.emit(
        "approval.integrity_verified" if report.get("ok") else "approval.integrity_failed",
        {"integrity": report},
    )
    return report


@router.get("/approvals/{approval_id}")
async def get_approval(approval_id: str):
    request = approvals.get_request(approval_id)
    if not request:
        raise HTTPException(404, f"approval {approval_id} not found")
    return {"approval": request}


@router.get("/approvals/{approval_id}/integrity")
async def verify_approval_integrity(approval_id: str):
    result = approvals.verify_approval_integrity(approval_id)
    if not result:
        raise HTTPException(404, f"approval {approval_id} not found")
    await events.emit(
        "approval.integrity_verified" if result["integrity"].get("ok") else "approval.integrity_failed",
        {"integrity": result["integrity"]},
    )
    return result


@router.get("/approvals/{approval_id}/policy")
async def get_approval_policy(approval_id: str):
    request = approvals.get_request(approval_id)
    if not request:
        raise HTTPException(404, f"approval {approval_id} not found")
    packet = approvals.policy_review_packet(request)
    await events.emit("approval.policy_evaluated", {"approval_id": approval_id, "policy": packet})
    return {"approval": request, "policy": packet}


@router.post("/approvals", dependencies=[Depends(require_api_token)])
async def create_approval(req: ApprovalCreateRequest):
    try:
        request = approvals.create_request(
            title=req.title,
            action_type=req.action_type,
            reason=req.reason,
            requested_by=req.requested_by,
            source=req.source,
            risk_level=req.risk_level,
            payload=req.payload,
            permissions=req.permissions,
            expires_in_minutes=req.expires_in_minutes,
            required_approvals=req.required_approvals,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await events.emit("approval.requested", {"approval": request})
    return {"approval": request}


@router.post("/approvals/{approval_id}/approve", dependencies=[Depends(require_api_token)])
async def approve_approval(approval_id: str, req: ApprovalDecisionRequest):
    try:
        request = approvals.approve_request(
            approval_id,
            reviewed_by=req.reviewed_by,
            note=req.note,
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if not request:
        raise HTTPException(404, f"approval {approval_id} not found")
    await events.emit("approval.approved", {"approval": request})
    return {"approval": request}


@router.post("/approvals/{approval_id}/break-glass", dependencies=[Depends(require_api_token)])
async def break_glass_approval(approval_id: str, req: ApprovalBreakGlassRequest):
    try:
        request = approvals.break_glass_request(
            approval_id,
            invoked_by=req.invoked_by,
            justification=req.justification,
            grant_ttl_minutes=req.grant_ttl_minutes,
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if not request:
        raise HTTPException(404, f"approval {approval_id} not found")
    await events.emit("approval.break_glass", {"approval": request})
    grant = (request.get("execution_result") or {}).get("permission_grant")
    if grant:
        await events.emit("permission.granted", {"grant": grant, "approval_id": approval_id})
    return {"approval": request}


@router.post("/approvals/{approval_id}/reject", dependencies=[Depends(require_api_token)])
async def reject_approval(approval_id: str, req: ApprovalDecisionRequest):
    try:
        request = approvals.reject_request(
            approval_id,
            reviewed_by=req.reviewed_by,
            note=req.note,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if not request:
        raise HTTPException(404, f"approval {approval_id} not found")
    await events.emit("approval.rejected", {"approval": request})
    return {"approval": request}


@router.post("/approvals/{approval_id}/execute", dependencies=[Depends(require_api_token)])
async def execute_approval(approval_id: str, req: ApprovalExecuteRequest):
    try:
        request = approvals.execute_request(
            approval_id,
            executed_by=req.executed_by,
            grant_ttl_minutes=req.grant_ttl_minutes,
            grant_max_uses=req.grant_max_uses,
            require_confirmation=req.require_confirmation,
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    if not request:
        raise HTTPException(404, f"approval {approval_id} not found")
    await events.emit("approval.executed", {"approval": request})
    grant = (request.get("execution_result") or {}).get("permission_grant")
    if grant:
        await events.emit("permission.granted", {"grant": grant, "approval_id": approval_id})
    return {"approval": request}


@router.post("/approvals/{approval_id}/confirm-execution", dependencies=[Depends(require_api_token)])
async def confirm_approval_execution(approval_id: str, req: ApprovalConfirmExecutionRequest):
    try:
        request = approvals.confirm_execution(
            approval_id,
            confirmed_by=req.confirmed_by,
            confirmation_phrase=req.confirmation_phrase,
            note=req.note,
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    if not request:
        raise HTTPException(404, f"approval {approval_id} not found")
    await events.emit("approval.confirmed", {"approval": request})
    return {"approval": request, "policy": request.get("policy_review")}


@router.post("/permissions/check", dependencies=[Depends(require_api_token)])
async def check_permission(req: PermissionCheckRequest):
    result = approvals.validate_grant(
        req.grant_id,
        permission=req.permission,
        action_type=req.action_type,
        scope=req.scope,
        consume=req.consume,
        actor=req.actor,
    )
    await events.emit(
        "permission.consumed" if result.get("ok") and req.consume else "permission.checked" if result.get("ok") else "permission.denied",
        {"result": result},
    )
    return result


@router.post("/permissions/simulate-action", dependencies=[Depends(require_api_token)])
async def simulate_permissioned_action(req: PermissionSimulateRequest):
    result = approvals.simulate_protected_action(
        grant_id=req.grant_id,
        permission=req.permission,
        action_type=req.action_type,
        scope=req.scope,
        actor=req.actor,
        payload=req.payload,
    )
    await events.emit("permission.consumed" if result.get("ok") else "permission.denied", {"result": result})
    if not result.get("ok"):
        raise HTTPException(403, result)
    return result


@router.post("/permissions/grants/{grant_id}/revoke", dependencies=[Depends(require_api_token)])
async def revoke_permission_grant(grant_id: str, req: PermissionRevokeRequest):
    grant = approvals.revoke_grant(
        grant_id,
        revoked_by=req.revoked_by,
        note=req.note,
    )
    if not grant:
        raise HTTPException(404, f"permission grant {grant_id} not found")
    await events.emit("permission.revoked", {"grant": grant})
    return {"grant": grant}


@router.post("/connectors/run", dependencies=[Depends(require_api_token)])
async def run_connector_adapter(req: ConnectorRunRequest):
    await events.emit("connector.started", {
        "adapter_id": req.adapter_id,
        "grant_id": req.grant_id,
        "scope": req.scope,
        "actor": req.actor,
    })
    try:
        run = connectors.run_adapter(
            adapter_id=req.adapter_id,
            grant_id=req.grant_id,
            scope=req.scope,
            actor=req.actor,
            payload=req.payload,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    status = run.get("status")
    if status == "complete":
        await events.emit("connector.completed", {"run": run})
        if run.get("adapter", {}).get("id") == "local_artifact_write":
            await events.emit("connector.artifact_written", {
                "run": run,
                "artifact": (run.get("result") or {}).get("output"),
            })
    elif status == "blocked":
        await events.emit("connector.blocked", {"run": run})
        raise HTTPException(403, run)
    elif status == "failed":
        await events.emit("connector.failed", {"run": run})
        raise HTTPException(500, run)
    return {"run": run}


# ── Module 14..23: Assurance and Operations ─────────────────────────────

@router.get("/governance/status")
async def governance_status():
    return governance.assurance_status()


@router.post("/governance/drill", dependencies=[Depends(require_api_token)])
async def run_governance_drill():
    result = governance.run_assurance_drill()
    await events.emit("governance.drill_completed", {"result": result})
    return result


@router.post("/governance/risk-score")
async def score_governance_risk(req: GovernanceRiskRequest):
    return governance.risk_score(
        action_type=req.action_type,
        payload=req.payload,
        permissions=req.permissions,
    )


@router.get("/governance/capabilities")
async def get_capability_registry():
    return governance.capability_registry()


@router.post("/governance/lockdown", dependencies=[Depends(require_api_token)])
async def set_governance_lockdown(req: LockdownRequest):
    state = governance.set_lockdown(
        locked=req.locked,
        reason=req.reason,
        actor=req.actor,
    )
    await events.emit("governance.lockdown_changed", {"lockdown": state})
    return {"lockdown": state}


@router.post("/governance/approvals/{approval_id}/bind-intent", dependencies=[Depends(require_api_token)])
async def bind_governance_intent(approval_id: str, req: IntentBindRequest):
    try:
        approval = governance.bind_intent(
            approval_id,
            user_intent=req.user_intent,
            bound_by=req.bound_by,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not approval:
        raise HTTPException(404, f"approval {approval_id} not found")
    await events.emit("governance.intent_bound", {"approval": approval})
    return {"approval": approval}


@router.get("/governance/approvals/{approval_id}/replay")
async def replay_governance_approval(approval_id: str):
    replay = governance.replay_approval(approval_id)
    if not replay:
        raise HTTPException(404, f"approval {approval_id} not found")
    await events.emit("governance.replay_completed", {"replay": replay})
    return {"replay": replay}


@router.post("/governance/approvals/{approval_id}/evidence", dependencies=[Depends(require_api_token)])
async def create_governance_evidence(approval_id: str):
    bundle = governance.create_evidence_bundle(approval_id)
    if not bundle:
        raise HTTPException(404, f"approval {approval_id} not found")
    await events.emit("governance.evidence_created", {"evidence": bundle})
    return {"evidence": bundle}


@router.get("/governance/evidence")
async def list_governance_evidence(limit: int = 20):
    return {"evidence": governance.list_evidence(limit=limit)}


@router.post("/governance/evaluations/run", dependencies=[Depends(require_api_token)])
async def run_governance_evaluation():
    result = governance.evaluation_monitor()
    await events.emit("governance.evaluation_completed", {"evaluation": result})
    return {"evaluation": result}


@router.get("/governance/production-readiness")
async def get_governance_production_readiness():
    return governance.production_readiness()


@router.get("/governance/accountability")
async def get_governance_accountability():
    return governance.accountability_dashboard()


# ── Module 24..33: Capability Growth ────────────────────────────────────

@router.get("/capabilities/status")
async def capability_status():
    return capabilities.capability_status()


@router.post("/capabilities/drill", dependencies=[Depends(require_api_token)])
async def run_capability_drill():
    result = capabilities.run_capability_drill()
    await events.emit("capability.drill_completed", {"result": result})
    return result


@router.post("/capabilities/task-graphs", dependencies=[Depends(require_api_token)])
async def create_capability_task_graph(req: TaskGraphCreateRequest):
    try:
        graph = capabilities.create_task_graph(goal=req.goal, tasks=req.tasks, owner=req.owner)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await events.emit("capability.task_graph_created", {"task_graph": graph})
    return {"task_graph": graph}


@router.post("/capabilities/task-graphs/{graph_id}/tasks/{task_id}/complete", dependencies=[Depends(require_api_token)])
async def complete_capability_task(graph_id: str, task_id: str, req: TaskCompleteRequest):
    try:
        graph = capabilities.complete_task(graph_id, task_id, result=req.result)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    if not graph:
        raise HTTPException(404, f"task graph {graph_id} not found")
    await events.emit("capability.task_completed", {"task_graph": graph, "task_id": task_id})
    return {"task_graph": graph}


@router.post("/capabilities/research", dependencies=[Depends(require_api_token)])
async def run_capability_research(req: CapabilityResearchRequest):
    try:
        result = capabilities.research_loop(question=req.question, sources=req.sources)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await events.emit("capability.research_completed", {"research": result})
    return {"research": result}


# ── Module 34..43: Product Intelligence and Release Management ──────────

@router.get("/intelligence/status")
async def intelligence_status():
    return intelligence.intelligence_status()


@router.post("/intelligence/drill", dependencies=[Depends(require_api_token)])
async def run_intelligence_drill():
    result = intelligence.run_intelligence_drill()
    await events.emit("intelligence.drill_completed", {"result": result})
    return result


@router.get("/intelligence/knowledge-graph")
async def build_intelligence_knowledge_graph():
    graph = intelligence.build_knowledge_graph()
    await events.emit("intelligence.knowledge_graph_built", {"knowledge_graph": graph})
    return {"knowledge_graph": graph}


@router.post("/intelligence/goal-contracts", dependencies=[Depends(require_api_token)])
async def create_intelligence_goal_contract(req: GoalContractRequest):
    try:
        contract = intelligence.create_goal_contract(
            goal=req.goal,
            success_criteria=req.success_criteria,
            constraints=req.constraints,
            forbidden=req.forbidden,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await events.emit("intelligence.goal_contract_created", {"goal_contract": contract})
    return {"goal_contract": contract}


@router.post("/intelligence/data/classify", dependencies=[Depends(require_api_token)])
async def classify_intelligence_data(req: DataClassifyRequest):
    classification = intelligence.classify_data(
        name=req.name,
        sample=req.sample,
        declared_level=req.declared_level,
    )
    await events.emit("intelligence.data_classified", {"classification": classification})
    return {"classification": classification}


@router.post("/intelligence/feedback", dependencies=[Depends(require_api_token)])
async def record_intelligence_feedback(req: FeedbackRequest):
    feedback = intelligence.record_feedback(target=req.target, rating=req.rating, note=req.note)
    await events.emit("intelligence.feedback_recorded", {"feedback": feedback})
    return {"feedback": feedback}


@router.post("/intelligence/releases", dependencies=[Depends(require_api_token)])
async def create_intelligence_release(req: ReleaseRequest):
    release = intelligence.release_manager(version=req.version, changes=req.changes)
    await events.emit("intelligence.release_created", {"release": release})
    return {"release": release}


# ── Module 44..53: Reliability and Mission Execution ────────────────────

@router.get("/reliability/status")
async def reliability_status():
    return reliability.reliability_status()


@router.post("/reliability/drill", dependencies=[Depends(require_api_token)])
async def run_reliability_drill():
    result = reliability.run_reliability_drill()
    await events.emit("reliability.drill_completed", {"result": result})
    return result


@router.post("/reliability/benchmark-packs", dependencies=[Depends(require_api_token)])
async def create_reliability_benchmark_pack(req: ReliabilityBenchmarkRequest):
    pack = reliability.create_benchmark_pack(name=req.name, focus=req.focus)
    await events.emit("reliability.benchmark_created", {"benchmark_pack": pack})
    return {"benchmark_pack": pack}


@router.post("/reliability/missions", dependencies=[Depends(require_api_token)])
async def create_reliability_mission(req: ReliabilityMissionRequest):
    try:
        mission = reliability.mission_runner(goal=req.goal, constraints=req.constraints)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await events.emit("reliability.mission_created", {"mission": mission})
    return {"mission": mission}


@router.post("/reliability/workstyle", dependencies=[Depends(require_api_token)])
async def remember_reliability_workstyle(req: WorkstyleMemoryRequest):
    try:
        memory_item = reliability.remember_workstyle(
            preference=req.preference,
            value=req.value,
            editable=req.editable,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await events.emit("reliability.workstyle_recorded", {"workstyle_memory": memory_item})
    return {"workstyle_memory": memory_item}


# ── World Model and Mission Learning ──────────────────────────────────

@router.get("/world/status")
async def get_world_status():
    return world_model.world_status()


@router.post("/world/drill", dependencies=[Depends(require_api_token)])
async def run_world_learning_drill(req: WorldLearningDrillRequest):
    result = world_model.run_learning_drill(goal=req.goal)
    await events.emit("world.learning_completed", {"result": result})
    return result


@router.post("/world/entities", dependencies=[Depends(require_api_token)])
async def create_world_entity(req: WorldEntityRequest):
    try:
        entity = world_model.upsert_entity(
            name=req.name,
            entity_type=req.entity_type,
            attributes=req.attributes,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await events.emit("world.entity_recorded", {"entity": entity})
    return {"entity": entity}


@router.post("/world/evidence", dependencies=[Depends(require_api_token)])
async def create_world_evidence(req: WorldEvidenceRequest):
    try:
        evidence = world_model.attach_evidence(
            source=req.source,
            summary=req.summary,
            kind=req.kind,
            payload=req.payload,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await events.emit("world.evidence_recorded", {"evidence": evidence})
    return {"evidence": evidence}


@router.post("/world/beliefs", dependencies=[Depends(require_api_token)])
async def create_world_belief(req: WorldBeliefRequest):
    try:
        belief = world_model.record_belief(
            subject=req.subject,
            claim=req.claim,
            confidence=req.confidence,
            evidence_ids=req.evidence_ids,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await events.emit("world.belief_recorded", {"belief": belief})
    return {"belief": belief}


@router.post("/world/snapshot", dependencies=[Depends(require_api_token)])
async def create_world_snapshot():
    snapshot = world_model.build_world_snapshot()
    await events.emit("world.snapshot_created", {"snapshot": snapshot})
    return {"snapshot": snapshot}


# ── Organism Nervous System ───────────────────────────────────────────

@router.get("/nervous-system/status")
async def get_nervous_fleet_status():
    return nervous_system.status()


@router.get("/organisms/{organism_id}/nervous-system")
async def get_organism_nervous_system(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return nervous_system.status(organism_id)


@router.post("/organisms/{organism_id}/nervous-system/tick", dependencies=[Depends(require_api_token)])
async def tick_organism_nervous_system(organism_id: str, req: NervousTickRequest):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    state = nervous_system.tick(organism_id, req.stimulus or {"type": "manual_tick"})
    await events.emit("organism.nervous_tick", {"organism_id": organism_id, "nervous_system": state})
    return {"nervous_system": state}


@router.post("/organisms/{organism_id}/nervous-system/intentions/{intention_id}/complete", dependencies=[Depends(require_api_token)])
async def complete_organism_intention(organism_id: str, intention_id: str, req: IntentionCompleteRequest):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    try:
        state = nervous_system.complete_intention(organism_id, intention_id, req.result)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    await events.emit(
        "organism.intention_completed",
        {"organism_id": organism_id, "intention_id": intention_id, "nervous_system": state},
    )
    return {"nervous_system": state}


@router.post("/organisms/{organism_id}/autonomy/cycle", dependencies=[Depends(require_api_token)])
async def run_organism_autonomy_cycle(organism_id: str, req: AutonomyCycleRequest):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    result = await nervous_system.run_autonomy_cycle(
        organism_id,
        event_callback=events.emit,
        stimulus=req.stimulus or {"type": "manual_autonomy_cycle"},
    )
    await events.emit(
        "organism.autonomy_cycle",
        {"organism_id": organism_id, "cycle": result["cycle"], "nervous_system": result["nervous_system"]},
    )
    return result


# ── Organism Body and Sensors ────────────────────────────────────────

@router.get("/body/status")
async def get_body_fleet_status():
    return body.fleet_status()


@router.get("/organisms/{organism_id}/body")
async def get_organism_body(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    nervous_state = nervous_system.tick(organism_id, {"type": "body_map_status"})
    body_map = body.build_body_map(organism_id, nervous_state=nervous_state)
    await events.emit("organism.body_mapped", {"organism_id": organism_id, "body": body_map})
    return {"body": body_map}


@router.post("/organisms/{organism_id}/body/sensors/recommended", dependencies=[Depends(require_api_token)])
async def attach_organism_recommended_sensor(organism_id: str, req: BodySensorAttachRequest):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    try:
        result = body.attach_recommended_sensor(organism_id, req.recommendation_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    await events.emit("organism.sensor_attached", {"organism_id": organism_id, "sensor": result["attached_sensor"]})
    nervous_state = nervous_system.tick(organism_id, {"type": "sensor_attached", "sensor": result["attached_sensor"]})
    return {"result": result, "body": body.build_body_map(organism_id, nervous_state=nervous_state)}


# ── Organism Metabolism ───────────────────────────────────────────────

@router.get("/organisms/{organism_id}/metabolism")
async def get_organism_metabolism(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    nervous_state = nervous_system.tick(organism_id, {"type": "metabolism_status"})
    metabolic_state = metabolism.evaluate(nervous_state)
    return {"metabolism": metabolic_state, "nervous_system": nervous_state}


@router.post("/organisms/{organism_id}/metabolism/recover", dependencies=[Depends(require_api_token)])
async def recover_organism_metabolism(organism_id: str, req: MetabolismRecoverRequest):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    nervous_state = nervous_system.ensure_state(organism_id)
    metabolic_state = metabolism.recover(nervous_state, depth=req.depth)
    homeostasis.evaluate(nervous_state)
    nervous_system.save_state(nervous_state)
    await events.emit(
        "organism.metabolism_recovered",
        {"organism_id": organism_id, "metabolism": metabolic_state},
    )
    return {"metabolism": metabolic_state, "nervous_system": nervous_state}


# ── Organism Homeostasis And Immune System ────────────────────────────

@router.get("/organisms/{organism_id}/homeostasis")
async def get_organism_homeostasis(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    nervous_state = nervous_system.tick(organism_id, {"type": "homeostasis_status"})
    body_map = body.build_body_map(organism_id, nervous_state=nervous_state)
    nervous_state["body"] = body_map
    metabolic_state = metabolism.evaluate(nervous_state, body_map=body_map)
    homeostatic_state = homeostasis.evaluate(nervous_state, body_map=body_map)
    nervous_system.save_state(nervous_state)
    await events.emit(
        "organism.homeostasis_checked",
        {"organism_id": organism_id, "homeostasis": homeostatic_state},
    )
    return {
        "homeostasis": homeostatic_state,
        "metabolism": metabolic_state,
        "body": body_map,
        "nervous_system": nervous_state,
    }


@router.post("/organisms/{organism_id}/homeostasis/immune-response", dependencies=[Depends(require_api_token)])
async def run_organism_immune_response(organism_id: str, req: ImmuneResponseRequest):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    nervous_state = nervous_system.tick(organism_id, {"type": "manual_immune_response"})
    nervous_state["body"] = body.build_body_map(organism_id, nervous_state=nervous_state)
    metabolism.evaluate(nervous_state, body_map=nervous_state["body"])
    result = homeostasis.run_immune_response(nervous_state, action=req.action or "auto")
    nervous_system.save_state(nervous_state)
    await events.emit(
        "organism.immune_response",
        {
            "organism_id": organism_id,
            "response": result["response"],
            "homeostasis": result["homeostasis"],
        },
    )
    return {
        "response": result["response"],
        "homeostasis": result["homeostasis"],
        "nervous_system": nervous_state,
    }


# ── Living Organism Systems ───────────────────────────────────────────

@router.get("/ecology")
async def get_living_ecology():
    return living_systems.ecology()


@router.get("/living-definition")
async def get_living_definition():
    return living_systems.living_definition()


@router.get("/organisms/{organism_id}/living-systems")
async def get_organism_living_systems(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return living_systems.status(organism_id)


@router.get("/organisms/{organism_id}/living-definition")
async def get_organism_living_definition(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return living_systems.living_definition(organism_id)


@router.get("/organisms/{organism_id}/life-engine")
async def get_organism_life_engine(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return living_systems.life_engine(organism_id)


@router.get("/organisms/{organism_id}/selection")
async def get_organism_selection(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return living_systems.selection_status(organism_id)


@router.get("/organisms/{organism_id}/temperament")
async def get_organism_temperament(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return living_systems.temperament_profile(organism_id)


@router.post("/organisms/{organism_id}/temperament/calibrate", dependencies=[Depends(require_api_token)])
async def calibrate_organism_temperament(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    result = living_systems.calibrate_temperament(organism_id)
    await events.emit("organism.temperament_calibrated", {"organism_id": organism_id, **result})
    return result


@router.get("/organisms/{organism_id}/goal-refinement")
async def get_organism_goal_refinement(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return living_systems.goal_refinement_status(organism_id)


@router.post("/organisms/{organism_id}/goal-refinement/propose", dependencies=[Depends(require_api_token)])
async def propose_organism_goal_refinement(organism_id: str, req: GoalRefinementRequest):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    result = living_systems.propose_goal_refinement(organism_id, focus=req.focus)
    await events.emit("organism.goal_refinement_proposed", {"organism_id": organism_id, **result})
    return result


@router.get("/organisms/{organism_id}/society-culture")
async def get_organism_society_culture(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return living_systems.society_roles_and_culture(organism_id)


@router.post("/organisms/{organism_id}/society-culture/pulse", dependencies=[Depends(require_api_token)])
async def pulse_organism_society_culture(organism_id: str, req: CulturePulseRequest):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    result = living_systems.run_culture_pulse(organism_id, focus=req.focus)
    await events.emit("organism.culture_pulse", {"organism_id": organism_id, **result})
    return result


@router.get("/organisms/{organism_id}/task-economy")
async def get_organism_task_economy(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return living_systems.task_economy_and_resource_budget(organism_id)


@router.post("/organisms/{organism_id}/task-economy/pulse", dependencies=[Depends(require_api_token)])
async def pulse_organism_task_economy(organism_id: str, req: BudgetPulseRequest):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    result = living_systems.run_budget_pulse(organism_id, focus=req.focus)
    await events.emit("organism.budget_pulse", {"organism_id": organism_id, **result})
    return result


@router.get("/organisms/{organism_id}/world-sandbox")
async def get_organism_world_sandbox(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return living_systems.world_sandbox_with_hazards(organism_id)


@router.post("/organisms/{organism_id}/world-sandbox/pulse", dependencies=[Depends(require_api_token)])
async def pulse_organism_world_sandbox(organism_id: str, req: WorldSandboxPulseRequest):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    result = living_systems.run_world_sandbox_pulse(organism_id, scenario=req.scenario)
    await events.emit("organism.world_sandbox_pulse", {"organism_id": organism_id, **result})
    return result


@router.get("/selection/history")
async def get_selection_history(limit: int = 20):
    return living_systems.selection_history(limit=limit)


@router.post("/selection/round", dependencies=[Depends(require_api_token)])
async def run_selection_round(req: SelectionRoundRequest):
    result = living_systems.selection_round(pressure=req.pressure, limit=req.limit)
    await events.emit("organism.selection_round", result)
    return result


@router.post("/organisms/{organism_id}/development/tick", dependencies=[Depends(require_api_token)])
async def tick_organism_development(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    result = living_systems.development_tick(organism_id)
    await events.emit("organism.development_tick", {"organism_id": organism_id, **result})
    return result


@router.get("/organisms/{organism_id}/lineage")
async def get_organism_lineage(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return {"lineage": living_systems.lineage(organism_id)}


@router.post("/organisms/{organism_id}/reproduce", dependencies=[Depends(require_api_token)])
async def reproduce_organism(organism_id: str, req: ReproductionRequest):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    try:
        result = living_systems.reproduce(organism_id, mutation=req.mutation)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    await events.emit("organism.reproduced", result)
    return result


@router.post("/organisms/{organism_id}/sleep/consolidate", dependencies=[Depends(require_api_token)])
async def consolidate_organism_sleep(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    result = living_systems.consolidate_sleep(organism_id)
    await events.emit("organism.sleep_consolidated", {"organism_id": organism_id, **result})
    return result


@router.get("/organisms/{organism_id}/social-contracts")
async def get_organism_social_contracts(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return {"social_contracts": living_systems.social_contracts(organism_id)}


@router.get("/organisms/{organism_id}/identity")
async def get_organism_identity(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return {"identity": living_systems.identity(organism_id)}


@router.get("/organisms/{organism_id}/tool-marketplace")
async def get_organism_tool_marketplace(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return {"tool_marketplace": living_systems.tool_marketplace(organism_id)}


@router.get("/organisms/{organism_id}/deployment-boundaries")
async def get_organism_deployment_boundaries(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return {"deployment_boundaries": living_systems.deployment_boundaries(organism_id)}


@router.get("/organisms/{organism_id}/mortality-legacy")
async def get_organism_mortality_legacy(organism_id: str):
    if not store.load_organism(organism_id):
        raise HTTPException(404, f"organism {organism_id} not found")
    return {"mortality_legacy": living_systems.mortality_legacy(organism_id)}


@router.post("/operators", dependencies=[Depends(require_api_token)])
async def create_operator(req: OperatorCreateRequest):
    operator = autonomous_operator.create_operator(
        goal=req.goal,
        name=req.name,
        cadence_s=req.cadence_s,
        max_ticks=req.max_ticks,
        constraints=req.constraints or None,
        start_active=req.start_active,
    )
    await events.emit("operator.created", {"operator": operator})
    return {"operator": operator}


@router.post("/operators/{operator_id}/pause", dependencies=[Depends(require_api_token)])
async def pause_operator(operator_id: str):
    operator = autonomous_operator.pause_operator(operator_id)
    if not operator:
        raise HTTPException(404, f"operator {operator_id} not found")
    await events.emit("operator.paused", {"operator": operator})
    return {"operator": operator}


@router.post("/operators/{operator_id}/resume", dependencies=[Depends(require_api_token)])
async def resume_operator(operator_id: str):
    operator = autonomous_operator.resume_operator(operator_id)
    if not operator:
        raise HTTPException(404, f"operator {operator_id} not found")
    await events.emit("operator.resumed", {"operator": operator})
    return {"operator": operator}


@router.post("/operators/{operator_id}/tick", dependencies=[Depends(require_api_token)])
async def tick_operator(operator_id: str):
    operator = await autonomous_operator.tick(
        operator_id,
        event_callback=events.emit,
        manual=True,
    )
    if not operator:
        raise HTTPException(404, f"operator {operator_id} not found")
    return {"operator": operator}


# ── Runtime status ────────────────────────────────────────────────────

@router.get("/status")
async def genesis_status():
    """Live runtime health snapshot.

    Returns the state of:
    - The lifecycle supervisor (is it running? which organisms have heartbeats?)
    - Per-organism last-active and last-message-check timestamps
    - The global LLM rate guard (calls in last 60s vs. limit)
    - Environment knobs currently in effect

    Useful for debugging rate-limit issues and confirming organisms are alive.
    """
    import os
    from backend.shared.config import settings
    from backend.shared.gemini_client import rate_guard_stats

    hb_status = lifecycle.status()
    llm_stats = rate_guard_stats()

    organisms = store.list_organisms()
    organism_summary = []
    for org in organisms:
        last_active = hb_status["last_active"].get(org.id)
        last_msg = lifecycle._last_msg_check.get(org.id)
        organism_summary.append({
            "id": org.id,
            "name": org.name,
            "state": org.state,
            "heartbeat_alive": org.id in hb_status["alive_organisms"],
            "last_active": last_active,
            "last_msg_check": last_msg.isoformat() if last_msg else None,
            "decision_count": len(store.load_decisions(org.id)),
            "active_strategy": next(
                (s.name for s in org.reasoning_strategies if s.id == getattr(org, "active_strategy_id", None)),
                None,
            ),
        })

    return {
        "lifecycle": {
            "enabled": hb_status["enabled"],
            "supervisor_running": hb_status["supervisor_running"],
            "alive_organism_count": len(hb_status["alive_organisms"]),
            "webhooks_registered": len(hb_status["webhooks"]),
        },
        "llm": {
            **llm_stats,
            "provider": settings.GENESIS_LLM_PROVIDER,
            "model": settings.GROQ_MODEL
                     if settings.GENESIS_LLM_PROVIDER == "groq"
                     else settings.GEMINI_MODEL,
        },
        "config": {
            "GENESIS_LIFECYCLE": os.getenv("GENESIS_LIFECYCLE", "1"),
            "GENESIS_DREAMING": os.getenv("GENESIS_DREAMING", "1"),
            "GENESIS_IDLE_DREAM_AFTER_S": os.getenv("GENESIS_IDLE_DREAM_AFTER_S", "3600"),
            "GENESIS_MSG_CHECK_INTERVAL_S": os.getenv("GENESIS_MSG_CHECK_INTERVAL_S", "30"),
            "GENESIS_MAX_LLM_CALLS_PER_MIN": os.getenv("GENESIS_MAX_LLM_CALLS_PER_MIN", "0"),
            "DATABASE_URL": long_term.status().get("database", {}).get("url"),
        },
        "long_term": long_term.status(),
        "product_core": product_core.status(),
        "organisms": organism_summary,
    }


# ── Population / Evolution endpoints ─────────────────────────────────

class PopulationStartRequest(BaseModel):
    task: str = Field(..., description="Goal shared by all organisms in the population.")
    perception: dict = Field(
        default_factory=dict,
        description="The perception event fired at every organism each generation.",
    )
    benchmark_id: Optional[str] = Field(
        None,
        description="Optional repeatable benchmark id. When supplied, the run is compared against prior runs for regression tracking.",
    )
    n_organisms: int = Field(4, ge=2, le=20, description="Population size.")
    max_generations: int = Field(3, ge=1, le=20)
    action_timeout_s: int = Field(90, ge=10, le=600)
    survival_rate: float = Field(0.5, ge=0.1, le=0.9)
    min_fitness_to_distill: float = Field(
        0.5, ge=0.0, le=1.0,
        description="Minimum fitness score for a survivor to have its experience distilled into a Skill.",
    )


@router.post("/population/start", dependencies=[Depends(require_api_token)])
async def start_population(req: PopulationStartRequest):
    """Start a new population evolution run.

    Organisms are seeded, scored by fitness (reasoning quality + action efficiency),
    survivors breed the next generation, and skills are distilled from top performers.
    """
    benchmark = None
    task = req.task
    perception = req.perception
    if req.benchmark_id:
        benchmark = population.get_benchmark(req.benchmark_id)
        if not benchmark:
            raise HTTPException(404, f"benchmark {req.benchmark_id} not found")
        if not task.strip():
            task = benchmark["task"]
        perception = perception or benchmark["perception"]

    perception = perception or {
        "type": "task",
        "description": task,
    }
    run = population.new_run(
        task=task,
        perception=perception,
        benchmark_id=req.benchmark_id,
        n_organisms=req.n_organisms,
        max_generations=req.max_generations,
        action_timeout_s=req.action_timeout_s,
        survival_rate=req.survival_rate,
        min_fitness_to_distill=req.min_fitness_to_distill,
    )
    population.start(run)
    return {"ok": True, "run_id": run["id"], "run": run}


@router.get("/population/benchmarks")
async def list_population_benchmarks():
    """List repeatable benchmark tasks and historical regression baselines."""
    return {"benchmarks": population.benchmark_summaries()}


@router.get("/benchmarks")
async def list_benchmarks():
    """List Module 1 benchmark arena tasks and historical baselines."""
    return {"benchmarks": population.benchmark_summaries()}


@router.get("/benchmarks/{benchmark_id}")
async def get_benchmark(benchmark_id: str):
    """Get one benchmark definition, including its deterministic rubric."""
    benchmark = population.get_benchmark(benchmark_id)
    if not benchmark:
        raise HTTPException(404, f"benchmark {benchmark_id} not found")
    return {
        "benchmark": benchmark,
        "summary": population.benchmark_summary(benchmark_id),
    }


@router.get("/population")
async def list_populations():
    """List all evolution runs (completed, running, stopped)."""
    runs = population.list_runs()
    return {
        "runs": [
            {
                "id": r["id"],
                "benchmark_id": r.get("benchmark_id"),
                "benchmark_name": r.get("benchmark_name"),
                "task": r["task"],
                "status": r["status"],
                "current_generation": r["current_generation"],
                "max_generations": r["max_generations"],
                "n_organisms": r["n_organisms"],
                "is_running": population.is_running(r["id"]),
                "best_fitness": max(
                    (g["best_fitness"] for g in r.get("generations", [])),
                    default=None,
                ),
                "created_at": r["created_at"],
            }
            for r in runs
        ]
    }


@router.get("/population/{run_id}")
async def get_population(run_id: str):
    """Get the full state of a single evolution run."""
    run = population.load_run(run_id)
    if not run:
        raise HTTPException(404, f"run {run_id} not found")
    return {**run, "is_running": population.is_running(run_id)}


@router.get("/population/{run_id}/report")
async def get_population_report(run_id: str):
    """Get an evidence-of-learning report for a population run."""
    run = population.load_run(run_id)
    if not run:
        raise HTTPException(404, f"run {run_id} not found")
    return population.build_evidence_report(run)


@router.post("/population/{run_id}/stop", dependencies=[Depends(require_api_token)])
async def stop_population(run_id: str):
    """Stop a running evolution after the current generation completes."""
    ok = population.stop(run_id)
    if not ok:
        raise HTTPException(404, f"run {run_id} not found")
    return {"ok": True, "run_id": run_id}


@router.delete("/population/{run_id}", dependencies=[Depends(require_api_token)])
async def delete_population(run_id: str):
    """Delete an evolution run and all its data."""
    deleted = population.delete_run(run_id)
    return {"ok": True, "deleted": deleted}
