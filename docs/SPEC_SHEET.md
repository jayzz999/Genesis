# Genesis Spec Sheet

## Product Summary

Genesis is a governed autonomous-operations platform for creating persistent AI
organisms. Each organism has an identity, goal, lifecycle state, causal memory,
learned skills, inherited behavior, simulated futures, and permission-gated
connectors for real-world work.

## Intended User

| User | Need |
|------|------|
| Maintainer | Delegate repository triage, issue review, and routine operational checks without losing control over side effects. |
| Operator | Inspect autonomous work, approve risky actions, revoke grants, and audit the exact reason an action happened. |
| Researcher | Run repeatable population experiments and compare adaptation across benchmark tasks. |
| Developer | Extend organisms with connectors, MCP tools, lifecycle sources, and product panels. |

## Core Promise

Genesis should make autonomous agents observable, governable, measurable, and
capable of improving from real feedback. A production proof must use real
connector state, real credentials, explicit allowlists, approval grants, and an
auditable connector ledger.

## System Capabilities

| Area | Capability | Current Contract |
|------|------------|------------------|
| Organisms | Seed, list, inspect, kill, perceive, dream, reproduce | Persistent JSON-backed organism bodies with API access. |
| Memory | Causal decisions, long-term memories, branch history | Every decision records trigger, reasoning, action, result, and alternatives. |
| Simulation | Dreams and counterfactual branches | Simulated changes are isolated until explicitly promoted. |
| Learning | Skill distillation, lineage, inheritance, compiled context | Skills can be listed, inspected, inherited, compiled, and deleted. |
| Autonomy | Lifecycle heartbeat, perception sources, operator loops | Background activity can be disabled with `GENESIS_LIFECYCLE=0`. |
| Safety | API token protection, approvals, scoped grants, revocation | Mutating routes and WebSockets can require `GENESIS_API_TOKEN`. |
| Connectors | GitHub, HTTP, Slack/webhook, deploy, browser, artifact writes | Real side effects require allowlists plus scoped permission grants. |
| Observability | Status, connector runs, approval integrity, governance evidence | UI and APIs expose runtime, config, and audit state without leaking secrets. |
| Evaluation | Population runs, benchmark reports, regression deltas | Benchmark identity is stored and compared against historical completed runs. |

## Product Surface

| Surface | Purpose |
|---------|---------|
| Genesis UI | Main operator console for organisms, approvals, connectors, dreams, skills, governance, and experiments. |
| REST API | Programmatic control plane under `/api/genesis/*`. |
| WebSocket | Live organism events at `/ws/{client_id}`. |
| Render Blueprint | Single-container deployment with generated API token and secret slots. |
| Docker Compose | Local production-like deployment with named-volume persistence. |
| Maintenance Scripts | Preflight checks, local snapshots, resets, and repo-maintainer organism setup. |

## Architecture At A Glance

| Layer | Implementation |
|-------|----------------|
| Backend | FastAPI app in `backend/main.py` with Genesis router in `backend/genesis/api.py`. |
| Runtime | Organism loop, lifecycle supervisor, autonomous operator, perception pipeline, and causal store under `backend/genesis/`. |
| Frontend | React + Vite app in `frontend/` with Genesis panels under `frontend/src/components/genesis/`. |
| Persistence | JSON runtime stores plus SQLite locally; Postgres/Supabase can hold auth, sessions, audit events, and query mirrors. |
| Deployment | Docker image builds frontend and serves static UI from FastAPI. |

## Runtime Defaults

| Setting | Default | Notes |
|---------|---------|-------|
| API port | `8002` | Set with `PORT`. |
| Frontend dev port | Vite default, commonly `5173` or next open port | README examples use local API `http://127.0.0.1:8002`. |
| LLM provider | `gemini` | Use `GENESIS_LLM_PROVIDER=mock` for no-key local demos and tests. |
| Lifecycle | `GENESIS_LIFECYCLE=1` | Set to `0` for focused local development or controlled hosted demos. |
| Dreaming | `GENESIS_DREAMING=1` | Set to `0` to avoid idle LLM usage. |
| Auth protection | `GENESIS_REQUIRE_API_TOKEN=0` in development | Required in production. |
| Database | `sqlite+aiosqlite:///./genesis.db` | Use Postgres/Supabase for hosted production control-plane durability. |

## Required Production Settings

