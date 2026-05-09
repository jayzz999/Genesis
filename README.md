# Genesis — Living Digital Organisms

> An open-source framework for creating autonomous AI agents modelled as living organisms: they perceive events, reason about what to do, act through real tools (MCP), build a causal memory of every decision, dream up hypothetical futures, and distill what they learn into inheritable skills.

---

## What Makes Genesis Different

### 30-second explanation

Genesis is a product platform for operating autonomous digital workers. Each
organism has a persistent identity, objective, causal memory, learned skills,
descendants, and permission-gated integrations that can touch real systems. The
product goal is to make autonomous work observable, governable, measurable, and
capable of improving under real-world feedback.

Most agent frameworks give you a graph of function calls. Genesis gives you a **living entity**:

| Concept | What It Means |
|---------|--------------|
| **Organism** | An AI agent with a persistent intent (goal), a state machine, and full causal memory |
| **Intent** | Natural-language goal + constraints. Immutable once set — re-interpreted fresh against every new perception |
| **Decision** | The atom of memory. Every act of reasoning is recorded: what triggered it, what the LLM reasoned, what action was taken, what alternatives it considered |
| **Causal Graph** | Decisions form a directed graph. You can inspect exactly why any action was taken |
| **Counterfactual editing** | Edit a past decision and replay everything downstream to see what would have happened differently |
| **Dream** | The organism imagines hypothetical futures by replaying decisions in simulation — learning without real consequences |
| **Skill** | A pattern distilled from experience (real + dreamt). Versioned, with lineage. New organisms inherit skills from successful ancestors |
| **MCP Servers** | Each organism connects to Model Context Protocol servers as its tools — file systems, APIs, databases, anything |

### Why not just LangGraph, CrewAI, or AutoGen?

Those frameworks are useful for orchestrating agents and tool calls. Genesis is
trying to solve a different product problem: how to make autonomous agents
persist, remember, simulate, inherit, reproduce, and improve under measurable
pressure while real-world actions remain permission-gated. The core object is
not a workflow graph or a chat crew; it is an organism with a life history.

---

## Definition Of Living

A Genesis organism is considered "living" only when there is evidence for these
criteria:

| Criterion | Evidence |
|-----------|----------|
| Persistent identity | durable organism id, intent, state, and birth record |
| Memory across time | decisions, messages, lessons, or learned patterns persist across events |
| Autonomous perception/action loop | perceptions trigger reasoning and actions without rewriting the goal |
| Causal self-history | every decision stores trigger, reasoning, action, result, and alternatives |
| Future simulation | dreams and counterfactual branches can be explored without real side effects |
| Reusable learning | skills or learned patterns influence future behavior |
| Reproduction/inheritance | descendants can inherit skills, strategies, and safety constraints |
| Measurable adaptation | benchmark fitness, regression deltas, or environmental pressure can be tracked |

The backend exposes this contract:

```bash
curl http://localhost:8002/api/genesis/living-definition
curl http://localhost:8002/api/genesis/organisms/<organism_id>/living-definition
```

---

## Nervous System Architecture

| Biological frame | Genesis subsystem |
|------------------|-------------------|
| Senses | events, webhooks, HTTP polling, APIs, files, repository signals |
| Brain | reasoning, planning, metacognition, collaboration, debate |
| Memory | causal graph, long-term database, messages, learned patterns |
| Dreams | simulations, counterfactual branches, skill rehearsal |
| Hands | MCP tools and permission-gated real connectors |
| Immune system | approvals, scoped grants, allowlists, reliability gates, homeostasis |
| Reproduction | skill inheritance, lineage, population evolution, descendants |

---

## Organism Lifecycle

```
SEEDED ──> PERCEIVING ──> ACTING ──> PERCEIVING (loop)
                                 └──> DREAMING ──> PERCEIVING
                                 └──> DYING ──> DEAD (skills donated to pool)
```

---

## Current Product Surface

Genesis is now an operations product surface. The app includes:

