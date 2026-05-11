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
import os
import random
import tempfile
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Optional
from uuid import uuid4

from . import events, runtime, store
from .skills import distill as _distill
from .types import Intent, Organism, OrganismState

logger = logging.getLogger("genesis.population")

_BASE = Path(os.getenv("GENESIS_POPULATION_STORAGE", "populations")).resolve()
_BASE.mkdir(exist_ok=True)

# Running evolution tasks: run_id -> asyncio.Task
_running: dict[str, asyncio.Task] = {}


BENCHMARKS = [
    {
        "id": "repo_triage",
        "name": "Repository Triage",
        "task": "Analyze the state of an open-source repository and suggest the most impactful contribution.",
        "perception": {
            "type": "benchmark_task",
            "benchmark_id": "repo_triage",
            "description": "Analyze repository health, identify risks, and choose one high-leverage contribution.",
            "success_criteria": [
                "Names a concrete contribution",
                "Explains impact",
                "Mentions implementation risk",
            ],
        },
        "rubric": [
            {
                "id": "concrete_contribution",
                "label": "Concrete contribution",
                "signals": ["contribution", "fix", "implement", "issue", "pull request", "test", "documentation"],
            },
            {
                "id": "impact",
                "label": "Impact explained",
                "signals": ["impact", "leverage", "user", "risk", "reliability", "maintainer", "adoption"],
            },
            {
                "id": "implementation_risk",
                "label": "Implementation risk",
                "signals": ["risk", "tradeoff", "regression", "test", "blast radius", "compatibility"],
            },
        ],
    },
    {
        "id": "incident_response",
        "name": "Incident Response",
        "task": "Diagnose a production incident from sparse symptoms and propose the safest next action.",
        "perception": {
            "type": "benchmark_task",
            "benchmark_id": "incident_response",
            "description": "Given slow requests, elevated errors, and no deploy in the last hour, pick the safest investigation step.",
            "success_criteria": [
                "Prioritizes user impact",
                "Checks telemetry before changing production",
                "Chooses a reversible action",
            ],
        },
        "rubric": [
            {
                "id": "user_impact",
                "label": "User impact first",
                "signals": ["user impact", "affected users", "severity", "customer", "error rate", "latency"],
            },
            {
                "id": "telemetry_first",
                "label": "Telemetry before changes",
                "signals": ["telemetry", "logs", "metrics", "trace", "dashboard", "observe", "investigate"],
            },
            {
                "id": "reversible_action",
                "label": "Reversible next action",
                "signals": ["reversible", "rollback", "mitigate", "canary", "disable", "safe", "read-only"],
            },
        ],
    },
    {
        "id": "product_synthesis",
        "name": "Product Synthesis",
        "task": "Turn ambiguous product feedback into a focused next feature with measurable success criteria.",
        "perception": {
            "type": "benchmark_task",
            "benchmark_id": "product_synthesis",
            "description": "Synthesize mixed user feedback into one shippable feature and define how to measure it.",
            "success_criteria": [
                "Separates signal from noise",
                "Defines a scoped feature",
                "Provides measurable success criteria",
            ],
        },
        "rubric": [
            {
                "id": "signal_from_noise",
                "label": "Signal separated from noise",
                "signals": ["signal", "noise", "pattern", "segment", "feedback", "theme"],
            },
            {
                "id": "scoped_feature",
                "label": "Scoped feature",
                "signals": ["feature", "scope", "ship", "mvp", "workflow", "user story"],
            },
            {
                "id": "measurable_success",
                "label": "Measurable success",
                "signals": ["measure", "metric", "success criteria", "conversion", "retention", "time", "rate"],
            },
        ],
    },
]

_BENCHMARK_BY_ID = {b["id"]: b for b in BENCHMARKS}


# ── Data models (stored as plain dicts in JSON) ───────────────────────

def _run_path(run_id: str) -> Path:
    p = _BASE / run_id
    p.mkdir(exist_ok=True)
    return p / "run.json"


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def save_run(run: dict) -> None:
    run["updated_at"] = datetime.utcnow().isoformat()
    _atomic_write_json(_run_path(run["id"]), run)