| Variable | Requirement |
|----------|-------------|
| `GENESIS_ENV` | `production` |
| `GENESIS_LLM_PROVIDER` | `gemini` or `groq`; `mock` is refused in production. |
| `GEMINI_API_KEY` or `GROQ_API_KEY` | Required for the selected provider. |
| `GENESIS_REQUIRE_API_TOKEN` | `1` |
| `GENESIS_API_TOKEN` | At least 24 characters. |
| `GENESIS_CORS_ORIGINS` | Exact deployed origin; no wildcard in production. |
| `GENESIS_TRUSTED_HOSTS` | Exact deployed host; no wildcard in production. |
| `DATABASE_URL` | Postgres/Supabase recommended for hosted deployments. |

## Connector Safety Contract

| Adapter | External Effect | Required Controls |
|---------|-----------------|-------------------|
| `external_api` | HTTP request to an allowlisted endpoint | Scoped grant plus `GENESIS_CONNECTOR_HTTP_ALLOWLIST`. |
| `send_message` | JSON post to a generic webhook | Scoped grant plus `GENESIS_CONNECTOR_WEBHOOK_ALLOWLIST`. |
| `slack_webhook_message` | Slack incoming-webhook message | Scoped grant plus Slack webhook allowlist. |
| `github_create_issue` | Create GitHub issue | Scoped grant, token, and `GENESIS_GITHUB_REPOSITORIES`. |
| `github_issue_comment` | Post GitHub issue comment | Scoped grant, token, and `GENESIS_GITHUB_REPOSITORIES`. |
| `deploy_change` | POST to deployment executor | Scoped grant plus `GENESIS_CONNECTOR_DEPLOY_ALLOWLIST`. |
| `browser_submit` | POST to browser executor | Explicit enable flag, scoped grant, and browser allowlist. |
| `local_artifact_write` / `file_upload` | Write controlled local artifact | Scoped grant and controlled artifact destination. |

## Canonical Demo Spec

| Item | Requirement |
|------|-------------|
| Demo organism | Repo maintainer organism for an allowlisted GitHub repository. |
| Read path | Live read-only GitHub probe before organism creation. |
| Work loop | Notice repository state, prioritize issues/PRs, dream alternatives, remember maintainer preferences, and propose approved actions. |
| Write path | GitHub comments or issues only after approval and scoped grant. |
| Evidence | Connector ledger shows `simulated: false` and terminal status `complete`, `blocked`, or `failed`. |
| Fallback | Missing credentials or allowlists fail closed without creating fake activity. |

## Key API Groups

| Group | Representative Endpoints |
|-------|--------------------------|
| Health and status | `GET /api/health`, `GET /api/genesis/status`, `GET /api/genesis/lifecycle/status` |
| Organisms | `POST /api/genesis/seed`, `GET /api/genesis/organisms`, `POST /api/genesis/organisms/{id}/perceive` |
| Memory and simulation | `GET /api/genesis/organisms/{id}/causality`, `POST /api/genesis/organisms/{id}/dream`, `POST /api/genesis/organisms/{id}/branches/{branch_id}/promote` |
| Skills | `GET /api/genesis/skills`, `GET /api/genesis/skills/{skill_id}/lineage`, `POST /api/genesis/skills/{skill_id}/compile` |
| Connectors | `GET /api/genesis/connectors/configuration`, `POST /api/genesis/connectors/probe`, `POST /api/genesis/connectors/run` |
| Approvals | `GET /api/genesis/approvals`, `POST /api/genesis/approvals/{id}/approve`, `POST /api/genesis/approvals/{id}/execute` |
| Governance | `GET /api/genesis/governance/status`, `GET /api/genesis/governance/production-readiness`, `GET /api/genesis/governance/accountability` |
| Evaluation | `POST /api/genesis/population/start`, `GET /api/genesis/population/{run_id}/report`, `GET /api/genesis/benchmarks` |

## Local Verification

```bash
GENESIS_LLM_PROVIDER=mock GENESIS_LIFECYCLE=0 PORT=8002 python -m backend.main
```

```bash
pytest -q
cd frontend && npm run build
```

## Release Readiness Checklist

| Check | Pass Criteria |
|-------|---------------|
| Startup preflight | `python scripts/production_preflight.py --create-dirs` passes with production env. |
| Tests | `pytest -q` passes. |
| Frontend build | `cd frontend && npm run build` succeeds. |
| Auth | Mutating API calls and WebSockets reject missing/invalid token when protection is enabled. |
| Connectors | Probes reflect real server-side configuration without exposing secrets. |
| Approvals | Approval, grant, execution, and revocation flows are visible in the UI and API. |
| Ledger | Real connector runs write durable status records and do not simulate success. |
| Deployment | `/api/health` returns `{"status":"ok","service":"Genesis"}` on the target host. |
