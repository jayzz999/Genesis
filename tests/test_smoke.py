import asyncio
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.shared.config import settings
from backend.genesis import store


@pytest.fixture()
def isolated_genesis(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_BASE", tmp_path / "organisms")
    monkeypatch.setattr(settings, "GENESIS_LLM_PROVIDER", "mock")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")
    yield tmp_path


@pytest.mark.asyncio
async def test_seed_status_and_perceive_work_without_api_keys(isolated_genesis):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        seed_response = await client.post(
            "/api/genesis/seed",
            json={
                "name": "smoke",
                "goal": "Remember useful test signals.",
                "constraints": ["stay deterministic"],
            },
        )
        assert seed_response.status_code == 200
        organism = seed_response.json()["organism"]

        status_response = await client.get("/api/genesis/status")
        assert status_response.status_code == 200
        assert status_response.json()["llm"]["provider"] in {"gemini", "mock"}
        assert "@" not in status_response.json()["config"]["DATABASE_URL"] or "***@" in status_response.json()["config"]["DATABASE_URL"]

        perceive_response = await client.post(
            f"/api/genesis/organisms/{organism['id']}/perceive",
            json={"perception": {"type": "test_event", "payload": {"ok": True}}},
        )
        assert perceive_response.status_code == 200
        decision = perceive_response.json()["decision"]
        assert decision["organism_id"] == organism["id"]
        assert decision["result"]["ok"] is True

        graph_response = await client.get(
            f"/api/genesis/organisms/{organism['id']}/causality"
        )
        assert graph_response.status_code == 200
        assert len(graph_response.json()["nodes"]) >= 1


@pytest.mark.asyncio
async def test_mutating_routes_can_require_api_token(isolated_genesis, monkeypatch):
    monkeypatch.setattr(settings, "GENESIS_REQUIRE_API_TOKEN", True)
    monkeypatch.setattr(settings, "GENESIS_API_TOKEN", "test-token-that-is-long-enough")
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            denied = await client.post(
                "/api/genesis/seed",
                json={"name": "locked", "goal": "Reject unauthenticated writes."},
            )
            assert denied.status_code == 401

            allowed = await client.post(
                "/api/genesis/seed",
                headers={"X-Genesis-Token": "test-token-that-is-long-enough"},
                json={"name": "locked", "goal": "Accept authenticated writes."},
            )
            assert allowed.status_code == 200
    finally:
        monkeypatch.setattr(settings, "GENESIS_REQUIRE_API_TOKEN", False)
        monkeypatch.setattr(settings, "GENESIS_API_TOKEN", "")


@pytest.mark.asyncio
async def test_long_term_database_auth_sessions_and_mirrors(isolated_genesis, monkeypatch):
    from backend.genesis import long_term

    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{isolated_genesis / 'genesis.db'}")
    monkeypatch.setattr(settings, "GENESIS_REQUIRE_API_TOKEN", True)
    monkeypatch.setattr(settings, "GENESIS_API_TOKEN", "")
    if long_term._CONN is not None:
        long_term._CONN.close()
    monkeypatch.setattr(long_term, "_CONN", None)
    monkeypatch.setattr(long_term, "_CONN_KEY", "")

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            status = await client.get("/api/genesis/long-term/status")
            assert status.status_code == 200
            assert status.json()["version"] == "organism-long-term-db-auth-v2"
            assert status.json()["database"]["connected"] is True

            bootstrapped = await client.post(
                "/api/genesis/auth/bootstrap",
                json={"username": "owner", "password": "longpassword123", "display_name": "Owner"},
            )
            assert bootstrapped.status_code == 200
            assert bootstrapped.json()["user"]["username"] == "owner"

            logged_in = await client.post(
                "/api/genesis/auth/login",
                json={"username": "owner", "password": "longpassword123"},
            )
            assert logged_in.status_code == 200
            session_token = logged_in.json()["token"]

            denied = await client.post(
                "/api/genesis/seed",
                json={"name": "db-denied", "goal": "Should require auth."},
            )
            assert denied.status_code == 401

            seeded = await client.post(
                "/api/genesis/seed",
                headers={"X-Genesis-Session": session_token},
                json={"name": "db-auth", "goal": "Persist into SQLite mirror."},
            )
            assert seeded.status_code == 200

            status = (await client.get("/api/genesis/status")).json()
            assert status["long_term"]["auth"]["users"] == 1
            assert status["long_term"]["database"]["tables"]["organism_records"] >= 1

            me = await client.get("/api/genesis/auth/me", headers={"X-Genesis-Session": session_token})
            assert me.status_code == 200
            assert me.json()["user"]["username"] == "owner"
    finally:
        monkeypatch.setattr(settings, "GENESIS_REQUIRE_API_TOKEN", False)
        monkeypatch.setattr(settings, "GENESIS_API_TOKEN", "")


def test_long_term_supports_supabase_postgres_url_redaction(monkeypatch):
    from backend.genesis import long_term

    url = "postgresql://postgres:secret-pass@db.project-ref.supabase.co:5432/postgres"
    assert long_term._database_engine(url) == "postgres"
    redacted = long_term._redacted_database_url(url)
    assert "secret-pass" not in redacted
    assert "postgres:***@db.project-ref.supabase.co:5432/postgres" in redacted


def test_store_rehydrates_runtime_json_from_long_term_mirror(isolated_genesis, monkeypatch):
    from backend.genesis import long_term, runtime
    from backend.genesis.types import Decision

    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{isolated_genesis / 'rehydrate.db'}")
    if long_term._CONN is not None:
        long_term._CONN.close()
    monkeypatch.setattr(long_term, "_CONN", None)
    monkeypatch.setattr(long_term, "_CONN_KEY", "")

    org = runtime.seed(intent_goal="Survive hosted restarts.", name="rehydrate")
    store.save_organism(org)
    decision = Decision(
        organism_id=org.id,
        trigger={"type": "restart_check", "payload": {"ok": True}},
        reasoning="Mirror survives a Render restart.",
        action={"name": "noop", "args": {}},
        result={"ok": True},
    )
    store.save_decision(decision)

    monkeypatch.setattr(store, "_BASE", isolated_genesis / "after-render-restart")

    rehydrated = store.load_organism(org.id)
    assert rehydrated is not None
    assert rehydrated.id == org.id
    assert store.load_decisions(org.id)[0].id == decision.id

    listed = store.list_organisms()
    assert [o.id for o in listed] == [org.id]


def test_render_production_normalizes_template_wildcards(monkeypatch):
    import importlib
    import backend.shared.config as config

    monkeypatch.setenv("GENESIS_ENV", "production")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://genesis-demo.onrender.com")
    monkeypatch.setenv("GENESIS_CORS_ORIGINS", "*")
    monkeypatch.setenv("GENESIS_TRUSTED_HOSTS", "*")
    reloaded = importlib.reload(config)
    try:
        assert reloaded.settings.GENESIS_CORS_ORIGINS == ["https://genesis-demo.onrender.com"]
        assert reloaded.settings.GENESIS_TRUSTED_HOSTS == ["genesis-demo.onrender.com"]
    finally:
        importlib.reload(config)


@pytest.mark.asyncio
async def test_webhook_source_gets_token_and_accepts_delivery(isolated_genesis):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        organism = (
            await client.post(
                "/api/genesis/seed",
                json={"name": "webhook", "goal": "Observe webhook events."},
            )
        ).json()["organism"]

        source_response = await client.post(
            f"/api/genesis/organisms/{organism['id']}/sources",
            json={"kind": "webhook", "type": "external_event"},
        )
        assert source_response.status_code == 200

        from backend.genesis import lifecycle

        await lifecycle._reconcile()
        updated = store.load_organism(organism["id"])
        token = updated.perception_sources[0]["token"]

        delivery_response = await client.post(
            f"/api/genesis/webhook/{token}",
            json={"hello": "world"},
        )
        assert delivery_response.status_code == 200
        assert delivery_response.json()["action"]["name"] in {
            "noop",
            "remember",
            "declare_done",
        }


@pytest.mark.asyncio
async def test_population_events_use_callback_signature(isolated_genesis, monkeypatch):
    from backend.genesis import population

    monkeypatch.setattr(population, "_BASE", isolated_genesis / "populations")
    population._BASE.mkdir(exist_ok=True)

    seen = []

    async def fake_perceive(organism_id, perception, event_callback=None, **kwargs):
        from backend.genesis.types import Decision

        decision = Decision(
            organism_id=organism_id,
            trigger=perception,
            reasoning="fake",
            action={"name": "noop", "args": {}},
            result={"ok": True},
        )
        store.save_decision(decision)
        return decision

    async def fake_critique(*args, **kwargs):
        return None

    monkeypatch.setattr("backend.genesis.runtime.perceive", fake_perceive)
    monkeypatch.setattr("backend.genesis.skills.distill.distill", fake_critique)

    from backend.genesis import events

    async def subscriber(event):
        seen.append(event["type"])

    events.subscribe(subscriber)
    try:
        run = population.new_run(
            task="Run a fast evolution smoke test.",
            perception={"type": "task"},
            n_organisms=2,
            max_generations=1,
            action_timeout_s=10,
        )
        population.save_run(run)
        await population._run_evolution(run["id"])
    finally:
        events.unsubscribe(subscriber)

    finished = population.load_run(run["id"])
    assert finished["status"] == "complete"
    assert "population.generation_start" in seen
    assert "population.complete" in seen

    report = population.build_evidence_report(finished)
    assert report["run_id"] == run["id"]
    assert report["generations_run"] == 1
    assert report["verdict"] in {
        "improved",
        "skills_distilled",
        "inconclusive",
        "not_started",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/genesis/population/{run['id']}/report")
        assert response.status_code == 200
        assert response.json()["claim"].startswith("Genesis shows evidence")


@pytest.mark.asyncio
async def test_population_benchmarks_track_regression_baselines(isolated_genesis, monkeypatch):
    from backend.genesis import population

    monkeypatch.setattr(population, "_BASE", isolated_genesis / "populations")
    population._BASE.mkdir(exist_ok=True)

    prior = population.new_run(
        task="Benchmark prior",
        perception={"type": "benchmark_task"},
        benchmark_id="repo_triage",
        n_organisms=2,
        max_generations=1,
    )
    prior["status"] = "complete"
    prior["created_at"] = "2026-01-01T00:00:00"
    prior["generations"] = [
        {
            "generation": 1,
            "scores": [{"organism_id": "old", "name": "old", "fitness": 0.8}],
            "survivor_ids": ["old"],
            "loser_ids": [],
            "skills_distilled": [],
            "best_fitness": 0.8,
            "mean_fitness": 0.8,
        }
    ]
    population.save_run(prior)

    current = population.new_run(
        task="Benchmark current",
        perception={"type": "benchmark_task"},
        benchmark_id="repo_triage",
        n_organisms=2,
        max_generations=1,
    )
    current["status"] = "complete"
    current["created_at"] = "2026-01-02T00:00:00"
    current["generations"] = [
        {
            "generation": 1,
            "scores": [{"organism_id": "new", "name": "new", "fitness": 0.7}],
            "survivor_ids": ["new"],
            "loser_ids": [],
            "skills_distilled": [],
            "best_fitness": 0.7,
            "mean_fitness": 0.7,
        }
    ]
    population.save_run(current)

    report = population.build_evidence_report(current)
    assert report["benchmark"]["id"] == "repo_triage"
    assert report["regression"]["previous_completed_runs"] == 1
    assert report["regression"]["previous_best_fitness"] == 0.8
    assert report["regression"]["delta_vs_previous_best"] == -0.1
    assert report["verdict"] == "regressed"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/genesis/population/benchmarks")
        assert response.status_code == 200
        summaries = response.json()["benchmarks"]
        triage = next(b for b in summaries if b["benchmark"]["id"] == "repo_triage")
        assert triage["completed_runs"] == 2
        assert triage["best_fitness"] == 0.8


@pytest.mark.asyncio
async def test_benchmark_alignment_scores_task_specific_rubric(isolated_genesis, monkeypatch):
    from backend.genesis import population
    from backend.genesis.types import Decision, Intent, MetaDecision, Organism

    monkeypatch.setattr(population, "_BASE", isolated_genesis / "populations")
    population._BASE.mkdir(exist_ok=True)

    org = Organism(
        name="triage_runner",
        intent=Intent(goal="Analyze repository health."),
    )
    store.save_organism(org)
    store.save_decision(Decision(
        organism_id=org.id,
        trigger={"type": "benchmark_task", "benchmark_id": "repo_triage"},
        reasoning=(
            "The best contribution is to implement a failing regression test, "
            "because it has high maintainer impact and lowers compatibility risk."
        ),
        action={"name": "remember", "args": {"pattern": "Prioritize tests with clear impact."}},
        result={"ok": True},
    ))
    store.save_meta_decision(MetaDecision(
        organism_id=org.id,
        decision_id="d_test",
        reasoning_quality=0.8,
        action_efficiency=0.7,
    ))

    score = population.score_organism(org.id, benchmark_id="repo_triage")
    assert score["benchmark_alignment"]["score"] == 1.0
    assert score["meta_fitness"] == 0.76
    assert score["fitness"] > score["meta_fitness"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/genesis/benchmarks/repo_triage")
        assert response.status_code == 200
        payload = response.json()
        assert payload["benchmark"]["id"] == "repo_triage"
        assert payload["benchmark"]["rubric"][0]["id"] == "concrete_contribution"


@pytest.mark.asyncio
async def test_agi2_memory_retrieval_and_curriculum(isolated_genesis, monkeypatch):
    from backend.genesis import memory, population
    from backend.genesis.types import Intent, Organism

    monkeypatch.setattr(memory, "_BASE", isolated_genesis / "memories")
    monkeypatch.setattr(memory, "_MEMORY_DIR", isolated_genesis / "memories" / "items")
    monkeypatch.setattr(memory, "_CURRICULUM_PATH", isolated_genesis / "memories" / "curriculum.json")
    monkeypatch.setattr(population, "_BASE", isolated_genesis / "populations")
    population._BASE.mkdir(exist_ok=True)

    item = memory.remember(
        "For repo triage, prefer a concrete regression test with clear maintainer impact.",
        kind="lesson",
        scope="benchmark",
        tags=["repo_triage", "test"],
        benchmark_id="repo_triage",
        score=0.9,
    )
    assert item is not None

    org = Organism(
        name="memory_user",
        intent=Intent(goal="Analyze repository health and choose a contribution."),
    )
    retrieved = memory.retrieve(
        org,
        {"type": "benchmark_task", "benchmark_id": "repo_triage", "description": "Repository contribution"},
    )
    assert retrieved
    assert retrieved[0].id == item.id

    run = population.new_run(
        task="Benchmark current",
        perception={"type": "benchmark_task"},
        benchmark_id="repo_triage",
        n_organisms=2,
        max_generations=1,
    )
    run["status"] = "complete"
    run["generations"] = [
        {
            "generation": 1,
            "scores": [{"organism_id": "new", "name": "new", "fitness": 0.66}],
            "survivor_ids": ["new"],
            "loser_ids": [],
            "skills_distilled": [],
            "best_fitness": 0.66,
            "mean_fitness": 0.5,
        }
    ]
    curriculum = memory.update_curriculum_from_run(run)
    assert curriculum["recommended_next"] == "repo_triage"
    assert memory.curriculum()["memory_count"] >= 2

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
      response = await client.get("/api/genesis/curriculum")
      assert response.status_code == 200


@pytest.mark.asyncio
async def test_agi3_tool_sandbox_runs_and_blocks_unsafe_imports(isolated_genesis, monkeypatch):
    from backend.genesis import tool_sandbox

    monkeypatch.setattr(tool_sandbox, "_BASE", isolated_genesis / "tool_runs")

    ok_run = await tool_sandbox.run_python(
        code="values = input_data['values']\nresult = {'total': sum(values), 'count': len(values)}",
        input_data={"values": [1, 2, 3]},
        purpose="sum values",
    )
    assert ok_run["ok"] is True
    assert ok_run["result"] == {"total": 6, "count": 3}

    blocked = await tool_sandbox.run_python(
        code="import os\nresult = os.listdir('.')",
        purpose="blocked import",
    )
    assert blocked["ok"] is False
    assert "not allowed" in blocked["error"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/genesis/tools/sandbox/runs")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_security_runtime_http_requires_allowlist_and_grant(isolated_genesis, monkeypatch):
    from backend.genesis import approvals, runtime

    monkeypatch.setattr(approvals, "_BASE", isolated_genesis / "approvals")
    monkeypatch.delenv("GENESIS_CONNECTOR_HTTP_ALLOWLIST", raising=False)

    localhost = await runtime._tool_http_request("GET", "http://127.0.0.1:8002/private", org_id="o_test")
    assert localhost["ok"] is False
    assert localhost["blocked"] is True
    assert localhost["reason"] == "private_or_local_ip_is_blocked"

    unlisted = await runtime._tool_http_request("GET", "https://example.com/data", org_id="o_test")
    assert unlisted["ok"] is False
    assert unlisted["reason"] == "url_not_in_GENESIS_CONNECTOR_HTTP_ALLOWLIST"

    monkeypatch.setenv("GENESIS_CONNECTOR_HTTP_ALLOWLIST", "https://example.com")
    no_grant = await runtime._tool_fetch_web_page("https://example.com/data", org_id="o_test")
    assert no_grant["ok"] is False
    assert no_grant["reason"] == "permission_grant_required"
    assert no_grant["approval_request"]["action_type"] == "external_api"
    assert no_grant["approval_request"]["payload"]["scope"] == "https://example.com"

    request = approvals.approve_request(no_grant["approval_request"]["id"], reviewed_by="human-a")
    executed = approvals.execute_request(request["id"], executed_by="human-a", grant_max_uses=1)
    grant_id = executed["execution_result"]["permission_grant"]["id"]

    blocked_method = await runtime._tool_http_request(
        "GET",
        "https://not-example.com/data",
        grant_id=grant_id,
        org_id="o_test",
    )
    assert blocked_method["ok"] is False
    assert blocked_method["reason"] == "url_not_in_GENESIS_CONNECTOR_HTTP_ALLOWLIST"


@pytest.mark.asyncio
async def test_security_mcp_forge_requires_deploy_grant_before_writing(isolated_genesis, monkeypatch):
    from backend.genesis import approvals, runtime

    monkeypatch.setattr(approvals, "_BASE", isolated_genesis / "approvals")
    org = runtime.seed(intent_goal="Test MCP forge gating.", name="forge-gate")
    store.save_organism(org)

    result = await runtime._tool_forge_mcp_server(
        name="../bad name",
        description="create a harmless test tool",
        org_id=org.id,
    )
    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["reason"] == "permission_grant_required"
    assert result["approval_request"]["action_type"] == "deploy_change"
    assert not (isolated_genesis / "organisms" / org.id / "mcps").exists()


@pytest.mark.asyncio
async def test_security_webhook_unknown_token_is_rejected(isolated_genesis):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/genesis/webhook/wh_unknown", json={"event": "x"})
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_security_auth_bootstrap_closes_after_first_user(isolated_genesis, monkeypatch):
    from backend.genesis import long_term

    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{isolated_genesis / 'auth-edge.db'}")
    if long_term._CONN is not None:
        long_term._CONN.close()
    monkeypatch.setattr(long_term, "_CONN", None)
    monkeypatch.setattr(long_term, "_CONN_KEY", "")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        too_short = await client.post(
            "/api/genesis/auth/bootstrap",
            json={"username": "ow", "password": "short", "display_name": "Owner"},
        )
        assert too_short.status_code == 422

        created = await client.post(
            "/api/genesis/auth/bootstrap",
            json={"username": "owner", "password": "longpassword123", "display_name": "Owner"},
        )
        assert created.status_code == 200

        second = await client.post(
            "/api/genesis/auth/bootstrap",
            json={"username": "other", "password": "longpassword456", "display_name": "Other"},
        )
        assert second.status_code == 409


@pytest.mark.asyncio
async def test_security_sandbox_blocks_file_and_eval_escape_attempts(isolated_genesis, monkeypatch):
    from backend.genesis import tool_sandbox

    monkeypatch.setattr(tool_sandbox, "_BASE", isolated_genesis / "tool_runs")
    file_attempt = await tool_sandbox.run_python(
        code="result = open('/etc/passwd').read()",
        purpose="file escape attempt",
    )
    assert file_attempt["ok"] is False
    assert "NameError" in file_attempt["error"]

    eval_attempt = await tool_sandbox.run_python(
        code="result = eval('1 + 1')",
        purpose="eval escape attempt",
    )
    assert eval_attempt["ok"] is False
    assert "NameError" in eval_attempt["error"]


@pytest.mark.asyncio
async def test_json_authoritative_reconciliation_repairs_sqlite_mirror(isolated_genesis, monkeypatch):
    from backend.genesis import long_term, runtime

    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{isolated_genesis / 'mirror.db'}")
    if long_term._CONN is not None:
        long_term._CONN.close()
    monkeypatch.setattr(long_term, "_CONN", None)
    monkeypatch.setattr(long_term, "_CONN_KEY", "")

    org = runtime.seed(intent_goal="Mirror me into SQLite.", name="mirror")
    store.save_organism(org)
    conn = long_term._connect()
    conn.execute("DELETE FROM organism_records WHERE id = ?", (org.id,))
    conn.commit()

    report = store.reconcile_long_term(repair=False)
    assert report["authority"] == "json_store"
    assert report["database"]["engine"] == "sqlite"
    assert org.id in report["missing_in_sqlite"]["organisms"]
    assert org.id in report["missing_in_database"]["organisms"]
    assert report["summary"]["missing_total"] >= 1

    repaired = store.reconcile_long_term(repair=True)
    assert repaired["ok"] is True
    assert repaired["repaired"]["organisms"] == 1
    assert repaired["summary"]["repaired_total"] >= 1


@pytest.mark.asyncio
async def test_reconciliation_repair_endpoint_requires_explicit_confirmation(isolated_genesis, monkeypatch):
    from backend.genesis import long_term, runtime

    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{isolated_genesis / 'repair-api.db'}")
    if long_term._CONN is not None:
        long_term._CONN.close()
    monkeypatch.setattr(long_term, "_CONN", None)
    monkeypatch.setattr(long_term, "_CONN_KEY", "")

    org = runtime.seed(intent_goal="Repair me only with confirmation.", name="repair-api")
    store.save_organism(org)
    conn = long_term._connect()
    conn.execute("DELETE FROM organism_records WHERE id = ?", (org.id,))
    conn.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post("/api/genesis/long-term/reconciliation/repair", json={"confirm": False})
        assert denied.status_code == 409

        repaired = await client.post("/api/genesis/long-term/reconciliation/repair", json={"confirm": True})
        assert repaired.status_code == 200
        body = repaired.json()
        assert body["ok"] is True
        assert body["summary"]["repaired_total"] >= 1


@pytest.mark.asyncio
async def test_organism_list_supports_filter_and_pagination(isolated_genesis):
    from backend.genesis import runtime

    alpha = runtime.seed(intent_goal="Find me with server-side search.", name="page-alpha")
    beta = runtime.seed(intent_goal="Keep me on another page.", name="page-beta")
    store.save_organism(alpha)
    store.save_organism(beta)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first_page = await client.get("/api/genesis/organisms?limit=1")
        assert first_page.status_code == 200
        assert len(first_page.json()["organisms"]) == 1
        assert first_page.json()["pagination"]["total"] >= 2
        assert first_page.json()["pagination"]["has_more"] is True

        filtered = await client.get("/api/genesis/organisms?q=page-alpha&limit=10")
        assert filtered.status_code == 200
        names = [item["name"] for item in filtered.json()["organisms"]]
        assert "page-alpha" in names
        assert "page-beta" not in names


def test_dev_reload_is_scoped_away_from_generated_state(monkeypatch):
    import backend.main as main

    monkeypatch.setattr(settings, "GENESIS_ENV", "development")
    monkeypatch.setattr(settings, "GENESIS_RELOAD", True)
    monkeypatch.setattr(settings, "GENESIS_RELOAD_DIRS", ["backend"])
    monkeypatch.setattr(settings, "GENESIS_RELOAD_EXCLUDES", ["organisms", "frontend/dist", "*.db"])

    options = main._uvicorn_reload_options()
    assert options["reload"] is True
    assert options["reload_dirs"] == ["backend"]
    assert "organisms" in options["reload_excludes"]
    assert "frontend/dist" in options["reload_excludes"]


@pytest.mark.asyncio
async def test_agi4_collaboration_debate_contract(isolated_genesis, monkeypatch):
    from backend.genesis import collaboration, memory

    monkeypatch.setattr(collaboration, "_BASE", isolated_genesis / "collaborations")
    monkeypatch.setattr(memory, "_BASE", isolated_genesis / "memories")
    monkeypatch.setattr(memory, "_MEMORY_DIR", isolated_genesis / "memories" / "items")
    monkeypatch.setattr(memory, "_CURRICULUM_PATH", isolated_genesis / "memories" / "curriculum.json")

    seen = []

    async def event_callback(event_type, payload):
        seen.append(event_type)

    debate = await collaboration.run_debate(
        topic="Should Module 4 require critique before synthesis?",
        context={"phase": "Module 4", "test": True},
        event_callback=event_callback,
    )
    assert debate["status"] == "complete"
    assert len(debate["proposals"]) == 3
    assert len(debate["critiques"]) == 3
    assert debate["synthesis"]["decision"]
    assert debate["synthesis"]["ranked_agents"]
    assert "collaboration.completed" in seen

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/genesis/collaboration/debates")
        assert response.status_code == 200
        assert any(d["id"] == debate["id"] for d in response.json()["debates"])


@pytest.mark.asyncio
async def test_agi5_self_improvement_strict_gates(isolated_genesis, monkeypatch):
    from backend.genesis import memory, self_improvement

    monkeypatch.setattr(self_improvement, "_BASE", isolated_genesis / "improvements")
    monkeypatch.setattr(memory, "_BASE", isolated_genesis / "memories")
    monkeypatch.setattr(memory, "_MEMORY_DIR", isolated_genesis / "memories" / "items")
    monkeypatch.setattr(memory, "_CURRICULUM_PATH", isolated_genesis / "memories" / "curriculum.json")

    seen = []

    async def event_callback(event_type, payload):
        seen.append(event_type)

    passing = await self_improvement.run_improvement_cycle(
        objective="Improve tool promotion safety.",
        context={"phase": "Module 5"},
        evidence={
            "benchmark_delta": 0.04,
            "regression_risk": 0.12,
            "confidence": 0.78,
            "checks": {"unit": True, "build": True, "browser": True},
        },
        event_callback=event_callback,
    )
    assert passing["status"] == "complete"
    assert passing["evaluation"]["promotable"] is True
    assert passing["promotion"]["state"] == "approved_for_experiment"
    assert "self_improvement.completed" in seen

    blocked = await self_improvement.run_improvement_cycle(
        objective="Ship a vague risky change.",
        candidate={
            "title": "Vague change",
            "problem": "Too short",
            "hypothesis": "Unclear",
            "change_summary": "Disable auth and bypass checks.",
            "expected_metrics": {},
            "tests": [],
            "rollback_plan": "",
            "safety_notes": [],
            "confidence": 0.2,
        },
        evidence={
            "benchmark_delta": -0.01,
            "regression_risk": 0.9,
            "confidence": 0.2,
            "checks": {"unit": False, "build": False, "browser": False},
        },
    )
    assert blocked["evaluation"]["promotable"] is False
    assert "benchmark_delta" in blocked["evaluation"]["blocked_by"]
    assert "safety_review" in blocked["evaluation"]["blocked_by"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/genesis/self-improvement/runs")
        assert response.status_code == 200
        assert any(r["id"] == passing["id"] for r in response.json()["runs"])


@pytest.mark.asyncio
async def test_agi6_persistent_operator_ticks_safely(isolated_genesis, monkeypatch):
    from backend.genesis import autonomous_operator, memory, self_improvement

    monkeypatch.setattr(autonomous_operator, "_BASE", isolated_genesis / "operators")
    monkeypatch.setattr(self_improvement, "_BASE", isolated_genesis / "improvements")
    monkeypatch.setattr(memory, "_BASE", isolated_genesis / "memories")
    monkeypatch.setattr(memory, "_MEMORY_DIR", isolated_genesis / "memories" / "items")
    monkeypatch.setattr(memory, "_CURRICULUM_PATH", isolated_genesis / "memories" / "curriculum.json")
    autonomous_operator._operator_tasks.clear()

    seen = []

    async def event_callback(event_type, payload):
        seen.append(event_type)

    operator = autonomous_operator.create_operator(
        goal="Keep Genesis improving with strict gates.",
        cadence_s=10,
        max_ticks=2,
    )
    assert operator["status"] == "active"

    ticked = await autonomous_operator.tick(operator["id"], event_callback=event_callback, manual=True)
    assert ticked["ticks"]
    first_tick = ticked["ticks"][0]
    assert first_tick["chosen_action"]["action"] in autonomous_operator.SAFE_ACTIONS
    assert first_tick["result"]["ok"] is True
    assert "operator.tick_completed" in seen

    paused = autonomous_operator.pause_operator(operator["id"])
    assert paused["status"] == "paused"
    resumed = autonomous_operator.resume_operator(operator["id"])
    assert resumed["status"] == "active"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/genesis/operators")
        assert response.status_code == 200
        assert any(op["id"] == operator["id"] for op in response.json()["operators"])


@pytest.mark.asyncio
async def test_agi7_human_approval_permission_layer(isolated_genesis, monkeypatch):
    from backend.genesis import approvals, autonomous_operator

    monkeypatch.setattr(approvals, "_BASE", isolated_genesis / "approvals")
    monkeypatch.setattr(autonomous_operator, "_BASE", isolated_genesis / "operators")
    autonomous_operator._operator_tasks.clear()

    seen = []

    async def event_callback(event_type, payload):
        seen.append(event_type)

    request = approvals.create_request(
        title="Approve dry-run connector call",
        action_type="external_api",
        reason="Verify that risky actions are blocked until reviewed.",
        requested_by="test",
        source="smoke",
        risk_level="high",
        payload={"operation": "dry_run", "target": "example"},
        permissions=["external_api"],
    )
    assert request["status"] == "pending"
    assert "human_approval" in request["permissions"]

    with pytest.raises(PermissionError):
        approvals.execute_request(request["id"])

    approved = approvals.approve_request(
        request["id"],
        reviewed_by="tester",
        note="Simulation is allowed.",
    )
    assert approved["status"] == "approved"

    executed = approvals.execute_request(request["id"], executed_by="gate")
    assert executed["status"] == "executed"
    assert executed["execution_result"]["simulated"] is True

    rejected = approvals.create_request(
        title="Reject destructive action",
        action_type="delete_data",
        reason="This should remain blocked.",
        risk_level="critical",
        permissions=["delete_data"],
    )
    rejected = approvals.reject_request(rejected["id"], reviewed_by="tester")
    assert rejected["status"] == "rejected"
    with pytest.raises(PermissionError):
        approvals.execute_request(rejected["id"])

    operator = autonomous_operator.create_operator(
        goal="Ask before using external connectors.",
        cadence_s=10,
        max_ticks=1,
    )
    chosen = {
        "action": "request_approval",
        "args": {
            "title": "Operator external API gate",
            "action_type": "external_api",
            "reason": "Operator wants future connector access.",
            "permissions": ["external_api"],
        },
    }
    result = await autonomous_operator._execute_action(operator, chosen, event_callback)
    assert result["ok"] is True
    assert result["approval_id"].startswith("apr_")
    assert "approval.requested" in seen

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/genesis/approvals")
        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["executed"] >= 1
        assert any(item["id"] == request["id"] for item in body["approvals"])

        create_response = await client.post(
            "/api/genesis/approvals",
            json={
                "title": "API approval",
                "action_type": "send_message",
                "reason": "Verify API create path.",
                "risk_level": "medium",
                "permissions": ["send_message"],
            },
        )
        assert create_response.status_code == 200
        api_request = create_response.json()["approval"]
        blocked_response = await client.post(
            f"/api/genesis/approvals/{api_request['id']}/execute",
            json={"executed_by": "test"},
        )
        assert blocked_response.status_code == 403


@pytest.mark.asyncio
async def test_agi8_scoped_permission_grants_gate_actions(isolated_genesis, monkeypatch):
    from backend.genesis import approvals

    monkeypatch.setattr(approvals, "_BASE", isolated_genesis / "approvals")

    request = approvals.create_request(
        title="Grant scoped external access",
        action_type="external_api",
        reason="Verify scoped grants control protected action execution.",
        requested_by="test",
        source="smoke",
        risk_level="high",
        payload={"target": "future_external_system"},
        permissions=["external_api"],
    )
    approvals.approve_request(request["id"], reviewed_by="tester")

    blocked = approvals.simulate_protected_action(
        grant_id="gr_missing",
        permission="external_api",
        action_type="external_api",
        scope="future_external_system",
    )
    assert blocked["ok"] is False
    assert blocked["blocked"] is True

    executed = approvals.execute_request(
        request["id"],
        executed_by="tester",
        grant_ttl_minutes=5,
        grant_max_uses=2,
    )
    grant = executed["execution_result"]["permission_grant"]
    assert grant["status"] == "active"
    assert grant["scope"] == "future_external_system"

    mismatch = approvals.validate_grant(
        grant["id"],
        permission="external_api",
        action_type="send_message",
        scope="future_external_system",
    )
    assert mismatch["ok"] is False
    assert mismatch["reason"] == "action_type_mismatch"

    first = approvals.simulate_protected_action(
        grant_id=grant["id"],
        permission="external_api",
        action_type="external_api",
        scope="future_external_system",
        actor="tool",
    )
    assert first["ok"] is True
    assert first["grant"]["uses"] == 1

    second = approvals.simulate_protected_action(
        grant_id=grant["id"],
        permission="external_api",
        action_type="external_api",
        scope="future_external_system",
        actor="tool",
    )
    assert second["ok"] is True
    assert second["grant"]["status"] == "exhausted"

    third = approvals.simulate_protected_action(
        grant_id=grant["id"],
        permission="external_api",
        action_type="external_api",
        scope="future_external_system",
        actor="tool",
    )
    assert third["ok"] is False
    assert third["reason"] == "grant_exhausted"

    revoke_request = approvals.create_request(
        title="Grant revocable messaging",
        action_type="send_message",
        reason="Verify revocation blocks a grant.",
        risk_level="medium",
        payload={"target": "team-channel"},
        permissions=["send_message"],
    )
    approvals.approve_request(revoke_request["id"], reviewed_by="tester")
    revoke_executed = approvals.execute_request(
        revoke_request["id"],
        executed_by="tester",
        grant_max_uses=3,
    )
    revoked = approvals.revoke_grant(
        revoke_executed["execution_result"]["permission_grant"]["id"],
        revoked_by="tester",
    )
    assert revoked["status"] == "revoked"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        grants_response = await client.get("/api/genesis/permissions/grants")
        assert grants_response.status_code == 200
        grants = grants_response.json()["grants"]
        assert any(item["id"] == grant["id"] for item in grants)

        denied = await client.post(
            "/api/genesis/permissions/simulate-action",
            json={
                "grant_id": "gr_missing",
                "permission": "external_api",
                "action_type": "external_api",
                "scope": "future_external_system",
            },
        )
        assert denied.status_code == 403


@pytest.mark.asyncio
async def test_agi9_connector_adapters_require_permission_grants(isolated_genesis, monkeypatch):
    from backend.genesis import approvals, connectors

    monkeypatch.setattr(approvals, "_BASE", isolated_genesis / "approvals")
    monkeypatch.setattr(connectors, "_BASE", isolated_genesis / "connectors")

    blocked = connectors.run_adapter(
        adapter_id="external_api",
        grant_id="gr_missing",
        scope="future_external_system",
        actor="tool",
        payload={"method": "POST"},
    )
    assert blocked["status"] == "blocked"
    assert blocked["result"]["reason"] == "grant_not_found"

    request = approvals.create_request(
        title="Allow external connector",
        action_type="external_api",
        reason="Verify Module 9 connector can use a matching grant.",
        risk_level="high",
        payload={"target": "future_external_system"},
        permissions=["external_api"],
    )
    approvals.approve_request(request["id"], reviewed_by="tester")
    executed = approvals.execute_request(
        request["id"],
        executed_by="tester",
        grant_max_uses=2,
    )
    grant = executed["execution_result"]["permission_grant"]

    unconfigured = connectors.run_adapter(
        adapter_id="external_api",
        grant_id=grant["id"],
        scope="future_external_system",
        actor="tool",
        payload={"method": "POST", "body": {"ok": True}},
    )
    assert unconfigured["status"] == "failed"
    assert unconfigured["result"]["ok"] is False
    assert "GENESIS_CONNECTOR_HTTP_ALLOWLIST" in unconfigured["result"]["error"]
    assert unconfigured["permission_check"]["grant"]["uses"] == 1

    wrong_scope = connectors.run_adapter(
        adapter_id="external_api",
        grant_id=grant["id"],
        scope="other-system",
        actor="tool",
        payload={},
    )
    assert wrong_scope["status"] == "blocked"
    assert wrong_scope["result"]["reason"] == "scope_mismatch"

    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            _ = self.rfile.read(int(self.headers.get("content-length", "0") or "0"))
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"received": true}')

        def log_message(self, *_args):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}/connector"
        monkeypatch.setenv("GENESIS_CONNECTOR_HTTP_ALLOWLIST", f"127.0.0.1")
        real_request = approvals.create_request(
            title="Allow real local HTTP connector",
            action_type="external_api",
            reason="Verify Module 9 connector performs a real HTTP request.",
            risk_level="high",
            payload={"target": endpoint},
            permissions=["external_api"],
        )
        approvals.approve_request(real_request["id"], reviewed_by="tester")
        real_grant = approvals.execute_request(
            real_request["id"],
            executed_by="tester",
            grant_max_uses=1,
        )["execution_result"]["permission_grant"]
        completed = connectors.run_adapter(
            adapter_id="external_api",
            grant_id=real_grant["id"],
            scope=endpoint,
            actor="tool",
            payload={"method": "POST", "endpoint": endpoint, "body": {"ok": True}},
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert completed["status"] == "complete"
    assert completed["result"]["simulated"] is False
    assert completed["result"]["output"]["status_code"] == 200

    monkeypatch.delenv("GENESIS_MESSAGE_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("GENESIS_SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("GENESIS_CONNECTOR_WEBHOOK_ALLOWLIST", raising=False)
    message_request = approvals.create_request(
        title="Allow message connector",
        action_type="send_message",
        reason="Verify API connector path.",
        risk_level="medium",
        payload={"target": "team-channel"},
        permissions=["send_message"],
    )
    approvals.approve_request(message_request["id"], reviewed_by="tester")
    message_grant = approvals.execute_request(
        message_request["id"],
        executed_by="tester",
    )["execution_result"]["permission_grant"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        adapters_response = await client.get("/api/genesis/connectors/adapters")
        assert adapters_response.status_code == 200
        assert any(item["id"] == "send_message" for item in adapters_response.json()["adapters"])

        run_response = await client.post(
            "/api/genesis/connectors/run",
            json={
                "adapter_id": "send_message",
                "grant_id": message_grant["id"],
                "scope": "team-channel",
                "actor": "api-test",
                "payload": {"message": "dry run"},
            },
        )
        assert run_response.status_code == 500
        assert run_response.json()["detail"]["status"] == "failed"
        assert "GENESIS_MESSAGE_WEBHOOK_URL" in run_response.json()["detail"]["result"]["error"]

        denied = await client.post(
            "/api/genesis/connectors/run",
            json={
                "adapter_id": "send_message",
                "grant_id": "gr_missing",
                "scope": "team-channel",
                "payload": {},
            },
        )
        assert denied.status_code == 403


@pytest.mark.asyncio
async def test_agi10_local_artifact_connector_writes_only_after_permission(isolated_genesis, monkeypatch):
    from backend.genesis import approvals, connectors

    monkeypatch.setattr(approvals, "_BASE", isolated_genesis / "approvals")
    monkeypatch.setattr(connectors, "_BASE", isolated_genesis / "connectors")

    artifact_dir = isolated_genesis / "connectors" / "artifacts"
    blocked = connectors.run_adapter(
        adapter_id="local_artifact_write",
        grant_id="gr_missing",
        scope="local-artifacts",
        actor="tool",
        payload={"filename": "../agi10-proof.txt", "content": "should not write"},
    )
    assert blocked["status"] == "blocked"
    assert not artifact_dir.exists()

    request = approvals.create_request(
        title="Allow local artifact connector",
        action_type="file_upload",
        reason="Verify Module 10 local connector can write only with a matching grant.",
        risk_level="medium",
        payload={"target": "local-artifacts"},
        permissions=["file_upload"],
    )
    approvals.approve_request(request["id"], reviewed_by="tester")
    executed = approvals.execute_request(
        request["id"],
        executed_by="tester",
        grant_max_uses=2,
    )
    grant = executed["execution_result"]["permission_grant"]

    completed = connectors.run_adapter(
        adapter_id="local_artifact_write",
        grant_id=grant["id"],
        scope="local-artifacts",
        actor="tool",
        payload={
            "filename": "../agi10-proof.txt",
            "content": "Module 10 proof",
            "metadata": {"phase": "Module 10"},
        },
    )
    assert completed["status"] == "complete"
    assert completed["result"]["simulated"] is False
    output = completed["result"]["output"]
    path = Path(output["path"])
    assert path.exists()
    assert path.parent == artifact_dir
    assert path.name == "agi10-proof.txt"
    assert "Module 10 proof" in path.read_text(encoding="utf-8")

    wrong_scope = connectors.run_adapter(
        adapter_id="local_artifact_write",
        grant_id=grant["id"],
        scope="other-artifacts",
        actor="tool",
        payload={"filename": "scope-fail.txt", "content": "blocked"},
    )
    assert wrong_scope["status"] == "blocked"
    assert wrong_scope["result"]["reason"] == "scope_mismatch"
    assert not (artifact_dir / "scope-fail.txt").exists()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        artifacts_response = await client.get("/api/genesis/connectors/artifacts")
        assert artifacts_response.status_code == 200
        assert any(item["filename"] == "agi10-proof.txt" for item in artifacts_response.json()["artifacts"])

        api_request = approvals.create_request(
            title="Allow API local artifact connector",
            action_type="file_upload",
            reason="Verify API path writes with scoped grant.",
            risk_level="medium",
            payload={"target": "local-artifacts"},
            permissions=["file_upload"],
        )
        approvals.approve_request(api_request["id"], reviewed_by="tester")
        api_grant = approvals.execute_request(
            api_request["id"],
            executed_by="tester",
        )["execution_result"]["permission_grant"]

        run_response = await client.post(
            "/api/genesis/connectors/run",
            json={
                "adapter_id": "local_artifact_write",
                "grant_id": api_grant["id"],
                "scope": "local-artifacts",
                "actor": "api-test",
                "payload": {"filename": "api-agi10-proof.txt", "content": "API module 10 proof"},
            },
        )
        assert run_response.status_code == 200
        assert run_response.json()["run"]["result"]["simulated"] is False
        assert (artifact_dir / "api-agi10-proof.txt").exists()


@pytest.mark.asyncio
async def test_real_connector_configuration_and_github_adapter(isolated_genesis, monkeypatch):
    from backend.genesis import approvals, connectors

    monkeypatch.setattr(approvals, "_BASE", isolated_genesis / "approvals")
    monkeypatch.setattr(connectors, "_BASE", isolated_genesis / "connectors")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("GENESIS_GITHUB_REPOSITORIES", "owner/repo")

    class FakeResponse:
        status_code = 201
        headers = {"content-type": "application/json"}
        text = '{"number": 42, "html_url": "https://github.com/owner/repo/issues/42", "title": "Real issue"}'

        def json(self):
            return {
                "number": 42,
                "html_url": "https://github.com/owner/repo/issues/42",
                "title": "Real issue",
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, endpoint, headers=None, json=None):
            assert endpoint == "https://api.github.com/repos/owner/repo/issues"
            assert headers["Authorization"] == "Bearer ghp_test"
            assert json["title"] == "Real issue"
            return FakeResponse()

        def request(self, method, endpoint, headers=None):
            assert method == "GET"
            assert endpoint == "https://api.github.com/repos/owner/repo"
            assert headers["Authorization"] == "Bearer ghp_test"
            response = FakeResponse()
            response.status_code = 200
            response.text = '{"full_name": "owner/repo"}'
            return response

    monkeypatch.setattr(connectors.httpx, "Client", FakeClient)

    configuration = connectors.connector_configuration()
    github_status = next(item for item in configuration["adapters"] if item["adapter_id"] == "github_create_issue")
    assert github_status["configured"] is True
    assert configuration["fake_success_allowed"] is False

    blocked_probe = connectors.probe_adapter(adapter_id="github_create_issue", scope="other/repo")
    assert blocked_probe["status"] == "fail"
    assert blocked_probe["configured"] is True
    assert blocked_probe["allowed"] is False

    live_probe = connectors.probe_adapter(adapter_id="github_create_issue", scope="owner/repo", live=True)
    assert live_probe["status"] == "pass"
    assert live_probe["configured"] is True
    assert live_probe["allowed"] is True
    assert live_probe["live_checked"] is True

    request = approvals.create_request(
        title="Allow GitHub issue connector",
        action_type="external_api",
        reason="Verify GitHub issue adapter performs a real configured connector call.",
        risk_level="high",
        payload={"target": "owner/repo"},
        permissions=["external_api"],
    )
    approvals.approve_request(request["id"], reviewed_by="tester")
    grant = approvals.execute_request(request["id"], executed_by="tester")["execution_result"]["permission_grant"]

    run = connectors.run_adapter(
        adapter_id="github_create_issue",
        grant_id=grant["id"],
        scope="owner/repo",
        actor="test",
        payload={"title": "Real issue", "body": "Created by test."},
    )
    assert run["status"] == "complete"
    assert run["result"]["simulated"] is False
    assert run["result"]["output"]["number"] == 42

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/genesis/connectors/configuration")
        assert response.status_code == 200
        assert response.json()["version"] == "genesis-real-connector-configuration-v1"

        probe_response = await client.post(
            "/api/genesis/connectors/probe",
            json={"adapter_id": "github_create_issue", "scope": "owner/repo", "live": True},
        )
        assert probe_response.status_code == 200
        assert probe_response.json()["probe"]["status"] == "pass"


@pytest.mark.asyncio
async def test_agi11_policy_review_requires_strict_confirmation(isolated_genesis, monkeypatch):
    from backend.genesis import approvals

    monkeypatch.setattr(approvals, "_BASE", isolated_genesis / "approvals")

    request = approvals.create_request(
        title="Strict local artifact review",
        action_type="file_upload",
        reason="Verify Module 11 binds execution confirmation to the review packet.",
        risk_level="high",
        payload={"target": "local-artifacts", "filename": "agi11-proof.txt"},
        permissions=["file_upload"],
    )
    packet = approvals.policy_review_packet(request)
    assert packet["verdict"] == "review_required"
    assert packet["confirmation_phrase"].startswith(f"CONFIRM {request['id']}")
    assert "strict_execution_confirmation" in packet["required_confirmations"]

    approvals.approve_request(request["id"], reviewed_by="tester")
    with pytest.raises(PermissionError):
        approvals.execute_request(
            request["id"],
            executed_by="tester",
            require_confirmation=True,
        )

    with pytest.raises(PermissionError):
        approvals.confirm_execution(
            request["id"],
            confirmed_by="tester",
            confirmation_phrase="CONFIRM wrong",
        )

    confirmed = approvals.confirm_execution(
        request["id"],
        confirmed_by="tester",
        confirmation_phrase=packet["confirmation_phrase"],
        note="Evidence hash reviewed.",
    )
    assert confirmed["execution_confirmation"]["evidence_hash"] == packet["evidence_hash"]

    executed = approvals.execute_request(
        request["id"],
        executed_by="tester",
        require_confirmation=True,
    )
    assert executed["status"] == "executed"
    assert executed["execution_result"]["policy_review"]["evidence_hash"] == packet["evidence_hash"]
    assert executed["execution_result"]["permission_grant"]["status"] == "active"

    handoff = approvals.create_request(
        title="Credential handoff",
        action_type="credential_access",
        reason="Verify credential requests cannot be approved by Genesis.",
        risk_level="critical",
        payload={"target": "password-vault"},
        permissions=["credential_access"],
    )
    assert approvals.policy_review_packet(handoff)["verdict"] == "handoff_required"
    with pytest.raises(PermissionError):
        approvals.approve_request(handoff["id"], reviewed_by="tester")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        api_request = approvals.create_request(
            title="API strict confirmation",
            action_type="file_upload",
            reason="Verify Module 11 API policy and confirmation routes.",
            risk_level="high",
            payload={"target": "local-artifacts"},
            permissions=["file_upload"],
        )
        policy_response = await client.get(f"/api/genesis/approvals/{api_request['id']}/policy")
        assert policy_response.status_code == 200
        api_packet = policy_response.json()["policy"]

        approve_response = await client.post(
            f"/api/genesis/approvals/{api_request['id']}/approve",
            json={"reviewed_by": "tester", "note": "Reviewed policy packet."},
        )
        assert approve_response.status_code == 200

        blocked_execute = await client.post(
            f"/api/genesis/approvals/{api_request['id']}/execute",
            json={"executed_by": "tester", "require_confirmation": True},
        )
        assert blocked_execute.status_code == 403

        confirm_response = await client.post(
            f"/api/genesis/approvals/{api_request['id']}/confirm-execution",
            json={
                "confirmed_by": "tester",
                "confirmation_phrase": api_packet["confirmation_phrase"],
                "note": "Confirmed exact evidence hash.",
            },
        )
        assert confirm_response.status_code == 200

        execute_response = await client.post(
            f"/api/genesis/approvals/{api_request['id']}/execute",
            json={"executed_by": "tester", "require_confirmation": True},
        )
        assert execute_response.status_code == 200
        assert execute_response.json()["approval"]["execution_result"]["execution_confirmation"]["evidence_hash"] == api_packet["evidence_hash"]


@pytest.mark.asyncio
async def test_agi12_approval_integrity_detects_tampering(isolated_genesis, monkeypatch):
    from backend.genesis import approvals
    import json

    monkeypatch.setattr(approvals, "_BASE", isolated_genesis / "approvals")

    request = approvals.create_request(
        title="Integrity stamped approval",
        action_type="file_upload",
        reason="Verify Module 12 stamps and verifies approval integrity.",
        risk_level="medium",
        payload={"target": "local-artifacts"},
        permissions=["file_upload"],
    )
    verified = approvals.verify_approval_integrity(request["id"])
    assert verified["integrity"]["ok"] is True
    assert verified["integrity"]["stored_hash"] == request["integrity"]["hash"]

    approvals.approve_request(request["id"], reviewed_by="tester")
    executed = approvals.execute_request(request["id"], executed_by="tester")
    grant = executed["execution_result"]["permission_grant"]
    grant_verified = approvals.verify_grant_integrity(grant["id"])
    assert grant_verified["integrity"]["ok"] is True

    path = approvals._path(request["id"])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["title"] = "Tampered approval title"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    tampered = approvals.verify_approval_integrity(request["id"])
    assert tampered["integrity"]["ok"] is False
    assert tampered["integrity"]["reason"] == "integrity_mismatch"

    report = approvals.integrity_report(limit=20)
    assert report["ok"] is False
    assert any(item["record_id"] == request["id"] for item in report["failures"])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        api_request = approvals.create_request(
            title="API integrity approval",
            action_type="file_upload",
            reason="Verify Module 12 API integrity route.",
            risk_level="medium",
            payload={"target": "local-artifacts"},
            permissions=["file_upload"],
        )
        response = await client.get(f"/api/genesis/approvals/{api_request['id']}/integrity")
        assert response.status_code == 200
        assert response.json()["integrity"]["ok"] is True

        report_response = await client.get("/api/genesis/approvals/integrity?limit=20")
        assert report_response.status_code == 200
        assert report_response.json()["summary"]["failure_count"] >= 1


@pytest.mark.asyncio
async def test_agi13_approval_quorum_and_break_glass(isolated_genesis, monkeypatch):
    from backend.genesis import approvals

    monkeypatch.setattr(approvals, "_BASE", isolated_genesis / "approvals")

    request = approvals.create_request(
        title="Critical dual-control approval",
        action_type="deploy_change",
        reason="Verify Module 13 requires distinct reviewer quorum.",
        risk_level="critical",
        payload={"target": "production-runtime"},
        permissions=["deploy_change"],
    )
    assert request["approval_controls"]["required_approvals"] == 2

    first = approvals.approve_request(request["id"], reviewed_by="reviewer_alpha")
    assert first["status"] == "pending"
    assert first["approval_controls"]["received_approvals"] == 1
    with pytest.raises(ValueError):
        approvals.approve_request(request["id"], reviewed_by="reviewer_alpha")
    with pytest.raises(PermissionError):
        approvals.execute_request(request["id"], executed_by="tester")

    second = approvals.approve_request(request["id"], reviewed_by="reviewer_beta")
    assert second["status"] == "approved"
    assert second["approval_controls"]["quorum_satisfied"] is True
    executed = approvals.execute_request(request["id"], executed_by="tester")
    assert executed["execution_result"]["permission_grant"]["status"] == "active"

    emergency = approvals.create_request(
        title="Emergency break-glass",
        action_type="external_api",
        reason="Verify Module 13 emergency access is bounded and audited.",
        risk_level="critical",
        payload={"target": "incident-response-api"},
        permissions=["external_api"],
    )
    broken = approvals.break_glass_request(
        emergency["id"],
        invoked_by="incident_commander",
        justification="Production incident drill requires immediate one-use emergency access.",
        grant_ttl_minutes=99,
    )
    grant = broken["execution_result"]["permission_grant"]
    assert broken["status"] == "break_glass"
    assert grant["break_glass"]["active"] is True
    assert grant["break_glass"]["ttl_minutes"] == 15
    assert grant["max_uses"] == 1

    first_use = approvals.validate_grant(
        grant["id"],
        permission="external_api",
        action_type="external_api",
        scope="incident-response-api",
        consume=True,
        actor="tester",
    )
    assert first_use["ok"] is True
    second_use = approvals.validate_grant(
        grant["id"],
        permission="external_api",
        action_type="external_api",
        scope="incident-response-api",
        consume=True,
        actor="tester",
    )
    assert second_use["ok"] is False
    assert second_use["reason"] == "grant_exhausted"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        api_request = approvals.create_request(
            title="API quorum approval",
            action_type="deploy_change",
            reason="Verify Module 13 API quorum route.",
            risk_level="critical",
            payload={"target": "production-runtime"},
            permissions=["deploy_change"],
        )
        first_response = await client.post(
            f"/api/genesis/approvals/{api_request['id']}/approve",
            json={"reviewed_by": "api_alpha", "note": "First review."},
        )
        assert first_response.status_code == 200
        assert first_response.json()["approval"]["status"] == "pending"
        second_response = await client.post(
            f"/api/genesis/approvals/{api_request['id']}/approve",
            json={"reviewed_by": "api_beta", "note": "Second review."},
        )
        assert second_response.status_code == 200
        assert second_response.json()["approval"]["status"] == "approved"

        break_request = approvals.create_request(
            title="API break glass",
            action_type="external_api",
            reason="Verify Module 13 API break-glass route.",
            risk_level="critical",
            payload={"target": "incident-response-api"},
            permissions=["external_api"],
        )
        break_response = await client.post(
            f"/api/genesis/approvals/{break_request['id']}/break-glass",
            json={
                "invoked_by": "api_incident_commander",
                "justification": "API drill requires immediate audited one-use emergency access.",
                "grant_ttl_minutes": 15,
            },
        )
        assert break_response.status_code == 200
        assert break_response.json()["approval"]["status"] == "break_glass"


@pytest.mark.asyncio
async def test_agi14_to_23_assurance_operations_layer(isolated_genesis, monkeypatch):
    from backend.genesis import approvals, autonomous_operator, connectors, governance

    monkeypatch.setattr(approvals, "_BASE", isolated_genesis / "approvals")
    monkeypatch.setattr(connectors, "_BASE", isolated_genesis / "connectors")
    monkeypatch.setattr(autonomous_operator, "_BASE", isolated_genesis / "operators")
    monkeypatch.setattr(governance, "_BASE", isolated_genesis / "governance")
    autonomous_operator._operator_tasks.clear()

    scored = governance.risk_score(
        action_type="deploy_change",
        payload={"target": "production-runtime"},
        permissions=["deploy_change", "human_approval"],
    )
    assert scored["score"] >= 55
    assert scored["risk_level"] in {"high", "critical"}

    registry = governance.capability_registry()
    assert registry["capabilities"]["deploy_change"]["requires_strict_confirmation"] is True
    assert "credential_vault_access" in registry["impossible"]

    request = approvals.create_request(
        title="Replayable assurance approval",
        action_type="deploy_change",
        reason="Validate replay and evidence vault.",
        risk_level="critical",
        payload={"target": "production-runtime"},
        permissions=["deploy_change"],
    )
    bound = governance.bind_intent(
        request["id"],
        user_intent="Validate replay and evidence for production runtime deployment controls.",
        bound_by="tester",
    )
    assert bound["intent_binding"]["drift"]["ok"] is True
    approvals.approve_request(request["id"], reviewed_by="alpha")
    approvals.approve_request(request["id"], reviewed_by="beta")
    executed = approvals.execute_request(request["id"], executed_by="tester")

    replay = governance.replay_approval(executed["id"])
    assert replay["decision"] == "allow"
    assert replay["integrity"]["ok"] is True

    evidence = governance.create_evidence_bundle(executed["id"])
    assert evidence["evidence_hash"]
    assert governance.list_evidence(limit=5)[0]["id"] == evidence["id"]

    operator = autonomous_operator.create_operator(goal="Pause during lockdown.", name="lockdown_test")
    assert operator["status"] == "active"
    lockdown = governance.set_lockdown(locked=True, reason="Test lockdown.", actor="tester")
    assert lockdown["locked"] is True
    assert autonomous_operator.get_operator(operator["id"])["status"] == "paused"
    assert approvals.get_grant(executed["execution_result"]["permission_grant"]["id"])["status"] == "revoked"
    assert governance.set_lockdown(locked=False, reason="Lift test lockdown.", actor="tester")["locked"] is False

    eval_run = governance.evaluation_monitor()
    assert any(check["name"] == "capability_registry" for check in eval_run["checks"])
    assert governance.production_connector_plan()["adapters"]
    readiness = governance.production_readiness()
    assert any(check["name"] == "lockdown_available" for check in readiness["checks"])
    dashboard = governance.accountability_dashboard()
    assert dashboard["counts"]["approvals"] >= 1

    drill = governance.run_assurance_drill()
    assert drill["replay"]["decision"] == "allow"
    assert drill["evidence"]["evidence_hash"]
    assert drill["evaluation"]["checks"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status_response = await client.get("/api/genesis/governance/status")
        assert status_response.status_code == 200
        assert "Module 23" in status_response.json()["phases"]

        score_response = await client.post(
            "/api/genesis/governance/risk-score",
            json={
                "action_type": "send_message",
                "payload": {"target": "public-channel"},
                "permissions": ["send_message"],
            },
        )
        assert score_response.status_code == 200
        assert score_response.json()["score"] > 0

        replay_response = await client.get(f"/api/genesis/governance/approvals/{drill['approval']['id']}/replay")
        assert replay_response.status_code == 200
        assert replay_response.json()["replay"]["decision"] == "allow"

        eval_response = await client.post("/api/genesis/governance/evaluations/run")
        assert eval_response.status_code == 200
        assert eval_response.json()["evaluation"]["checks"]


@pytest.mark.asyncio
async def test_agi24_to_33_capability_growth_layer(isolated_genesis, monkeypatch):
    from backend.genesis import approvals, autonomous_operator, capabilities, connectors, governance

    monkeypatch.setattr(approvals, "_BASE", isolated_genesis / "approvals")
    monkeypatch.setattr(connectors, "_BASE", isolated_genesis / "connectors")
    monkeypatch.setattr(autonomous_operator, "_BASE", isolated_genesis / "operators")
    monkeypatch.setattr(governance, "_BASE", isolated_genesis / "governance")
    monkeypatch.setattr(capabilities, "_BASE", isolated_genesis / "capabilities")
    autonomous_operator._operator_tasks.clear()

    graph = capabilities.create_task_graph(
        goal="Ship capability layer",
        tasks=[
            {"id": "a", "title": "Plan", "depends_on": []},
            {"id": "b", "title": "Build", "depends_on": ["a"]},
        ],
    )
    assert graph["summary"]["ready"] == 1
    with pytest.raises(PermissionError):
        capabilities.complete_task(graph["id"], "b", result="too soon")
    graph = capabilities.complete_task(graph["id"], "a", result="planned")
    assert any(task["id"] == "b" and task["status"] == "ready" for task in graph["tasks"])

    memory_item = capabilities.remember_project(title="Capability note", text="Durable project memory works.", tags=["module-25"])
    assert memory_item["memory_hash"]
    verification = capabilities.verify_tool_result(
        goal="Durable project memory works",
        result={"message": "Durable project memory works."},
    )
    assert verification["ok"] is True
    diagnostics = capabilities.self_heal_diagnostics()
    assert diagnostics["checks"]
    research = capabilities.research_loop(
        question="What changed?",
        sources=[{"title": "Planner", "url": "local://planner", "claim": "Task graphs track dependency states."}],
    )
    assert research["confidence"] >= 0.5
    route = capabilities.route_model(task_type="planning", risk_level="critical", reasoning_depth="high")
    assert route["model"] == "gpt-5.5"
    skill = capabilities.compile_skill_v2(name="Test workflow", workflow=["Plan", "Verify"])
    assert skill["skill_hash"]
    checkpoint = capabilities.create_session_checkpoint(summary="Capability layer complete.", open_items=["review later"])
    assert checkpoint["checkpoint_hash"]
    preference = capabilities.learn_preference(key="pace", value="finish end-to-end")
    assert preference["confidence"] == 1.0
    deployment = capabilities.deployment_pipeline()
    assert "rollback_if_needed" in deployment["stages"]

    drill = capabilities.run_capability_drill()
    assert drill["task_graph"]["summary"]["done"] == 1
    assert drill["verification"]["ok"] is True
    assert drill["deployment"]["checks"]
    status = capabilities.capability_status()
    assert "Module 33" in status["phases"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status_response = await client.get("/api/genesis/capabilities/status")
        assert status_response.status_code == 200
        assert "Module 24" in status_response.json()["phases"]

        drill_response = await client.post("/api/genesis/capabilities/drill")
        assert drill_response.status_code == 200
        assert drill_response.json()["verification"]["ok"] is True

        create_response = await client.post(
            "/api/genesis/capabilities/task-graphs",
            json={
                "goal": "API task graph",
                "tasks": [
                    {"id": "one", "title": "First", "depends_on": []},
                    {"id": "two", "title": "Second", "depends_on": ["one"]},
                ],
            },
        )
        assert create_response.status_code == 200
        api_graph = create_response.json()["task_graph"]
        complete_response = await client.post(
            f"/api/genesis/capabilities/task-graphs/{api_graph['id']}/tasks/one/complete",
            json={"result": "done"},
        )
        assert complete_response.status_code == 200
        assert any(task["id"] == "two" and task["status"] == "ready" for task in complete_response.json()["task_graph"]["tasks"])

        research_response = await client.post(
            "/api/genesis/capabilities/research",
            json={
                "question": "How does planning work?",
                "sources": [{"title": "Graph", "url": "local://graph", "claim": "Task graphs expose ready states."}],
            },
        )
        assert research_response.status_code == 200
        assert research_response.json()["research"]["research_hash"]


@pytest.mark.asyncio
async def test_agi34_to_43_product_intelligence_layer(isolated_genesis, monkeypatch):
    from backend.genesis import approvals, autonomous_operator, capabilities, connectors, governance, intelligence

    monkeypatch.setattr(approvals, "_BASE", isolated_genesis / "approvals")
    monkeypatch.setattr(connectors, "_BASE", isolated_genesis / "connectors")
    monkeypatch.setattr(autonomous_operator, "_BASE", isolated_genesis / "operators")
    monkeypatch.setattr(governance, "_BASE", isolated_genesis / "governance")
    monkeypatch.setattr(capabilities, "_BASE", isolated_genesis / "capabilities")
    monkeypatch.setattr(intelligence, "_BASE", isolated_genesis / "intelligence")
    autonomous_operator._operator_tasks.clear()

    capabilities.run_capability_drill()

    kg = intelligence.build_knowledge_graph()
    assert kg["version"] == "module-34-v1"
    assert kg["summary"]["nodes"] >= 1
    assert kg["graph_hash"]

    contract = intelligence.create_goal_contract(goal="Ship release", success_criteria=["tests pass"])
    assert contract["version"] == "module-35-v1"
    assert contract["contract_hash"]

    suite = intelligence.generate_tests(target="release-manager")
    assert suite["version"] == "module-36-v1"
    assert suite["coverage_evidence"]["count"] >= 1

    env = intelligence.environment_awareness()
    assert env["version"] == "module-37-v1"
    assert env["files"]["tests"] is True

    incident = intelligence.incident_response(title="Broken preview", severity="high")
    assert incident["version"] == "module-38-v1"
    assert incident["mitigations"][0] == "enable lockdown if external side effects are suspected"

    classification = intelligence.classify_data(name="customer note", sample="customer email token")
    assert classification["version"] == "module-39-v1"
    assert classification["sensitivity"] == "restricted"

    marketplace = intelligence.connector_marketplace()
    assert marketplace["version"] == "module-40-v1"
    assert marketplace["summary"]["total"] >= 1

    feedback = intelligence.record_feedback(target="release", rating=5)
    assert feedback["version"] == "module-41-v1"
    assert feedback["learning"] == "reinforce"

    resources = intelligence.resource_governor(model_calls=10, connector_runs=2, storage_mb=20)
    assert resources["version"] == "module-42-v1"
    assert resources["recommendation"] in {"within_budget", "throttle_nonessential_work"}

    release = intelligence.release_manager(version="module-43.0")
    assert release["version"] == "module-43-v1"
    assert release["release_hash"]
    assert release["readiness_score"] >= 70

    drill = intelligence.run_intelligence_drill()
    assert drill["version"] == "module-34-43-v1"
    assert drill["release"]["version"] == "module-43-v1"
    assert drill["data_governance"]["sensitivity"] == "confidential"

    status = intelligence.intelligence_status()
    assert "Module 43" in status["phases"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status_response = await client.get("/api/genesis/intelligence/status")
        assert status_response.status_code == 200
        assert "Module 34" in status_response.json()["phases"]

        drill_response = await client.post("/api/genesis/intelligence/drill")
        assert drill_response.status_code == 200
        assert drill_response.json()["release"]["release_hash"]

        graph_response = await client.get("/api/genesis/intelligence/knowledge-graph")
        assert graph_response.status_code == 200
        assert graph_response.json()["knowledge_graph"]["graph_hash"]

        classify_response = await client.post(
            "/api/genesis/intelligence/data/classify",
            json={"name": "credential sample", "sample": "password token", "declared_level": "internal"},
        )
        assert classify_response.status_code == 200
        assert classify_response.json()["classification"]["sensitivity"] == "restricted"

        release_response = await client.post(
            "/api/genesis/intelligence/releases",
            json={"version": "module-43.1", "changes": ["API release gate"]},
        )
        assert release_response.status_code == 200
        assert release_response.json()["release"]["release_version"] == "module-43.1"


@pytest.mark.asyncio
async def test_agi44_to_53_reliability_mission_layer(isolated_genesis, monkeypatch):
    from backend.genesis import approvals, autonomous_operator, capabilities, connectors, governance, intelligence, reliability

    monkeypatch.setattr(approvals, "_BASE", isolated_genesis / "approvals")
    monkeypatch.setattr(connectors, "_BASE", isolated_genesis / "connectors")
    monkeypatch.setattr(autonomous_operator, "_BASE", isolated_genesis / "operators")
    monkeypatch.setattr(governance, "_BASE", isolated_genesis / "governance")
    monkeypatch.setattr(capabilities, "_BASE", isolated_genesis / "capabilities")
    monkeypatch.setattr(intelligence, "_BASE", isolated_genesis / "intelligence")
    monkeypatch.setattr(reliability, "_BASE", isolated_genesis / "reliability")
    autonomous_operator._operator_tasks.clear()

    pack = reliability.create_benchmark_pack(name="Reliability gates", focus=["planning", "release"])
    assert pack["version"] == "module-44-v1"
    assert len(pack["cases"]) == 2

    scenario = reliability.simulate_scenario(mission="Recover a broken preview")
    assert scenario["version"] == "module-45-v1"
    assert "approval_required" in scenario["failure_modes"]

    plan = reliability.long_horizon_plan(goal="Ship mission execution", horizon_days=10)
    assert plan["version"] == "module-46-v1"
    assert plan["milestones"][-1]["day"] == 10

    trust = reliability.trust_dashboard()
    assert trust["version"] == "module-47-v1"
    assert trust["dashboard_hash"]

    workstyle = reliability.remember_workstyle(preference="pace", value="finish end-to-end")
    assert workstyle["version"] == "module-48-v1"
    assert workstyle["delete_supported"] is True

    env = reliability.environment_manager(required_env=["PORT"])
    assert env["version"] == "module-49-v1"
    assert env["checks"][0]["key"] == "PORT"

    route = reliability.model_router(task_type="release", risk_level="high")
    assert route["version"] == "module-50-v1"
    assert route["estimated_cost_tier"] == "high"

    mission = reliability.mission_runner(goal="Run safe mission")
    assert mission["version"] == "module-51-v1"
    assert mission["task_graph"]["summary"]["ready"] >= 1

    replay = reliability.observability_replay(run_id=mission["id"])
    assert replay["version"] == "module-52-v1"
    assert replay["checkpoint"]["replayable"] is True

    package = reliability.deployment_package(target="local-preview")
    assert package["version"] == "module-53-v1"
    assert package["health_checks"]

    drill = reliability.run_reliability_drill()
    assert drill["version"] == "module-44-53-v1"
    assert drill["mission_runner"]["version"] == "module-51-v1"
    assert drill["deployment_package"]["version"] == "module-53-v1"

    status = reliability.reliability_status()
    assert "Module 53" in status["phases"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status_response = await client.get("/api/genesis/reliability/status")
        assert status_response.status_code == 200
        assert "Module 44" in status_response.json()["phases"]

        drill_response = await client.post("/api/genesis/reliability/drill")
        assert drill_response.status_code == 200
        assert drill_response.json()["benchmark_pack"]["pack_hash"]

        mission_response = await client.post(
            "/api/genesis/reliability/missions",
            json={"goal": "API mission", "constraints": ["approval before external side effects"]},
        )
        assert mission_response.status_code == 200
        assert mission_response.json()["mission"]["mission_hash"]

        benchmark_response = await client.post(
            "/api/genesis/reliability/benchmark-packs",
            json={"name": "API benchmark", "focus": ["planning"]},
        )
        assert benchmark_response.status_code == 200
        assert benchmark_response.json()["benchmark_pack"]["version"] == "module-44-v1"

        workstyle_response = await client.post(
            "/api/genesis/reliability/workstyle",
            json={"preference": "review", "value": "short summaries"},
        )
        assert workstyle_response.status_code == 200
        assert workstyle_response.json()["workstyle_memory"]["version"] == "module-48-v1"


@pytest.mark.asyncio
async def test_world_model_and_mission_learning_loop(isolated_genesis, monkeypatch):
    from backend.genesis import approvals, autonomous_operator, capabilities, connectors, governance, intelligence, reliability, world_model

    monkeypatch.setattr(approvals, "_BASE", isolated_genesis / "approvals")
    monkeypatch.setattr(connectors, "_BASE", isolated_genesis / "connectors")
    monkeypatch.setattr(autonomous_operator, "_BASE", isolated_genesis / "operators")
    monkeypatch.setattr(governance, "_BASE", isolated_genesis / "governance")
    monkeypatch.setattr(capabilities, "_BASE", isolated_genesis / "capabilities")
    monkeypatch.setattr(intelligence, "_BASE", isolated_genesis / "intelligence")
    monkeypatch.setattr(reliability, "_BASE", isolated_genesis / "reliability")
    monkeypatch.setattr(world_model, "_BASE", isolated_genesis / "world_model")
    autonomous_operator._operator_tasks.clear()

    entity = world_model.upsert_entity(name="Genesis mission planning", entity_type="capability")
    assert entity["version"] == "world-entity-v1"
    assert entity["entity_hash"]

    evidence = world_model.attach_evidence(source="test", summary="Mission completed with evidence.")
    assert evidence["version"] == "world-evidence-v1"

    belief = world_model.record_belief(
        subject=entity["id"],
        claim="Mission planning improves with explicit constraints.",
        confidence=0.9,
        evidence_ids=[evidence["id"]],
    )
    assert belief["status"] == "supported"

    mission = reliability.mission_runner(goal="Review a mission for learning")
    lesson = world_model.review_mission(mission=mission, outcome="planned")
    assert lesson["version"] == "mission-lesson-v1"
    assert lesson["belief_id"]

    suggestion = world_model.suggest_skill(lesson=lesson, name="Mission review workflow")
    assert suggestion["version"] == "skill-suggestion-v1"
    assert suggestion["compiled_skill"]["skill_hash"]

    snapshot = world_model.build_world_snapshot()
    assert snapshot["summary"]["entities"] >= 1
    assert snapshot["summary"]["skill_suggestions"] >= 1

    drill = world_model.run_learning_drill(goal="Learn from mission outcomes")
    assert drill["version"] == "world-learning-v1"
    assert drill["snapshot"]["summary"]["lessons"] >= 1

    status = world_model.world_status()
    assert "beliefs" in status["modules"]
    assert status["latest_suggestions"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status_response = await client.get("/api/genesis/world/status")
        assert status_response.status_code == 200
        assert "entities" in status_response.json()["modules"]

        drill_response = await client.post("/api/genesis/world/drill", json={"goal": "API learning loop"})
        assert drill_response.status_code == 200
        assert drill_response.json()["skill_suggestion"]["suggestion_hash"]

        entity_response = await client.post(
            "/api/genesis/world/entities",
            json={"name": "API entity", "entity_type": "capability", "attributes": {"source": "test"}},
        )
        assert entity_response.status_code == 200
        assert entity_response.json()["entity"]["entity_hash"]

        evidence_response = await client.post(
            "/api/genesis/world/evidence",
            json={"source": "api", "summary": "API evidence captured.", "kind": "observation"},
        )
        assert evidence_response.status_code == 200
        evidence_id = evidence_response.json()["evidence"]["id"]

        belief_response = await client.post(
            "/api/genesis/world/beliefs",
            json={
                "subject": "api",
                "claim": "API beliefs can link to evidence.",
                "confidence": 0.8,
                "evidence_ids": [evidence_id],
            },
        )
        assert belief_response.status_code == 200
        assert belief_response.json()["belief"]["status"] == "supported"

        snapshot_response = await client.post("/api/genesis/world/snapshot")
        assert snapshot_response.status_code == 200
        assert snapshot_response.json()["snapshot"]["snapshot_hash"]


@pytest.mark.asyncio
async def test_dream_and_counterfactual_branch_flow(isolated_genesis):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        organism = (
            await client.post(
                "/api/genesis/seed",
                json={"name": "branchy", "goal": "Remember and compare decisions."},
            )
        ).json()["organism"]

        first = await client.post(
            f"/api/genesis/organisms/{organism['id']}/perceive",
            json={"perception": {"type": "remember_this", "payload": {}}},
        )
        assert first.status_code == 200
        decision_id = first.json()["decision"]["id"]

        dream = await client.post(
            f"/api/genesis/organisms/{organism['id']}/dream",
            json={"n": 2},
        )
        assert dream.status_code == 200
        assert dream.json()["imagined_count"] >= 1

        edit = await client.post(
            f"/api/genesis/organisms/{organism['id']}/edit/{decision_id}",
            json={
                "new_action": {"name": "noop", "args": {}},
                "new_reasoning": "Prefer a safe no-op for this counterfactual.",
            },
        )
        assert edit.status_code == 200
        branch_id = edit.json()["branch"]["id"]

        branches = await client.get(f"/api/genesis/organisms/{organism['id']}/branches")
        assert branches.status_code == 200
        assert any(b["id"] == branch_id for b in branches.json()["branches"])

        promote = await client.post(
            f"/api/genesis/organisms/{organism['id']}/branches/{branch_id}/promote"
        )
        assert promote.status_code == 200
        assert promote.json()["promoted_decisions"]


@pytest.mark.asyncio
async def test_organism_nervous_system_creates_autonomous_intentions(isolated_genesis, monkeypatch):
    from backend.genesis import body, homeostasis, living_systems, memory, metabolism, nervous_system, runtime, world_model

    monkeypatch.setattr(nervous_system, "_BASE", isolated_genesis / "nervous_system")
    monkeypatch.setattr(living_systems, "_BASE", isolated_genesis / "living_systems")
    monkeypatch.setattr(memory, "_BASE", isolated_genesis / "memories")
    monkeypatch.setattr(memory, "_MEMORY_DIR", isolated_genesis / "memories" / "items")
    monkeypatch.setattr(memory, "_CURRICULUM_PATH", isolated_genesis / "memories" / "curriculum.json")
    monkeypatch.setattr(world_model, "_BASE", isolated_genesis / "world_model")

    organism = runtime.seed(
        "Live autonomously, reduce uncertainty, and grow through experience.",
        name="nervous",
    )

    state = nervous_system.tick(organism.id, {"type": "test_tick"})
    assert state["version"] == "organism-nervous-system-v1"
    assert state["organism_id"] == organism.id
    assert state["phase"] in {"awake", "seeking", "dreaming", "resting"}
    assert state["drives"]
    assert any(need["id"] == "attach_sensor" for need in state["needs"])
    assert any(intent["need_id"] == "attach_sensor" for intent in state["intentions"])
    metabolic_state = metabolism.evaluate(state)
    assert metabolic_state["version"] == "organism-metabolism-v1"
    assert metabolic_state["policy"] in {"act", "rest", "repair", "seek_sensor", "conserve"}

    homeostatic_state = homeostasis.evaluate(state)
    assert homeostatic_state["version"] == "organism-homeostasis-v1"
    assert 0 <= homeostatic_state["stability_score"] <= 1
    assert any(item["kind"] == "sensor_silence" for item in homeostatic_state["anomalies"])

    body_map = body.build_body_map(organism.id, nervous_state=state)
    assert body_map["version"] == "organism-body-v1"
    assert body_map["summary"]["safe_actuators"] >= 3
    assert body_map["recommendations"]

    attached = body.attach_recommended_sensor(organism.id)
    assert attached["attached_sensor"]["kind"] == "interval"
    assert store.load_organism(organism.id).perception_sources

    intention_id = state["intentions"][0]["id"]
    updated = nervous_system.complete_intention(
        organism.id,
        intention_id,
        {"ok": True, "source": "test"},
    )
    assert any(
        intent["id"] == intention_id and intent["status"] == "completed"
        for intent in updated["intentions"]
    )

    fleet = nervous_system.status()
    assert fleet["summary"]["organisms"] == 1

    cycle_result = await nervous_system.run_autonomy_cycle(
        organism.id,
        stimulus={"type": "test_autonomy_cycle"},
    )
    assert cycle_result["cycle"]["version"] == "embodied-autonomy-cycle-v1"
    assert cycle_result["cycle"]["result"].get("body_version") in {None, "organism-body-v1"}
    assert cycle_result["cycle"]["status"] in {"executed", "blocked", "idle"}
    assert cycle_result["nervous_system"]["autonomy_cycles"]
    assert cycle_result["nervous_system"]["body"]["version"] == "organism-body-v1"
    assert cycle_result["nervous_system"]["metabolism"]["version"] == "organism-metabolism-v1"
    assert cycle_result["nervous_system"]["homeostasis"]["version"] == "organism-homeostasis-v1"

    recovered = metabolism.recover(cycle_result["nervous_system"])
    assert recovered["energy"] >= 0

    stressed = cycle_result["nervous_system"]
    stressed["metabolism"]["fatigue"] = 0.95
    immune_state = homeostasis.evaluate(stressed)
    assert any(item["kind"] == "fatigue_high" for item in immune_state["anomalies"])
    immune_response = homeostasis.run_immune_response(stressed, action="auto")
    assert immune_response["response"]["version"] == "immune-response-v1"
    assert immune_response["homeostasis"]["version"] == "organism-homeostasis-v1"

    living_status = living_systems.status(organism.id)
    assert living_status["version"] == "organism-living-systems-v1"
    assert living_status["lineage"]["version"] == "organism-lineage-v1"
    assert living_status["ecology"]["version"] == "organism-ecology-v1"
    assert living_status["social_contracts"]["version"] == "organism-social-contract-v1"
    assert living_status["society_culture"]["version"] == "organism-society-culture-v1"
    assert living_status["task_economy"]["version"] == "organism-task-economy-v1"
    assert living_status["world_sandbox"]["version"] == "organism-world-sandbox-v1"
    assert living_status["identity"]["version"] == "organism-identity-v1"
    assert living_status["tool_marketplace"]["version"] == "organism-tool-marketplace-v1"
    assert living_status["deployment_boundaries"]["version"] == "organism-deployment-boundaries-v1"
    assert living_status["life_engine"]["version"] == "genesis-life-engine-v1"
    assert living_status["selection"]["version"] == "organism-selection-v1"
    assert living_status["selection"]["current_score"]["version"] == "organism-selection-score-v1"
    assert living_status["life_engine"]["environment"]["version"] == "organism-environment-v1"
    assert living_status["life_engine"]["survival_pressure"]["version"] == "organism-survival-pressure-v1"
    assert living_status["life_engine"]["development"]["version"] == "organism-development-v1"
    assert living_status["life_engine"]["affect"]["version"] == "organism-affect-signals-v1"
    assert living_status["life_engine"]["layered_memory"]["version"] == "organism-layered-memory-v1"
    assert living_status["life_engine"]["organ_growth"]["version"] == "organism-organ-growth-v1"
    assert living_status["life_engine"]["mutation_strategy"]["version"] == "organism-mutation-strategy-v1"
    assert living_status["life_engine"]["mortality_legacy"]["version"] == "organism-mortality-legacy-v1"
    assert living_status["life_engine"]["persistent_self"]["version"] == "organism-persistent-self-v1"
    assert living_status["life_engine"]["temperament"]["version"] == "organism-temperament-v1"
    assert living_status["life_engine"]["goal_refinement"]["version"] == "organism-goal-refinement-status-v1"
    assert living_status["life_engine"]["society_culture"]["version"] == "organism-society-culture-v1"
    assert living_status["life_engine"]["task_economy"]["version"] == "organism-task-economy-v1"
    assert living_status["life_engine"]["world_sandbox"]["version"] == "organism-world-sandbox-v1"

    living_definition = living_systems.living_definition(organism.id)
    assert living_definition["version"] == "genesis-living-definition-v1"
    assert len(living_definition["criteria"]) == 8
    assert living_definition["assessment"]["organism_id"] == organism.id
    assert living_definition["assessment"]["total"] == 8
    assert living_definition["nervous_system_architecture"]

    development_tick = living_systems.development_tick(organism.id)
    assert development_tick["version"] == "organism-development-tick-v1"
    assert development_tick["life_engine"]["development"]["stage"] in {
        "infant",
        "juvenile",
        "apprentice",
        "adult",
        "elder",
    }

    sleep = living_systems.consolidate_sleep(organism.id)
    assert sleep["version"] == "organism-sleep-consolidation-v1"
    assert sleep["lesson"]

    selection_score = living_systems.selection_score(organism.id)
    assert selection_score["version"] == "organism-selection-score-v1"
    selection_round = living_systems.selection_round(limit=10)
    assert selection_round["version"] == "organism-selection-round-v1"
    assert selection_round["counts"]
    selection_history = living_systems.selection_history()
    assert selection_history["version"] == "organism-selection-history-v1"
    assert selection_history["rounds"]

    temperament = living_systems.temperament_profile(organism.id)
    assert temperament["version"] == "organism-temperament-v1"
    assert temperament["dominant_traits"]
    calibrated = living_systems.calibrate_temperament(organism.id)
    assert calibrated["version"] == "organism-temperament-calibration-v1"
    assert calibrated["temperament"]["decision_bias"]["style"]

    original_goal = store.load_organism(organism.id).intent.goal
    goal_refinement = living_systems.goal_refinement_status(organism.id)
    assert goal_refinement["version"] == "organism-goal-refinement-status-v1"
    assert goal_refinement["review_gate"]["requires_human_approval"] is True
    proposed_goal = living_systems.propose_goal_refinement(organism.id)
    assert proposed_goal["version"] == "organism-goal-refinement-proposal-v1"
    assert proposed_goal["proposal"]["requires_human_approval"] is True
    assert proposed_goal["proposal"]["ready_for_review"] is True
    assert store.load_organism(organism.id).intent.goal == original_goal

    society_culture = living_systems.society_roles_and_culture(organism.id)
    assert society_culture["version"] == "organism-society-culture-v1"
    assert society_culture["role"]["role"]
    assert society_culture["culture"]["norms"]
    culture_pulse = living_systems.run_culture_pulse(organism.id)
    assert culture_pulse["version"] == "organism-culture-pulse-v1"
    assert culture_pulse["pulse"]["role"]["role"] == culture_pulse["society_culture"]["role"]["role"]

    task_economy = living_systems.task_economy_and_resource_budget(organism.id)
    assert task_economy["version"] == "organism-task-economy-v1"
    assert task_economy["budgets"]["reserve"] >= 0
    assert task_economy["tasks"]
    budget_pulse = living_systems.run_budget_pulse(organism.id)
    assert budget_pulse["version"] == "organism-budget-pulse-v1"
    assert budget_pulse["pulse"]["budgets"]["reserve"] >= 0

    world_sandbox = living_systems.world_sandbox_with_hazards(organism.id)
    assert world_sandbox["version"] == "organism-world-sandbox-v1"
    assert world_sandbox["world_state"]["external_side_effects"] is False
    assert world_sandbox["hazards"]
    sandbox_pulse = living_systems.run_world_sandbox_pulse(organism.id)
    assert sandbox_pulse["version"] == "organism-world-sandbox-pulse-v1"
    assert sandbox_pulse["pulse"]["hazards"]

    refreshed = store.load_organism(organism.id)
    refreshed.learned_patterns.extend([f"stable inherited pattern {i}" for i in range(5)])
    store.save_organism(refreshed)
    reproduction = living_systems.reproduce(organism.id)
    assert reproduction["event"]["parent_id"] == organism.id
    assert reproduction["child"]["parent_organism_id"] == organism.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status_response = await client.get(f"/api/genesis/organisms/{organism.id}/nervous-system")
        assert status_response.status_code == 200
        assert status_response.json()["nervous_system"]["organism_id"] == organism.id

        tick_response = await client.post(
            f"/api/genesis/organisms/{organism.id}/nervous-system/tick",
            json={"stimulus": {"type": "api_tick"}},
        )
        assert tick_response.status_code == 200
        assert tick_response.json()["nervous_system"]["intentions"]

        fleet_response = await client.get("/api/genesis/nervous-system/status")
        assert fleet_response.status_code == 200
        assert fleet_response.json()["version"] == "organism-nervous-system-v1"

        body_response = await client.get(f"/api/genesis/organisms/{organism.id}/body")
        assert body_response.status_code == 200
        assert body_response.json()["body"]["version"] == "organism-body-v1"

        body_fleet_response = await client.get("/api/genesis/body/status")
        assert body_fleet_response.status_code == 200
        assert body_fleet_response.json()["version"] == "organism-body-v1"

        metabolism_response = await client.get(f"/api/genesis/organisms/{organism.id}/metabolism")
        assert metabolism_response.status_code == 200
        assert metabolism_response.json()["metabolism"]["version"] == "organism-metabolism-v1"

        recovery_response = await client.post(
            f"/api/genesis/organisms/{organism.id}/metabolism/recover",
            json={"depth": "rest"},
        )
        assert recovery_response.status_code == 200
        assert recovery_response.json()["metabolism"]["survival_status"] in {
            "stable",
            "tired",
            "hungry",
            "depleted",
            "fragile",
        }

        homeostasis_response = await client.get(f"/api/genesis/organisms/{organism.id}/homeostasis")
        assert homeostasis_response.status_code == 200
        assert homeostasis_response.json()["homeostasis"]["version"] == "organism-homeostasis-v1"

        immune_response = await client.post(
            f"/api/genesis/organisms/{organism.id}/homeostasis/immune-response",
            json={"action": "auto"},
        )
        assert immune_response.status_code == 200
        assert immune_response.json()["response"]["version"] == "immune-response-v1"

        living_response = await client.get(f"/api/genesis/organisms/{organism.id}/living-systems")
        assert living_response.status_code == 200
        assert living_response.json()["version"] == "organism-living-systems-v1"
        assert living_response.json()["life_engine"]["version"] == "genesis-life-engine-v1"

        living_definition_response = await client.get("/api/genesis/living-definition")
        assert living_definition_response.status_code == 200
        assert living_definition_response.json()["version"] == "genesis-living-definition-v1"

        organism_living_definition_response = await client.get(
            f"/api/genesis/organisms/{organism.id}/living-definition"
        )
        assert organism_living_definition_response.status_code == 200
        assert organism_living_definition_response.json()["assessment"]["organism_id"] == organism.id

        life_engine_response = await client.get(f"/api/genesis/organisms/{organism.id}/life-engine")
        assert life_engine_response.status_code == 200
        assert life_engine_response.json()["version"] == "genesis-life-engine-v1"

        organism_selection_response = await client.get(f"/api/genesis/organisms/{organism.id}/selection")
        assert organism_selection_response.status_code == 200
        assert organism_selection_response.json()["version"] == "organism-selection-v1"

        temperament_response = await client.get(f"/api/genesis/organisms/{organism.id}/temperament")
        assert temperament_response.status_code == 200
        assert temperament_response.json()["version"] == "organism-temperament-v1"

        temperament_calibration_response = await client.post(
            f"/api/genesis/organisms/{organism.id}/temperament/calibrate"
        )
        assert temperament_calibration_response.status_code == 200
        assert temperament_calibration_response.json()["version"] == "organism-temperament-calibration-v1"

        goal_refinement_response = await client.get(f"/api/genesis/organisms/{organism.id}/goal-refinement")
        assert goal_refinement_response.status_code == 200
        assert goal_refinement_response.json()["version"] == "organism-goal-refinement-status-v1"

        goal_refinement_proposal_response = await client.post(
            f"/api/genesis/organisms/{organism.id}/goal-refinement/propose",
            json={"focus": "auto"},
        )
        assert goal_refinement_proposal_response.status_code == 200
        assert goal_refinement_proposal_response.json()["version"] == "organism-goal-refinement-proposal-v1"
        assert goal_refinement_proposal_response.json()["proposal"]["applied"] is False

        society_culture_response = await client.get(f"/api/genesis/organisms/{organism.id}/society-culture")
        assert society_culture_response.status_code == 200
        assert society_culture_response.json()["version"] == "organism-society-culture-v1"

        culture_pulse_response = await client.post(
            f"/api/genesis/organisms/{organism.id}/society-culture/pulse",
            json={"focus": "norms"},
        )
        assert culture_pulse_response.status_code == 200
        assert culture_pulse_response.json()["version"] == "organism-culture-pulse-v1"

        task_economy_response = await client.get(f"/api/genesis/organisms/{organism.id}/task-economy")
        assert task_economy_response.status_code == 200
        assert task_economy_response.json()["version"] == "organism-task-economy-v1"

        budget_pulse_response = await client.post(
            f"/api/genesis/organisms/{organism.id}/task-economy/pulse",
            json={"focus": "balanced"},
        )
        assert budget_pulse_response.status_code == 200
        assert budget_pulse_response.json()["version"] == "organism-budget-pulse-v1"

        world_sandbox_response = await client.get(f"/api/genesis/organisms/{organism.id}/world-sandbox")
        assert world_sandbox_response.status_code == 200
        assert world_sandbox_response.json()["version"] == "organism-world-sandbox-v1"

        world_sandbox_pulse_response = await client.post(
            f"/api/genesis/organisms/{organism.id}/world-sandbox/pulse",
            json={"scenario": "current_tasks"},
        )
        assert world_sandbox_pulse_response.status_code == 200
        assert world_sandbox_pulse_response.json()["version"] == "organism-world-sandbox-pulse-v1"

        selection_history_response = await client.get("/api/genesis/selection/history")
        assert selection_history_response.status_code == 200
        assert selection_history_response.json()["version"] == "organism-selection-history-v1"

        selection_round_response = await client.post(
            "/api/genesis/selection/round",
            json={"pressure": "balanced", "limit": 10},
        )
        assert selection_round_response.status_code == 200
        assert selection_round_response.json()["version"] == "organism-selection-round-v1"

        development_response = await client.post(f"/api/genesis/organisms/{organism.id}/development/tick")
        assert development_response.status_code == 200
        assert development_response.json()["version"] == "organism-development-tick-v1"

        ecology_response = await client.get("/api/genesis/ecology")
        assert ecology_response.status_code == 200
        assert ecology_response.json()["version"] == "organism-ecology-v1"

        sleep_response = await client.post(f"/api/genesis/organisms/{organism.id}/sleep/consolidate")
        assert sleep_response.status_code == 200
        assert sleep_response.json()["version"] == "organism-sleep-consolidation-v1"

        lineage_response = await client.get(f"/api/genesis/organisms/{organism.id}/lineage")
        assert lineage_response.status_code == 200
        assert lineage_response.json()["lineage"]["version"] == "organism-lineage-v1"

        identity_response = await client.get(f"/api/genesis/organisms/{organism.id}/identity")
        assert identity_response.status_code == 200
        assert identity_response.json()["identity"]["version"] == "organism-identity-v1"

        marketplace_response = await client.get(f"/api/genesis/organisms/{organism.id}/tool-marketplace")
        assert marketplace_response.status_code == 200
        assert marketplace_response.json()["tool_marketplace"]["version"] == "organism-tool-marketplace-v1"

        boundaries_response = await client.get(f"/api/genesis/organisms/{organism.id}/deployment-boundaries")
        assert boundaries_response.status_code == 200
        assert boundaries_response.json()["deployment_boundaries"]["version"] == "organism-deployment-boundaries-v1"

        legacy_response = await client.get(f"/api/genesis/organisms/{organism.id}/mortality-legacy")
        assert legacy_response.status_code == 200
        assert legacy_response.json()["mortality_legacy"]["version"] == "organism-mortality-legacy-v1"

        cycle_response = await client.post(
            f"/api/genesis/organisms/{organism.id}/autonomy/cycle",
            json={"stimulus": {"type": "api_cycle"}},
        )
        assert cycle_response.status_code == 200
        assert cycle_response.json()["cycle"]["version"] == "embodied-autonomy-cycle-v1"


@pytest.mark.asyncio
async def test_kill_distills_skill_after_enough_decisions(isolated_genesis):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        organism = (
            await client.post(
                "/api/genesis/seed",
                json={"name": "distillable", "goal": "Remember repeated test signals."},
            )
        ).json()["organism"]

        for i in range(5):
            response = await client.post(
                f"/api/genesis/organisms/{organism['id']}/perceive",
                json={"perception": {"type": "remember_signal", "index": i}},
            )
            assert response.status_code == 200

        killed = await client.delete(f"/api/genesis/organisms/{organism['id']}")
        assert killed.status_code == 200
        skill_id = killed.json()["distilled_skill_id"]
        assert skill_id

        skills = await client.get("/api/genesis/skills")
        assert skills.status_code == 200
        assert any(s["skill_id"] == skill_id for s in skills.json()["skills"])


def test_corrupt_organism_file_is_ignored(isolated_genesis):
    from backend.genesis import runtime

    healthy = runtime.seed("Stay readable.", name="healthy")
    bad_dir = store._BASE / "o_corrupt"
    bad_dir.mkdir(parents=True)
    (bad_dir / "organism.json").write_text("{not json", encoding="utf-8")

    organisms = store.list_organisms()
    assert [o.id for o in organisms] == [healthy.id]


def test_corrupt_nervous_system_state_is_regenerated(isolated_genesis, monkeypatch):
    from backend.genesis import nervous_system, runtime

    monkeypatch.setattr(nervous_system, "_BASE", isolated_genesis / "nervous_system")
    organism = runtime.seed("Stay internally recoverable.", name="nervous")
    nervous_system._BASE.mkdir(parents=True)
    (nervous_system._BASE / f"{organism.id}.json").write_text('{"broken": true}\n{"extra": true}', encoding="utf-8")

    state = nervous_system.ensure_state(organism.id)
    assert state["organism_id"] == organism.id
    assert state["version"] == "organism-nervous-system-v1"


def test_production_config_rejects_unsafe_defaults(monkeypatch):
    previous = {
        "GENESIS_ENV": settings.GENESIS_ENV,
        "GENESIS_LLM_PROVIDER": settings.GENESIS_LLM_PROVIDER,
        "GENESIS_REQUIRE_API_TOKEN": settings.GENESIS_REQUIRE_API_TOKEN,
        "GENESIS_API_TOKEN": settings.GENESIS_API_TOKEN,
        "GENESIS_CORS_ORIGINS": settings.GENESIS_CORS_ORIGINS,
        "GENESIS_TRUSTED_HOSTS": settings.GENESIS_TRUSTED_HOSTS,
    }
    monkeypatch.setattr(settings, "GENESIS_ENV", "production")
    monkeypatch.setattr(settings, "GENESIS_LLM_PROVIDER", "mock")
    monkeypatch.setattr(settings, "GENESIS_REQUIRE_API_TOKEN", False)
    monkeypatch.setattr(settings, "GENESIS_API_TOKEN", "")
    monkeypatch.setattr(settings, "GENESIS_CORS_ORIGINS", ["*"])
    monkeypatch.setattr(settings, "GENESIS_TRUSTED_HOSTS", ["*"])

    with pytest.raises(RuntimeError) as exc:
        settings.validate_startup()

    message = str(exc.value)
    assert "mock is not allowed" in message
    assert "GENESIS_REQUIRE_API_TOKEN=1" in message

    for key, value in previous.items():
        monkeypatch.setattr(settings, key, value)


@pytest.mark.asyncio
async def test_lifecycle_reconcile_skips_dead_organisms(isolated_genesis):
    from backend.genesis import lifecycle, runtime
    from backend.genesis.types import OrganismState

    lifecycle._heartbeats.clear()
    lifecycle._webhook_index.clear()

    alive = runtime.seed("Stay alive.", name="alive")
    dead = runtime.seed("Do not revive.", name="dead")
    dead.state = OrganismState.DEAD
    store.save_organism(dead)

    await lifecycle._reconcile()
    try:
        assert alive.id in lifecycle._heartbeats
        assert dead.id not in lifecycle._heartbeats
    finally:
        for task in list(lifecycle._heartbeats.values()):
            task.cancel()
        lifecycle._heartbeats.clear()