def load_run(run_id: str) -> Optional[dict]:
    p = _run_path(run_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("[Population] failed to load run %s: %s", run_id, e)
        return None


def list_runs() -> list[dict]:
    _BASE.mkdir(exist_ok=True)
    runs = []
    for d in sorted(_BASE.iterdir()):
        p = d / "run.json"
        if p.exists():
            try:
                runs.append(json.loads(p.read_text()))
            except Exception:
                pass
    return runs


def list_benchmarks() -> list[dict]:
    return [dict(b) for b in BENCHMARKS]


def get_benchmark(benchmark_id: str) -> Optional[dict]:
    bench = _BENCHMARK_BY_ID.get(benchmark_id)
    return dict(bench) if bench else None


def _completed_benchmark_runs(benchmark_id: str, before_created_at: Optional[str] = None) -> list[dict]:
    runs = [
        r for r in list_runs()
        if r.get("benchmark_id") == benchmark_id
        and r.get("status") == "complete"
        and r.get("generations")
    ]
    if before_created_at:
        runs = [r for r in runs if r.get("created_at", "") < before_created_at]
    return sorted(runs, key=lambda r: r.get("created_at", ""))


def _run_best_fitness(run: dict) -> float:
    return max((g.get("best_fitness", 0.0) for g in run.get("generations", [])), default=0.0)


def _run_last_mean_fitness(run: dict) -> float:
    generations = run.get("generations", [])
    return generations[-1].get("mean_fitness", 0.0) if generations else 0.0


def benchmark_summary(benchmark_id: str) -> Optional[dict]:
    bench = get_benchmark(benchmark_id)
    if not bench:
        return None

    runs = _completed_benchmark_runs(benchmark_id)
    best_run = max(runs, key=_run_best_fitness, default=None)
    latest = runs[-1] if runs else None
    return {
        "benchmark": bench,
        "completed_runs": len(runs),
        "best_fitness": _run_best_fitness(best_run) if best_run else None,
        "best_run_id": best_run.get("id") if best_run else None,
        "latest_run_id": latest.get("id") if latest else None,
        "latest_best_fitness": _run_best_fitness(latest) if latest else None,
        "latest_mean_fitness": _run_last_mean_fitness(latest) if latest else None,
    }


def benchmark_summaries() -> list[dict]:
    return [benchmark_summary(b["id"]) for b in BENCHMARKS]


def build_evidence_report(run: dict) -> dict:
    """Summarize whether a population run improved over generations."""
    generations = run.get("generations", [])
    first = generations[0] if generations else None
    last = generations[-1] if generations else None
    best_scores = [g.get("best_fitness", 0.0) for g in generations]
    mean_scores = [g.get("mean_fitness", 0.0) for g in generations]
    skills_by_generation = [
        {
            "generation": g.get("generation"),
            "skills_distilled": g.get("skills_distilled", []),
            "skill_count": len(g.get("skills_distilled", [])),
        }
        for g in generations
    ]
    all_scores = [s for g in generations for s in g.get("scores", [])]
    best_organism = max(all_scores, key=lambda s: s.get("fitness", 0.0), default=None)
    first_best = first.get("best_fitness", 0.0) if first else 0.0
    last_best = last.get("best_fitness", 0.0) if last else 0.0
    first_mean = first.get("mean_fitness", 0.0) if first else 0.0
    last_mean = last.get("mean_fitness", 0.0) if last else 0.0
    best_delta = round(last_best - first_best, 4)
    mean_delta = round(last_mean - first_mean, 4)
    total_skills = sum(item["skill_count"] for item in skills_by_generation)
    benchmark_id = run.get("benchmark_id")
    regression = None

    if benchmark_id:
        previous_runs = _completed_benchmark_runs(
            benchmark_id,
            before_created_at=run.get("created_at"),
        )
        previous_best = max((_run_best_fitness(r) for r in previous_runs), default=None)
        previous_latest = previous_runs[-1] if previous_runs else None
        current_best = max(best_scores, default=0.0)
        current_last_mean = mean_scores[-1] if mean_scores else 0.0
        regression = {
            "benchmark_id": benchmark_id,
            "benchmark_name": run.get("benchmark_name"),
            "previous_completed_runs": len(previous_runs),
            "previous_best_fitness": previous_best,
            "previous_latest_run_id": previous_latest.get("id") if previous_latest else None,
            "current_best_fitness": current_best,
            "current_last_mean_fitness": current_last_mean,
            "delta_vs_previous_best": (
                round(current_best - previous_best, 4)
                if previous_best is not None else None
            ),
        }

    if not generations:
        verdict = "not_started"
        summary = "No generations have completed yet, so there is not enough evidence of learning."
    elif best_delta > 0.05 or mean_delta > 0.05:
        verdict = "improved"
        summary = "Later generations outperformed the first generation."
    elif total_skills > 0:
        verdict = "skills_distilled"
        summary = "The run produced inheritable skills, but fitness improvement is not yet clear."
    elif regression and regression["delta_vs_previous_best"] is not None and regression["delta_vs_previous_best"] < -0.05:
        verdict = "regressed"
        summary = "This benchmark run fell behind the previous best completed run."
    else:
        verdict = "inconclusive"
        summary = "The run completed, but fitness did not improve enough to prove learning."

    return {
        "run_id": run["id"],
        "task": run["task"],
        "status": run["status"],
        "benchmark": (
            {
                "id": benchmark_id,
                "name": run.get("benchmark_name"),
            }
            if benchmark_id else None
        ),
        "generations_run": len(generations),
        "verdict": verdict,
        "summary": summary,
        "fitness": {
            "first_best": first_best,
            "last_best": last_best,
            "best_delta": best_delta,
            "best_series": best_scores,
            "first_mean": first_mean,
            "last_mean": last_mean,
            "mean_delta": mean_delta,
            "mean_series": mean_scores,
        },
        "skills": {
            "total_distilled": total_skills,
            "by_generation": skills_by_generation,
        },
        "best_organism": best_organism,
        "regression": regression,
        "claim": (
            "Genesis shows evidence of learning when later generations achieve "
            "higher fitness, distill inheritable skills, or improve against a repeatable benchmark baseline."
        ),
    }


def new_run(
    task: str,
    perception: dict,
    benchmark_id: Optional[str] = None,
    n_organisms: int = 4,
    max_generations: int = 3,
    action_timeout_s: int = 90,
    survival_rate: float = 0.5,
    min_fitness_to_distill: float = 0.5,
) -> dict:
    benchmark_name = None
    if benchmark_id:
        bench = get_benchmark(benchmark_id)
        if not bench:
            raise ValueError(f"unknown benchmark_id: {benchmark_id}")
        benchmark_name = bench["name"]

    return {
        "id": f"pop_{uuid4().hex[:10]}",
        "benchmark_id": benchmark_id,
        "benchmark_name": benchmark_name,
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

def _decision_text(decision) -> str:
    return " ".join(
        [
            decision.reasoning or "",
            json.dumps(decision.action or {}, default=str),
            json.dumps(decision.result or {}, default=str),
            json.dumps(decision.alternatives_considered or [], default=str),
        ]
    ).lower()


def evaluate_benchmark_alignment(organism_id: str, benchmark_id: Optional[str]) -> Optional[dict]:
    """Score latest real decisions against a repeatable benchmark rubric.

    This is deliberately deterministic. The meta-cognitive critic judges
    reasoning quality, while this rubric checks whether the answer touched the
    benchmark-specific things Genesis asked for.
    """
    if not benchmark_id:
        return None
    benchmark = get_benchmark(benchmark_id)
    if not benchmark:
        return None

    decisions = [
        d for d in store.all_decisions(organism_id)
        if not d.is_dream and not d.shadow_branch
    ]
    if not decisions:
        return {
            "benchmark_id": benchmark_id,
            "score": 0.0,
            "criteria": [],
            "evidence": "No real decisions found.",
        }

    text = "\n".join(_decision_text(d) for d in decisions[-3:])
    criteria = []
    for item in benchmark.get("rubric", []):
        signals = item.get("signals", [])
        hits = [signal for signal in signals if signal.lower() in text]
        criteria.append({
            "id": item.get("id"),
            "label": item.get("label"),
            "score": 1.0 if hits else 0.0,
            "matched_signals": hits[:5],
        })

    score = (
        round(mean(c["score"] for c in criteria), 4)
        if criteria else 0.0
    )
    return {
        "benchmark_id": benchmark_id,
        "score": score,
        "criteria": criteria,
        "evidence": text[:600],
    }


def score_organism(organism_id: str, benchmark_id: Optional[str] = None) -> dict:
    """Compute fitness from MetaDecision records.

    fitness = 0.6 × mean(reasoning_quality) + 0.4 × mean(action_efficiency)

    Organisms that never acted (no meta_decisions) score 0 — they lose
    the selection round and their gene pool is not propagated.
    """
    mds = store.load_meta_decisions(organism_id, limit=50)
    org = store.load_organism(organism_id)
    name = org.name if org else organism_id

    if not mds:
        alignment = evaluate_benchmark_alignment(organism_id, benchmark_id)
        base = {
            "organism_id": organism_id,
            "name": name,
            "fitness": 0.0,
            "reasoning_quality_avg": 0.0,
            "action_efficiency_avg": 0.0,
            "decision_count": len(store.all_decisions(organism_id)),
            "meta_decision_count": 0,
        }
        if alignment:
            base["benchmark_alignment"] = alignment
        return base

    q = mean(md.reasoning_quality for md in mds)
    e = mean(md.action_efficiency for md in mds)
    meta_fitness = 0.6 * q + 0.4 * e
    alignment = evaluate_benchmark_alignment(organism_id, benchmark_id)
    fitness = (
        round((0.65 * meta_fitness) + (0.35 * alignment["score"]), 4)
        if alignment else round(meta_fitness, 4)
    )

    scored = {
        "organism_id": organism_id,
        "name": name,
        "fitness": fitness,
        "meta_fitness": round(meta_fitness, 4),
        "reasoning_quality_avg": round(q, 4),
        "action_efficiency_avg": round(e, 4),
        "decision_count": len(store.all_decisions(organism_id)),
        "meta_decision_count": len(mds),
    }
    if alignment:
        scored["benchmark_alignment"] = alignment
    return scored


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

    async def emit_population(event_type: str, payload: dict) -> None:
        await cb(event_type, payload)

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
            await emit_population("population.generation_start", {
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
            scores = [
                score_organism(oid, benchmark_id=run.get("benchmark_id"))
                for oid in organism_ids
            ]
            scores.sort(key=lambda s: s["fitness"], reverse=True)

            await emit_population("population.scored", {
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
            from . import memory as _memory
            curriculum = _memory.update_curriculum_from_run(run)

            await emit_population("population.generation_complete", {
                "run_id": run_id,
                "generation": gen_num,
                "result": gen_result,
            })
            await emit_population("curriculum.updated", {
                "run_id": run_id,
                "benchmark_id": run.get("benchmark_id"),
                "curriculum": curriculum,
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

                await emit_population("population.generation_bred", {
                    "run_id": run_id,
                    "generation": gen_num + 1,
                    "new_organism_ids": next_ids,
                    "parent_ids": survivor_ids,
                })

        # ── Evolution complete ─────────────────────────────────────────
        run["status"] = "complete"
        save_run(run)
        from . import memory as _memory
        curriculum = _memory.update_curriculum_from_run(run)

        # Best organism overall
        all_scores = [s for g in run["generations"] for s in g["scores"]]
        best = max(all_scores, key=lambda s: s["fitness"]) if all_scores else None

        await emit_population("population.complete", {
            "run_id": run_id,
            "generations_run": run["current_generation"],
            "best_organism": best,
        })
        await emit_population("curriculum.updated", {
            "run_id": run_id,
            "benchmark_id": run.get("benchmark_id"),
            "curriculum": curriculum,
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


def delete_run(run_id: str) -> bool:
    stop(run_id)
    path = _BASE / run_id
    if not path.exists():
        return False
    import shutil
    shutil.rmtree(path)
    return True


def is_running(run_id: str) -> bool:
    t = _running.get(run_id)
    return bool(t and not t.done())
