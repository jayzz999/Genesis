# Render Deployment Runbook

Genesis deploys to Render as one Docker web service. The container builds the
React app, serves it from FastAPI, and stores runtime data on a persistent disk
mounted at `/app/data`.

## 1. Push The Repo

Render deploys from Git. Make sure the current branch is pushed to GitHub:

```bash
git status
git push origin <branch-name>
```

## 2. Create The Blueprint

1. Open Render Dashboard.
2. Click **New +**.
3. Choose **Blueprint**.
4. Connect `jayzz999/Genesis`.
5. Select the branch you want to deploy.
6. Render should detect `render.yaml`.
7. Click **Apply**.

The Blueprint creates:

- Docker web service: `genesis`
- Persistent disk: `/app/data`, 5 GB
- Health check: `/api/health`
- Generated `GENESIS_API_TOKEN`
- Secret slots for LLM and connector credentials

## 3. Add Required Secrets

In the Render service, open **Environment** and set:

```bash
GEMINI_API_KEY=<your Gemini key>
GROQ_API_KEY=<your Groq key, optional fallback>
```

The Blueprint defaults to Gemini:

```bash
GENESIS_LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-2.5-flash
GENESIS_MAX_LLM_CALLS_PER_MIN=6
GENESIS_LIFECYCLE=0
GENESIS_DREAMING=0
```

Those defaults keep the public demo controlled and avoid surprise background LLM
usage. Turn lifecycle/dreaming on only after you are comfortable with provider
limits and connector behavior.

## 4. Add Real Connector Secrets

Only configure systems you want Genesis to touch:

```bash
GITHUB_TOKEN=<GitHub PAT or app token>
GENESIS_GITHUB_REPOSITORIES=jayzz999/Academic-Research-Agent
GENESIS_CONNECTOR_HTTP_ALLOWLIST=api.github.com

GENESIS_SLACK_WEBHOOK_URL=<Slack incoming webhook URL>
GENESIS_MESSAGE_WEBHOOK_URL=<optional generic webhook URL>
GENESIS_CONNECTOR_WEBHOOK_ALLOWLIST=hooks.slack.com
```

Optional production-only connectors:

```bash
GENESIS_DEPLOY_WEBHOOK_URL=<deploy executor webhook>
GENESIS_CONNECTOR_DEPLOY_ALLOWLIST=<deploy webhook host>

GENESIS_BROWSER_CONNECTOR_ENABLED=1
GENESIS_BROWSER_CONNECTOR_WEBHOOK_URL=<browser executor webhook>
GENESIS_CONNECTOR_BROWSER_ALLOWLIST=<browser executor host>
```

## 5. Host And Auth

On Render, Genesis derives safe same-origin CORS and trusted-host defaults from
Render metadata. If you add a custom domain, set these explicitly:

```bash
GENESIS_CORS_ORIGINS=https://your-domain.example
GENESIS_TRUSTED_HOSTS=your-domain.example
```

Do not set `VITE_GENESIS_API_TOKEN` in production. The UI should use sessions:

1. Open the deployed app.
2. In the Auth panel, bootstrap the first owner user.
3. Log in with that user.
4. The browser stores a session token locally.

## 6. Verify

After deployment:

```bash
curl https://<render-service>.onrender.com/api/health
```

Then use the UI:

1. Create or open an organism.
2. Run connector configuration checks.
3. Create an approval.
4. Execute the approved connector.
5. Confirm the connector ledger says `complete` and `simulated: false`.

For the final demo, keep lifecycle off until you intentionally start background
autonomy. That makes the system real without burning provider quota while idle.
