FROM node:22-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GENESIS_ENV=production \
    GENESIS_FRONTEND_DIST=/app/frontend/dist \
    DATABASE_URL=sqlite+aiosqlite:////app/data/genesis.db \
    GENESIS_STORAGE=/app/data/organisms \
    GENESIS_POPULATION_STORAGE=/app/data/populations \
    GENESIS_MEMORY_STORAGE=/app/data/memories \
    GENESIS_TOOL_SANDBOX_STORAGE=/app/data/tool_runs \
    GENESIS_COLLAB_STORAGE=/app/data/collaborations \
    GENESIS_IMPROVEMENT_STORAGE=/app/data/improvements \
    GENESIS_OPERATOR_STORAGE=/app/data/operators \
    GENESIS_APPROVAL_STORAGE=/app/data/approvals \
    GENESIS_CONNECTOR_STORAGE=/app/data/connectors \
    GENESIS_GOVERNANCE_STORAGE=/app/data/governance \
    GENESIS_CAPABILITY_STORAGE=/app/data/capabilities \
    GENESIS_INTELLIGENCE_STORAGE=/app/data/intelligence \
    GENESIS_RELIABILITY_STORAGE=/app/data/reliability \
    GENESIS_WORLD_MODEL_STORAGE=/app/data/world_model \
    GENESIS_LIVING_SYSTEMS_STORAGE=/app/data/living_systems \
    GENESIS_NERVOUS_SYSTEM_STORAGE=/app/data/nervous_system
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin genesis \
    && mkdir -p /app/data
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY scripts ./scripts
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN chown -R genesis:genesis /app
USER genesis
EXPOSE 8002
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8002}/api/health" || exit 1
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8002}"]
