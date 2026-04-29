# Genesis — Living Digital Organisms

> An open-source framework for creating autonomous AI agents modelled as living organisms: they perceive events, reason about what to do, act through real tools (MCP), build a causal memory of every decision, dream up hypothetical futures, and distill what they learn into inheritable skills.

---

## What Makes Genesis Different

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

---

## Organism Lifecycle

```
SEEDED ──> PERCEIVING ──> ACTING ──> PERCEIVING (loop)
                                 └──> DREAMING ──> PERCEIVING
                                 └──> DYING ──> DEAD (skills donated to pool)
```

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
# Edit .env — at minimum set GEMINI_API_KEY

# 4. Start the backend
python -m backend.main

# 5. In a new terminal — start the frontend
cd frontend && npm install && npm run dev
```

Open **http://localhost:3001** and seed your first organism.

---

## LLM Providers

Genesis supports two providers out of the box:

| Provider | Env var | Notes |
|----------|---------|-------|
| Google Gemini (default) | `GEMINI_API_KEY` | Best quality, used in production |
| Groq (free tier) | `GROQ_API_KEY` | Great for local dev — fast, free |

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
| `GET` | `/api/genesis/population` | List all evolution runs |
| `GET` | `/api/genesis/population/{run_id}` | Get one run (live state) |
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

## Observable Evolution (Phase 6)

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

### Example API call

```bash
curl -X POST http://localhost:8002/api/genesis/population/start \
  -H 'Content-Type: application/json' \
  -d '{
    "task": "Monitor a GitHub repository and summarise new issues daily",
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

---

## License

MIT