- persistent organisms with causal memory, dreams, counterfactual branches, and skill inheritance
- population evolution with repeatable benchmark reports
- long-term database/auth substrate and production API-token enforcement
- human approval requests, scoped permission grants, and revocation
- real connector adapters that fail closed when credentials are missing
- a connector control center with safe preflight probes before approved execution
- autonomous operator loops, multi-agent collaboration, reliability gates, world models, and living-system panels

Genesis is built as a product for governed autonomous operations: memory, tool
use, approvals, integrations, reliability, and measurable outcomes in one place.

## Production Core

Genesis treats these subsystems as production-critical:

- organism runtime, perception pipeline, causal memory, dreams, branches, and skill inheritance
- auth, sessions, startup configuration checks, and the long-term control plane
- human approvals, scoped permission grants, policy review, and integrity records
- permission-gated connectors and MCP server management
- lifecycle supervision, webhook delivery, and durable autonomous operators
- operational UI for inspection, approval, connector management, and runtime health
- smoke, security, and deployment verification

Everything else is currently experimental product/research surface: living-system
simulation, capability growth, self-improvement, collaboration/debate, world
modeling, reliability missions, and population evolution. These modules can be
useful, but they should not be treated as required production safety boundaries
until their evidence base is stronger.

Runtime HTTP tools and MCP server forging are governed by the same approval
model as real connectors. `http_request` and `fetch_web_page` require both a
scoped `external_api` grant and a URL allowed by
`GENESIS_CONNECTOR_HTTP_ALLOWLIST`. `forge_mcp_server` requires a scoped
`deploy_change` grant and creates an approval request when no grant is supplied.

---

## Canonical Real Demo: Repo Maintainer Organism

The first proof organism should be concrete: a maintainer assistant for a real
GitHub repository.

It should:

- watch an allowlisted GitHub repo
- notice issues and pull requests through real connector/API state
- prioritize work using impact, maintainer burden, implementation risk, and evidence
- propose comments, issues, or fixes through the approval queue
- dream alternative solutions before risky changes
- remember maintainer preferences across sessions
- improve triage quality across benchmark runs

Create it only after real GitHub credentials are configured:

```bash
export GITHUB_TOKEN=github_pat_...
export GENESIS_GITHUB_REPOSITORIES=owner/repo

python scripts/create_repo_maintainer_organism.py owner/repo
```

The script performs a live read-only GitHub probe first. If credentials or
allowlists are missing, it exits without creating the organism.

Product proof rule: development mode is allowed for local engineering and tests,
but production proof must use configured integrations, real repository state,
approval grants, and an honest connector ledger.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/your-org/Genesis.git
cd Genesis

# 2. Install backend dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# For local development without provider keys, set GENESIS_LLM_PROVIDER=mock.
# For real reasoning, set GEMINI_API_KEY or GROQ_API_KEY.

# 4. Start the backend API on port 8002
PORT=8002 python -m backend.main

# 5. In a new terminal, start the frontend
cd frontend && npm install && npm run dev
```

Open **http://127.0.0.1:5174/** and seed your first organism.

---

### Local Development Mode

You can run Genesis without Gemini or Groq keys by using the deterministic
development provider. This keeps the full organism loop working locally: seed,
perceive, dream, edit branches, promote counterfactuals, and distill skills.

```bash
GENESIS_LLM_PROVIDER=mock GENESIS_LIFECYCLE=0 PORT=8002 python -m backend.main

# in another terminal
cd frontend
npm install
npm run dev
```

Use lifecycle off for focused development and tests. Turn it back on when you want
background polling, webhook reconciliation, message checks, and idle dreaming.

The frontend expects the API at `http://127.0.0.1:8002` in development.

### Verification

```bash
pytest -q
cd frontend && npm run build
```

---

## Production Deployment

Genesis can ship as a single container: the Docker build compiles the React
frontend and serves it from FastAPI alongside the API and WebSocket server.

### Required production environment

Set these before deployment:

