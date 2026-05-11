# Genesis Development Prompts

This document contains reusable prompts for developing the Genesis project with
an AI coding assistant. These are not the runtime prompts sent by Genesis to its
LLM provider. They are project-development prompts for planning, implementation,
review, testing, and documentation.

Use these prompts from the repository root:

```text
/Users/jayanthmuthina/Documents/Projects/Genesis
```

Before using any prompt, ask the assistant to inspect the current code first and
preserve unrelated local changes.

## General Project Context Prompt

Use this at the start of a new development session.

```text
You are working in the Genesis repository.

Genesis is a governed autonomous-operations platform for persistent AI
organisms. Each organism has an identity, immutable goal, lifecycle state,
causal memory, dreams/counterfactual branches, learned skills, inheritance,
approval-gated permissions, and real connector adapters.

Read README.md, docs/SPEC_SHEET.md, backend/main.py, backend/genesis/api.py,
backend/genesis/runtime.py, backend/shared/config.py, and tests/test_smoke.py
before changing code.

Constraints:
- Preserve unrelated uncommitted changes.
- Keep implementation consistent with existing FastAPI, React, Vite, and pytest
  patterns.
- Treat approval, connector, permission, auth, and governance behavior as
  production-critical.
- Do not simulate success for real connectors when credentials, allowlists, or
  permission grants are missing.
- Use GENESIS_LLM_PROVIDER=mock for local no-key tests.
- Update tests and documentation when behavior changes.

After implementation, run the narrowest meaningful tests first, then broader
verification if the change touches shared behavior.
```

## Feature Implementation Prompt

Use this when adding a new Genesis capability.

```text
Implement the following Genesis feature:

Feature:
[describe the feature]

Expected user workflow:
[describe the UI/API/operator flow]

Safety requirements:
- Any real external side effect must require an explicit allowlist and scoped
  permission grant.
- Missing configuration must fail closed and produce auditable status.
- Mutating routes must use require_api_token when API token protection is
  enabled.
- Connector runs and approvals must preserve enough evidence for later review.

Implementation guidance:
- Inspect existing patterns in backend/genesis/api.py, backend/genesis/connectors.py,
  backend/genesis/approvals.py, backend/genesis/governance.py, and related tests.
- Keep backend state files under the appropriate GENESIS_*_STORAGE location.
- Add or update focused tests in tests/test_smoke.py or a targeted test file.
- Add frontend controls only if the feature needs operator interaction.
- Update README.md, docs/SPEC_SHEET.md, or a focused docs file if the operating
  contract changes.

Deliver:
- Code changes.
- Tests or a clear explanation of why no test is appropriate.
- A concise summary of behavior, files changed, and verification run.
```

## Backend API Prompt

Use this when adding or changing FastAPI routes.

```text
Add or modify Genesis backend API behavior:

Endpoint or behavior:
[describe endpoint, payload, response, and error states]

Read these files first:
- backend/genesis/api.py
- backend/genesis/types.py
- backend/shared/config.py
- tests/test_smoke.py

Requirements:
- Use existing request/response model style.
- Protect mutating endpoints with require_api_token.
- Emit events when the UI should update live.
- Return structured errors that the frontend can display.
- Avoid leaking secrets in status/config responses.
- Add pytest coverage using httpx ASGITransport when possible.

Verification:
- Run the targeted pytest test for the new route.
- Run pytest -q if the change touches auth, lifecycle, approvals, connectors,
  or shared runtime behavior.
```

## Frontend Product Prompt

Use this when improving the Genesis UI.

