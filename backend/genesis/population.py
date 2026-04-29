"""Phase 6 — Observable Evolution: population-based organism evolution.

Seeds N organisms on the same task with different starting strategies,
runs them in parallel, scores them by fitness, breeds the winners into the
next generation, and repeats for G generations.

This is the unique thing Genesis can do that no other agent framework does.
You can WATCH a population of AI agents evolve to solve a task over generations,
with each generation inheriting distilled skills from successful ancestors.

How it works:
  1. Seed N organisms with the same goal, random starting strategies
  2. Fire the same perception event at all of them in parallel
  3. Wait until each organism has acted (or timeout)
  4. Score: fitness = 0.6 × reasoning_quality + 0.4 × action_efficiency
     (from MetaDecision records produced by the metacognitive critic)
  5. Kill bottom 50%. Distill skills from survivors with fitness > 0.5.
  6. Breed next generation: N new organisms each inheriting from 1-2 survivors
  7. Repeat from step 2 for max_generations

Persistence:
  populations/{run_id}/run.json   — full run state (updated after each generation)
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Optional
from uuid import uuid4

from . import events, runtime, store
from .skills import distill as _distill
from .types import Intent, Organism, OrganismState

logger = logging.getLogger("genesis.population")

_BASE = Path("populations")
_BASE.mkdir(exist_ok=True)

# Running evolution tasks: run_id -> asyncio.Task
_running: dict[str, asyncio.Task] = {}


# ── Data models (stored as plain dicts in JSON) ───────────────────────

def _run_path(run_id: str) -> Path:
    p = _BASE / run_id
    p.mkdir(exist_ok=True)
    return p / "run.json"


def save_run(run: dict) -> None:
    run["updated_at"] = datetime.utcnow().isoformat()
    _run_path(run["id"]).write_text(json.dumps(run, indent=2, default=str))


def load_run(run_id: str) -> Optional[dict]:
    p = _run_path(run_id)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def list_runs() -> list[dict]:
    runs = []
    for d in sorted(_BASE.iterdir()):
        p = d / "run.json"
        if p.exists():
            try:
                runs.append(json.loads(p.read_text()))
            except Exception:
                pass
    return runs


def new_run(
    task: str,
    perception: dict,
    n_organisms: int = 4,
    max_generations: int = 3,
    action_timeout_s: int = 90,
    survival_rate: float = 0.5,
    min_fitness_to_distill: float = 0.5,
) -> dict:
    return {
        "id": f"pop_{uuid4().hex[:10]}",
        "task": task,
        "perception": perception,
        "n_organisms": n_organisms,
        "max_generations": max_generations,
        "action_timeout_s": action_timeout_s,
        "survival_rate": survival_rate,
        "min_fitness_to_distill": min_fitness_to_distill,
        "status": "pending",  # pending | running | complete | stopped
        "current_generation": 0,
        "current_organism_ids": [],
        "generations": [],   # list of GenerationResult dicts
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }


# ── Fitness scoring ───────────────────────────────────────────────────

def score_organism(organism_id: str) -> dict:
    """Compute fitness from MetaDecision records.

    fitness = 0.6 × mean(reasoning_quality) + 0.4 × mean(action_efficiency)

    Organisms that never acted (no meta_decisions) score 0 — they lose
    the selection round and their gene pool is not propagated.
    """
    mds = store.load_meta_decisions(organism_id, limit=50)
    org = store.load_organism(organism_id)
    name = org.name if org else organism_id

    if not mds:
        return {
            "organism_id": organism_id,
            "name": name,
            "fitness": 0.0,
            "reasoning_quality_avg": 0.0,
            "action_efficiency_avg": 0.0,
            "decision_count": len(store.all_decisions(organism_id)),
            "meta_decision_count": 0,
        }

    q = mean(md.reasoning_quality for md in mds)
    e = mean(md.action_efficiency for md in mds)
    fitness = round(0.6 * q + 0.4 * e, 4)

    return {
        "organism_id": organism_id,
        "name": name,
        "fitness": fitness,
        "reasoning_quality_avg": round(q, 4),
        "action_efficiency_avg": round(e, 4),
        "decision_count": len(store.all_decisions(organism_id)),
        "meta_decision_count": len(mds),
    }


# ── Wait for actions ──────────────────────────────────────────────────

async def _wait_for_actions(
    organism_ids: list[str],
    baseline_counts: dict[str, int],
    timeout_s: int,
) -> dict[str, bool]:
    """Poll until every organism has produced at least one new decision.

    Returns {organism_id: acted} mapping. Organisms that timeout are marked
    False but are still scored (fitness 0 if no meta_decisions).
    """
    acted = {oid: False for oid in organism_ids}
    deadline = asyncio.get_event_loop().time() + timeout_s

    while True:
        for oid in organism_ids:
            if acted[oid]:
                continue
            current = len(store.all_decisions(oid))
            if current > baseline_counts.get(oid, 0):
                acted[oid] = True

        if all(acted.values()):
            break
        if asyncio.get_event_loop().time() >= deadline:
            pending = [oid for oid, a in acted.items() if not a]
            logger.warning(
                f"[Population] Timeout waiting for {len(pending)} organism(s): {pending}"
            )
            break

        await asyncio.sleep(3)

    return acted


# ── Seed a generation ─────────────────────────────────────────────────

async def _seed_generation(
    run: dict,
    generation_num: int,
    inherit_from_organisms: list[str],
) -> list[str]:
    """Create N new organisms for a generation, inheriting from survivors."""
    from . import metacognition
    from .skills import inherit as _inherit

    task = run["task"]
    n = run["n_organisms"]
    new_ids = []

    for i in range(n):
        # Pick 1 or 2 parents from survivors (crossover if pool is big enough)
        parents: list[str] = []
        if inherit_from_organisms:
            k = min(2, len(inherit_from_organisms))
            parents = random.sample(inherit_from_organisms, k)

        inherited_refs, parent_orgs, compiled_mcp_specs, inherited_strategies = \
            _inherit.resolve_seed_inheritance(
                inherit_from=None,
                inherit_from_organisms=parents or None,
                max_inherited_skills=5,
            )

        org = runtime.seed(
            intent_goal=task,
            name=f"gen{generation_num}_org{i + 1}",
            constraints=[],
        )
        org.inherited_skills = inherited_refs
        org.parent_organisms = parent_orgs
        org.fitness_score = 0.0
        if compiled_mcp_specs:
            org.mcp_servers = compiled_mcp_specs

        # Merge inherited reasoning strategies (deduplicated by name)
        if inherited_strategies:
            existing_names = {s.name for s in org.reasoning_strategies}
            for s in inherited_strategies:
                if s.name not in existing_names:
                    org.reasoning_strategies.append(s)
                    existing_names.add(s.name)

        store.save_organism(org)
        metacognition.seed_default_strategies(org)

        new_ids.append(org.id)
        logger.info(
            f"[Population] gen{generation_num} org {i + 1}/{n} seeded: {org.id} "
            f"(parents: {parents})"
        )

    return new_ids


# ── Main evolution loop ───────────────────────────────────────────────

async def _run_evolution(run_id: str) -> None:
    """Background task: runs the full evolution for a population run."""
    run = load_run(run_id)
    if not run:
        return

    run["status"] = "running"
    save_run(run)

    cb = events.make_callback()

    try:
        for gen_num in range(1, run["max_generations"] + 1):
            if run.get("status") == "stopped":
                break

            logger.info(f"[Population] {run_id} — generation {gen_num} starting")

            # ── 1. Seed first generation or use existing IDs ──────────
            if gen_num == 1:
                organism_ids = await _seed_generation(run, gen_num, inherit_from_organisms=[])
                run["current_organism_ids"] = organism_ids
                save_run(run)
            else:
                organism_ids = run["current_organism_ids"]

            # ── 2. Snapshot baseline decision counts ──────────────────
            baseline = {oid: len(store.all_decisions(oid)) for oid in organism_ids}

            # Emit generation start
            await cb({
                "type": "population.generation_start",
                "run_id": run_id,
                "generation": gen_num,
                "organism_ids": organism_ids,
            })

            # ── 3. Fire the same perception at all organisms in parallel
            logger.info(f"[Population] Firing perception at {len(organism_ids)} organisms")
            perception_tasks = [
                runtime.perceive(
                    oid,
                    {**run["perception"], "generation": gen_num},
                    event_callback=cb,
                )
                for oid in organism_ids
            ]
            results = await asyncio.gather(*perception_tasks, return_exceptions=True)
            for oid, res in zip(organism_ids, results):
                if isinstance(res, Exception):
                    logger.warning(f"[Population] {oid} perceive raised: {res}")

            # ── 4. Wait for all organisms to act ──────────────────────
            logger.info(
                f"[Population] Waiting up to {run['action_timeout_s']}s for actions…"
            )
            acted = await _wait_for_actions(
                organism_ids, baseline, run["action_timeout_s"]
            )
            logger.info(
                f"[Population] Acted: {sum(acted.values())}/{len(organism_ids)}"
            )

            # ── 5. Score every organism ───────────────────────────────
            scores = [score_organism(oid) for oid in organism_ids]
            scores.sort(key=lambda s: s["fitness"], reverse=True)

            await cb({
                "type": "population.scored",
                "run_id": run_id,
                "generation": gen_num,
                "scores": scores,
            })

            # ── 6. Select survivors ───────────────────────────────────
            n_survivors = max(1, int(len(scores) * run["survival_rate"]))
            survivors = scores[:n_survivors]
            losers = scores[n_survivors:]
            survivor_ids = [s["organism_id"] for s in survivors]

            logger.info(
                f"[Population] Survivors: {len(survivors)} "
                f"(top fitness: {survivors[0]['fitness']:.3f})"
            )

            # ── 7. Distill skills from high-fitness survivors ─────────
            distilled_skill_ids: list[str] = []
            for s in survivors:
                if s["fitness"] >= run["min_fitness_to_distill"]:
                    try:
                        skill_id = await _distill.distill(s["organism_id"])
                        if skill_id:
                            distilled_skill_ids.append(skill_id)
                            logger.info(
                                f"[Population] Distilled skill {skill_id} from {s['organism_id']}"
                            )
                    except Exception as e:
                        logger.warning(f"[Population] Distill failed for {s['organism_id']}: {e}")

            # ── 8. Record generation result ───────────────────────────
            gen_result = {
                "generation": gen_num,
                "scores": scores,
                "survivor_ids": survivor_ids,
                "loser_ids": [s["organism_id"] for s in losers],
                "skills_distilled": distilled_skill_ids,
                "best_fitness": scores[0]["fitness"] if scores else 0.0,
                "mean_fitness": round(mean(s["fitness"] for s in scores), 4) if scores else 0.0,
                "completed_at": datetime.utcnow().isoformat(),
            }
            run["generations"].append(gen_result)
            run["current_generation"] = gen_num

            await cb({
                "type": "population.generation_complete",
                "run_id": run_id,
                "generation": gen_num,
                "result": gen_result,
            })

            # ── 9. Kill losers (after scoring, before next generation) ─
            for s in losers:
                try:
                    org = store.load_organism(s["organism_id"])
                    if org:
                        org.state = OrganismState.DEAD
                        store.save_organism(org)
                except Exception:
                    pass

            # ── 10. Breed next generation (skip if this is the last) ──
            if gen_num < run["max_generations"] and run.get("status") != "stopped":
                next_ids = await _seed_generation(run, gen_num + 1, survivor_ids)
                run["current_organism_ids"] = next_ids
                save_run(run)

                await cb({
                    "type": "population.generation_bred",
                    "run_id": run_id,
                    "generation": gen_num + 1,
                    "new_organism_ids": next_ids,
                    "parent_ids": survivor_ids,
                })

        # ── Evolution complete ─────────────────────────────────────────
        run["status"] = "complete"
        save_run(run)

        # Best organism overall
        all_scores = [s for g in run["generations"] for s in g["scores"]]
        best = max(all_scores, key=lambda s: s["fitness"]) if all_scores else None

        await cb({
            "type": "population.complete",
            "run_id": run_id,
            "generations_run": run["current_generation"],
            "best_organism": best,
        })
        logger.info(f"[Population] {run_id} complete. Best: {best}")

    except asyncio.CancelledError:
        run = load_run(run_id) or run
        run["status"] = "stopped"
        save_run(run)
        logger.info(f"[Population] {run_id} stopped")
    except Exception as e:
        logger.exception(f"[Population] {run_id} crashed: {e}")
        run = load_run(run_id) or run
        run["status"] = "error"
        run["error"] = str(e)
        save_run(run)
    finally:
        _running.pop(run_id, None)


# ── Public API ────────────────────────────────────────────────────────

def start(run: dict) -> None:
    """Persist the run and launch the background evolution task."""
    save_run(run)
    task = asyncio.create_task(
        _run_evolution(run["id"]), name=f"pop_{run['id']}"
    )
    _running[run["id"]] = task


def stop(run_id: str) -> bool:
    """Request a running evolution to stop gracefully after the current generation."""
    run = load_run(run_id)
    if not run:
        return False
    run["status"] = "stopped"
    save_run(run)
    task = _running.get(run_id)
    if task and not task.done():
        task.cancel()
    return True


def is_running(run_id: str) -> bool:
    t = _running.get(run_id)
    return bool(t and not t.done())