```bash
GENESIS_ENV=production
GENESIS_LLM_PROVIDER=gemini
GEMINI_API_KEY=...
GENESIS_REQUIRE_API_TOKEN=1
GENESIS_API_TOKEN=<long random secret, at least 24 chars>
GENESIS_CORS_ORIGINS=https://your-genesis-host.example
GENESIS_TRUSTED_HOSTS=your-genesis-host.example
DATABASE_URL=sqlite+aiosqlite:////app/data/genesis.db
```

For a trusted browser session that is allowed to mutate the backend, store the
token locally in that browser:

```js
localStorage.setItem("GENESIS_API_TOKEN", "<same long random secret>")
```

Do not bake production API tokens into public frontend builds.

Production startup refuses unsafe settings such as development LLM mode, wildcard CORS,
wildcard trusted hosts, or missing API token protection.

### Docker

```bash
cp .env.example .env
# Edit .env: set GENESIS_ENV=production, a real LLM key, exact host/origin,
# GENESIS_REQUIRE_API_TOKEN=1, and a long GENESIS_API_TOKEN.
python scripts/production_preflight.py --create-dirs
docker compose up --build
```

The container exposes `PORT` (default `8002`), runs as a non-root user, serves
the compiled React app from FastAPI, and persists all runtime state under one
named volume mounted at `/app/data`:

- SQLite auth/control database: `/app/data/genesis.db`
- organisms, decisions, approvals, permissions, operators, memories, world model,
  reliability packages, living systems, and nervous-system state

Health check:

```bash
curl https://your-genesis-host.example/api/health
```

Full production preflight:

```bash
GENESIS_ENV=production \
GENESIS_LLM_PROVIDER=gemini \
GEMINI_API_KEY=... \
GENESIS_REQUIRE_API_TOKEN=1 \
GENESIS_API_TOKEN=<long random secret> \
GENESIS_CORS_ORIGINS=https://your-genesis-host.example \
GENESIS_TRUSTED_HOSTS=your-genesis-host.example \
python scripts/production_preflight.py --create-dirs
```

### Hosted Blueprint

`render.yaml` is included as a production deployment blueprint. It provisions a
single Docker web service with a persistent disk at `/app/data`, health checks,
generated API token, and secret slots for the LLM key and exact public host.
On Render, Genesis can derive safe same-origin CORS/trusted-host defaults from
Render service metadata. After creating the service, set:

- `GEMINI_API_KEY` or switch provider-specific keys as needed
- connector credentials and allowlists for the systems you want Genesis to touch
- `GENESIS_CORS_ORIGINS` / `GENESIS_TRUSTED_HOSTS` only when using a custom domain

See [docs/RENDER_DEPLOYMENT.md](docs/RENDER_DEPLOYMENT.md) for the exact Render
Dashboard steps and production environment checklist.

### Operations

Inspect local data volume contents:

```bash
python scripts/genesis_maintenance.py status
```

Create a timestamped backup:

```bash
python scripts/genesis_maintenance.py snapshot --out backups
```

Reset local data after taking a snapshot:

```bash
python scripts/genesis_maintenance.py reset --confirm RESET
```

For public deployments, keep the frontend read-only unless the audience is
trusted. Mutating API routes and WebSockets require `X-Genesis-Token` when
`GENESIS_REQUIRE_API_TOKEN=1`.

### Real Connectors

Connectors are permission-gated real side effects. They do not return artificial
success when a provider is missing. Approved but unconfigured connector runs fail
closed and are still written to the connector ledger.

The intended operating loop is:

1. configure credentials and allowlists server-side
2. run a connector probe from the UI or API
3. review the exact action and mint a scoped permission grant
4. run the connector
5. inspect the connector ledger for `complete`, `blocked`, or `failed`

Configure only the systems you actually want Genesis to touch:

```bash
# HTTP API connector: comma-separated hostnames or URL prefixes.
GENESIS_CONNECTOR_HTTP_ALLOWLIST=api.github.com,https://hooks.slack.com/services/

# GitHub connector: create issues or comments only in allowlisted repos.
GITHUB_TOKEN=github_pat_...
GENESIS_GITHUB_REPOSITORIES=owner/repo,another-owner/another-repo

# Message connector: posts JSON `{ text, scope, metadata }` to this webhook.
GENESIS_MESSAGE_WEBHOOK_URL=https://...
GENESIS_CONNECTOR_WEBHOOK_ALLOWLIST=your-webhook-host.example

# Slack-specific connector uses Slack incoming webhooks.
GENESIS_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Deployment connector: posts approved deploy metadata to this webhook.
GENESIS_DEPLOY_WEBHOOK_URL=https://...
GENESIS_CONNECTOR_DEPLOY_ALLOWLIST=your-deploy-hook-host.example

# Browser connector: disabled unless you provide an executor webhook.
GENESIS_BROWSER_CONNECTOR_ENABLED=1
GENESIS_BROWSER_CONNECTOR_WEBHOOK_URL=https://...
GENESIS_CONNECTOR_BROWSER_ALLOWLIST=your-browser-executor.example
```

Available integration adapters:

| Adapter | Side effect | Safety model |
|---------|-------------|--------------|
| `external_api` | HTTP request to an allowlisted endpoint | grant + URL allowlist |
| `send_message` | JSON message to configured webhook | grant + webhook allowlist |
| `slack_webhook_message` | Slack incoming-webhook message | grant + Slack webhook allowlist |
| `github_create_issue` | create GitHub issue | grant + repo allowlist + token |
| `github_issue_comment` | post GitHub issue comment | grant + repo allowlist + token |
| `deploy_change` | deployment webhook call | grant + deploy allowlist |
| `browser_submit` | browser executor webhook call | grant + executor allowlist + explicit enable flag |
| `local_artifact_write` | write local artifact | grant + controlled artifact path |
| `file_upload` | write local artifact | grant + controlled artifact path |

`local_artifact_write` and `file_upload` are real local writes into the
controlled connector artifact store. External HTTP, message, deployment, and
browser connectors require explicit allowlists plus human approval grants.

Before granting a connector, use the safe probe endpoint to confirm server-side
configuration and allowlists without exposing secrets:

```bash
curl -X POST http://localhost:8002/api/genesis/connectors/probe \
  -H 'Content-Type: application/json' \
  -d '{"adapter_id":"github_create_issue","scope":"owner/repo","live":true}'
```

GitHub live probes are read-only repository checks. Slack/webhook probes report
configuration and allowlist readiness; posting a test message still goes through
the normal approval-gated connector run.

Connector status endpoints:

```bash
curl http://localhost:8002/api/genesis/connectors/configuration
curl http://localhost:8002/api/genesis/connectors/adapters
curl http://localhost:8002/api/genesis/connectors/runs
```

---

## LLM Providers

Genesis supports three providers out of the box:

| Provider | Env var | Notes |
|----------|---------|-------|
| Google Gemini (default) | `GEMINI_API_KEY` | Best quality, used in production |
| Groq (free tier) | `GROQ_API_KEY` | Great for local dev — fast, free |
| Development | none | Deterministic no-key mode for local development and tests |

Set `GENESIS_LLM_PROVIDER=groq` to switch.

---

## MCP Tool Integration