```text
Improve the Genesis frontend for this workflow:

Workflow:
[describe what the operator should be able to do]

Read these files first:
- frontend/src/components/genesis/GenesisPage.jsx
- frontend/src/hooks/useGenesis.js
- related panel components under frontend/src/components/genesis/
- frontend/src/index.css

Design requirements:
- Genesis is an operations console, not a marketing landing page.
- Keep the interface dense, scan-friendly, and work-focused.
- Use existing visual patterns, colors, panels, badges, and controls.
- Make error, loading, empty, blocked, approved, and completed states visible.
- Do not add decorative UI that does not help operators inspect or act.
- Do not expose secrets.

Implementation requirements:
- Keep API calls in the existing hook/helper style.
- Preserve responsive behavior.
- Avoid breaking existing panels.
- Run cd frontend && npm run build.

Deliver:
- UI changes.
- Any backend contract updates needed.
- Screenshot or browser verification if visual layout changed substantially.
```

## Connector Development Prompt

Use this when adding a new real-world connector.

```text
Add a new Genesis connector adapter:

Connector:
[name and external system]

Side effect:
[exact action the connector can perform]

Required configuration:
[environment variables, allowlists, scopes]

Read these files first:
- backend/genesis/connectors.py
- backend/genesis/approvals.py
- backend/genesis/governance.py
- backend/genesis/api.py
- tests/test_smoke.py
- .env.example
- README.md

Safety contract:
- The connector must fail closed when credentials are absent.
- The connector must require a scoped permission grant for real side effects.
- The connector must enforce an allowlist for external destinations or resource
  scopes.
- The connector must write an auditable run status: complete, blocked, or failed.
- Probe behavior must verify configuration without performing destructive or
  externally visible side effects.
- Tests must cover missing config, wrong scope, missing grant, and a successful
  mocked real call.

Update:
- .env.example
- README connector table
- docs/SPEC_SHEET.md connector section if the public contract changes
- Frontend connector UI only if operators need controls for this adapter
```

## Approval And Governance Prompt

Use this when changing approval, grant, or governance behavior.

```text
Modify Genesis approval/governance behavior:

Change:
[describe requested behavior]

Read these files first:
- backend/genesis/approvals.py
- backend/genesis/governance.py
- backend/genesis/connectors.py
- backend/genesis/api.py
- frontend/src/components/genesis/ApprovalPanel.jsx
- frontend/src/components/genesis/ApprovalGovernancePanel.jsx
- frontend/src/components/genesis/ApprovalIntegrityPanel.jsx
- tests/test_smoke.py

Requirements:
- Preserve auditability and deterministic integrity checks.
- Do not allow Genesis to self-approve credential requests or unsafe actions.
- Keep break-glass access bounded, visible, and one-use where applicable.
- Preserve reviewer/quorum rules for critical actions.
- Add regression tests for blocked and allowed paths.

Deliver:
- Behavior change.
- Tests proving the new policy.
- Documentation update if the operating policy changed.
```

## Runtime Reasoning Prompt

Use this when changing the organism perception/reasoning/action loop.

```text
Change Genesis organism runtime behavior:

Runtime change:
[describe how organisms should perceive, reason, act, dream, or remember]

Read these files first:
- backend/genesis/runtime.py
- backend/genesis/lifecycle.py
- backend/genesis/causality.py
- backend/genesis/dreams.py
- backend/genesis/memory.py
- backend/genesis/skills/
- tests/test_smoke.py

Requirements:
- Every real decision must preserve trigger, reasoning, action, result, and
  alternatives.
- Dream/counterfactual behavior must remain isolated from real side effects.
- Unknown or unsafe tools must fail clearly.
- Provider quota failures should degrade to safe, auditable no-op behavior.
- Repository monitoring should not repeatedly forge MCP servers when a
  github_repo perception source already exists.
- Add tests for both normal behavior and safety fallback.

Deliver:
- Runtime changes.
- Focused tests.
- Notes on any behavior that affects existing organisms or stored decisions.
```

## Skill And Inheritance Prompt

Use this when changing skill distillation, inheritance, or compiled skills.

```text
Update Genesis skills/inheritance behavior:

Change:
[describe distillation, inheritance, compiled skill, or lineage behavior]

Read these files first:
- backend/genesis/skills/distill.py
- backend/genesis/skills/pool.py
- backend/genesis/skills/inherit.py
- backend/genesis/skills/compiler.py
- backend/genesis/runtime.py
- tests/test_smoke.py

Requirements:
- Preserve skill lineage and parent references.
- Keep distillation deterministic enough for tests, with fallback behavior when
  LLM output is invalid.
- Compiled skills must validate syntax before being saved.
- Inherited skills must not bypass connector approval or permission checks.
- Add tests for lineage, inheritance, and fallback paths.
```

## Testing Prompt

Use this when asking an assistant to improve coverage.

```text
Review Genesis test coverage for this area:

Area:
[runtime / connectors / approvals / frontend build / deployment / auth / etc.]

Read the implementation and tests first. Identify high-risk behavior that is not
covered, then add focused tests.

Testing requirements:
- Prefer deterministic tests with GENESIS_LLM_PROVIDER=mock.
- Mock external network calls and provider calls.
- Cover both success and blocked/failure paths.
- Use isolated storage paths so tests do not touch local runtime data.
- Avoid brittle assertions against long generated strings.

After adding tests:
- Run the targeted test.
- If shared behavior changed, run pytest -q.
```

## Documentation Prompt

Use this when updating project docs.

```text
Update Genesis documentation for:

Topic:
[describe the feature, workflow, deployment, or operating contract]

Read existing docs first:
- README.md
- docs/SPEC_SHEET.md
- docs/RENDER_DEPLOYMENT.md
- .env.example
- relevant backend/frontend files

Documentation requirements:
- Document what the system actually does today.
- Separate local development, production deployment, and demo/proof behavior.
- Call out safety gates: auth token, approvals, grants, allowlists, and fail-closed
  connector behavior.
- Keep commands copy-pasteable.
- Avoid overclaiming autonomy or production readiness beyond tested behavior.

Deliver:
- Updated docs.
- Mention any code/docs mismatch found.
```

## Deployment Prompt

Use this when preparing a production or Render deployment.

```text
Prepare Genesis for deployment:

Target:
[Render / Docker Compose / custom host]

Read these files first:
- Dockerfile
- docker-compose.yml
- render.yaml
- docs/RENDER_DEPLOYMENT.md
- scripts/production_preflight.py
- backend/shared/config.py
- README.md

Requirements:
- Production must reject GENESIS_LLM_PROVIDER=mock.
- Production must require GENESIS_REQUIRE_API_TOKEN=1.
- Production must use exact CORS origins and trusted hosts.
- Do not place production API tokens into public frontend builds.
- Confirm health check path is /api/health.
- Keep lifecycle and dreaming off by default for controlled public demos unless
  explicitly requested.

Verification:
- Run production_preflight with representative env.
- Build the frontend/container when feasible.
- Document required secrets and post-deploy verification steps.
```

## Code Review Prompt

Use this to review changes before committing.

```text
Review the current Genesis changes as a senior engineer.

Focus on:
- Bugs, regressions, unsafe connector behavior, auth gaps, approval bypasses,
  data loss, secret leaks, and missing tests.
- Whether implementation matches README.md and docs/SPEC_SHEET.md.
- Whether frontend behavior exposes blocked/error states clearly.
- Whether production settings still fail closed.

Output:
- Findings first, ordered by severity, with file and line references.
- Open questions or assumptions.
- A brief summary of what changed.
- Tests still needed.

Do not spend time on cosmetic issues unless they create product confusion or
operator risk.
```

## Release Checklist Prompt

Use this before publishing a branch or opening a PR.

```text
Prepare a Genesis release/PR summary.

Inspect:
- git status
- git diff
- README.md
- docs/SPEC_SHEET.md
- tests touched by the change

Produce:
- Summary of behavior changes.
- Files changed by category: backend, frontend, docs, tests, config.
- Safety impact: auth, approvals, grants, connectors, persistence, secrets.
- Verification run and results.
- Known risks or follow-up work.

If anything production-critical changed without tests, call that out explicitly.
```