Organisms get real capabilities through [Model Context Protocol](https://modelcontextprotocol.io) servers. Configure them when seeding an organism:

```json
{
  "goal": "Monitor my GitHub repo and summarise new issues daily",
  "mcp_servers": [
    {
      "name": "github",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_..." }
    }
  ]
}
```

The organism's reasoning loop automatically discovers and calls the tools the MCP server exposes.

---

## Architecture

```
Perception Event
      │
      ▼
┌─────────────────┐
│ Organism Runtime│  interprets intent against new event
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  LLM Reasoning  │  Gemini/Groq: what should I do and why?
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌────────────┐
│  Act  │ │Dream Engine│  imagines alternatives, learns safely
│ (MCP) │ └─────┬──────┘
└───┬───┘       │
    └─────┬─────┘
          ▼
┌─────────────────┐
│  Decision Store │  append to causal graph
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Skill Distiller │  compress patterns into reusable skills
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Skill Pool    │  inherited by offspring organisms
└─────────────────┘
```

---

## Project Structure

```
Genesis/
  backend/
    main.py               # Standalone FastAPI + WebSocket server
    shared/
      config.py           # Environment config
      gemini_client.py    # Gemini API wrapper
    genesis/
      types.py            # Organism, Intent, Decision, Skill models
      runtime.py          # Organism reasoning loop
      lifecycle.py        # Heartbeat supervisor for all live organisms
      store.py            # Persistence (SQLite by default)
      causality.py        # Causal graph queries + counterfactual replay
      dreams.py           # Dream engine
      events.py           # Internal event bus
      api.py              # REST API (seed, perceive, dream, edit, promote)
      skills/
        pool.py           # Skill registry
        distill.py        # Distill experience into skills
        compiler.py       # Compile skills into organism context
        inherit.py        # Skill inheritance at seed time
        sandbox.py        # Safe skill execution
      mcp/
        client.py         # MCP server pool (per-organism tool connectivity)
        catalog.py        # Global MCP server registry
      pipeline/
        stages.py         # Organism evolution pipeline stages
  frontend/
    src/
      App.jsx             # Root — renders Genesis UI
      hooks/
        useGenesis.js     # Genesis API + WebSocket hook
      components/genesis/
        GenesisPage.jsx        # Main layout
        OrganismNucleus.jsx    # Organism detail panel
        CausalGraph.jsx        # Interactive causal decision graph
        DecisionInspector.jsx  # Decision detail + counterfactual editor
        DreamStream.jsx        # Live dream event feed
        SkillLibrary.jsx       # Skill pool browser
        SkillLineageGraph.jsx  # Skill inheritance tree
        InheritancePicker.jsx  # Seed from existing skills
        Tour.jsx               # Guided onboarding
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/genesis/status` | Live runtime snapshot — heartbeats, LLM rate guard, config |
| `POST` | `/api/genesis/population/start` | Start a population evolution run |
| `GET` | `/api/genesis/population/benchmarks` | List repeatable benchmark tasks and historical baselines |
| `GET` | `/api/genesis/population` | List all evolution runs |
| `GET` | `/api/genesis/population/{run_id}` | Get one run (live state) |
| `GET` | `/api/genesis/population/{run_id}/report` | Evidence-of-learning and regression report |
| `POST` | `/api/genesis/population/{run_id}/stop` | Stop a running evolution |
| `DELETE` | `/api/genesis/population/{run_id}` | Delete a run |
| `POST` | `/api/genesis/seed` | Create a new organism from intent |
| `GET` | `/api/genesis/organisms` | List all organisms |
| `GET` | `/api/genesis/organisms/{id}` | Get one organism |
| `DELETE` | `/api/genesis/organisms/{id}` | Kill an organism |
| `POST` | `/api/genesis/organisms/{id}/perceive` | Feed a perception event |
| `POST` | `/api/genesis/organisms/{id}/dream` | Trigger a dream cycle |
| `GET` | `/api/genesis/organisms/{id}/causality` | Full causal decision graph |
| `POST` | `/api/genesis/organisms/{id}/edit/{decision_id}` | Edit a past decision |
| `GET` | `/api/genesis/organisms/{id}/branches` | List counterfactual branches |
| `POST` | `/api/genesis/organisms/{id}/branches/{bid}/promote` | Promote a branch to reality |
| `GET` | `/api/genesis/skills` | List all distilled skills |

WebSocket: `ws://localhost:8002/ws/{client_id}` — receive live organism events.

---

## Observable Evolution

The **Evolution** tab in the UI lets you run population-based experiments where organisms compete and breed across generations.

### How it works

1. You define a **task** (a shared goal) and configure population size + generation count
2. Genesis seeds N organisms, each with default reasoning strategies (systematic, analogical, cautious, exploratory)
3. The same perception event is fired at all organisms simultaneously
4. Each organism reasons and acts independently — the meta-cognitive critic scores every decision on **reasoning quality** and **action efficiency**
5. Fitness is computed: `fitness = 0.6 × reasoning_quality + 0.4 × action_efficiency`
6. The bottom 50% are culled. Top performers with fitness > 0.5 have their experience **distilled into a Skill**
7. The next generation is bred: each new organism inherits skills from 1–2 survivor parents
8. Repeat for the configured number of generations

### What you observe

- Per-organism fitness scores and decision counts after each generation
- Fitness sparkline tracking best and mean fitness across generations
- Skills distilled from survivors (visible in the Skill Library)
- Which organisms survived, which were culled, and who bred the next generation
- Benchmark baselines that compare repeat runs against prior completed attempts

### Repeatable benchmarks

The Evolution tab ships with benchmark tasks for repository triage, incident
response, and product synthesis. Starting a run with `benchmark_id` stores that
identity on the run. The report then adds regression evidence: previous completed
run count, previous best fitness, current best fitness, and delta against the
previous best. This turns Genesis into a measurable operations platform.

### Example API call

```bash
curl -X POST http://localhost:8002/api/genesis/population/start \
  -H 'Content-Type: application/json' \
  -d '{
    "benchmark_id": "repo_triage",
    "task": "Analyze the state of an open-source repository and suggest the most impactful contribution.",
    "n_organisms": 4,
    "max_generations": 3
  }'
```

---

## Configuration

All knobs are set via environment variables. Copy `.env.example` to `.env` and edit.

### LLM Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `GENESIS_LLM_PROVIDER` | `gemini` | `gemini` or `groq` |
| `GEMINI_API_KEY` | — | Required when provider is `gemini` |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `GROQ_API_KEY` | — | Required when provider is `groq` |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model name |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `GENESIS_MAX_LLM_CALLS_PER_MIN` | `0` (off) | Global ceiling across all organisms. When the 60-second sliding window fills, callers sleep until it clears. Set to `20` for Groq free tier. |

### Lifecycle & Heartbeat

| Variable | Default | Description |
|----------|---------|-------------|
| `GENESIS_LIFECYCLE` | `1` | Set to `0` to disable all heartbeats. Useful during development — organisms only act when explicitly poked via the API. |
| `GENESIS_MSG_CHECK_INTERVAL_S` | `30` | Minimum seconds between society inbox checks per organism. Prevents a broadcast to N organisms triggering N simultaneous LLM calls. |

### Development Reload

| Variable | Default | Description |
|----------|---------|-------------|
| `GENESIS_RELOAD` | `1` | Enables Uvicorn reload in non-production runs. Set to `0` for quieter smoke tests. |
| `GENESIS_RELOAD_DIRS` | `backend` | Comma-separated source directories watched by the dev reloader. |
| `GENESIS_RELOAD_EXCLUDES` | generated state dirs + DB files | Comma-separated generated paths and globs ignored by the dev reloader. |

### Dreaming

| Variable | Default | Description |
|----------|---------|-------------|
| `GENESIS_DREAMING` | `1` | Set to `0` to disable idle dream cycles entirely (zero extra LLM cost). |
| `GENESIS_IDLE_DREAM_AFTER_S` | `3600` | Seconds idle before a dream cycle fires. Lower for faster experimentation. |

### Checking live state

```bash
curl http://localhost:8002/api/genesis/status | python -m json.tool
```

Response includes which organisms have active heartbeats, calls in the last 60 seconds vs. the rate limit, and all active config values — without exposing secrets.

The runtime settings screen can also check and repair the JSON-to-SQLite mirror. Repair is explicit: the API requires `{"confirm": true}` and only backfills SQLite from the JSON source of truth.

---

## License

MIT
