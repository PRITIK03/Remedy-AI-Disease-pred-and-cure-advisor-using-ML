# syntax=docker/dockerfile:1.7
# Build context is the repository root, so this file lives under backend/.
#
# ---------- Stage 1: dependencies ----------
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# build-essential is needed for any source-only wheels; removed from the runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# The package source is copied BEFORE the install: setuptools needs the
# `backend`, `ml` and `rag` package directories present to resolve the
# distribution, so dependency-only caching is not possible here. The heavy
# work (downloading and building wheels) is still cached by pip.
#
# pyproject.toml is the single source of truth; the legacy pinned
# requirements.txt is intentionally NOT installed (it predates the Phase 1
# package layout and would pin outdated versions of the ML stack).
COPY pyproject.toml README.md ./
COPY backend/ ./backend/
COPY ml/ ./ml/
COPY rag/ ./rag/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install ".[s3,telemetry]"

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production \
    PORT=8000

# curl is used only by the container healthcheck below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 remedy \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin remedy

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
# Application source: the `backend` package plus supporting top-level modules
# (ml, rag, alembic, app.py) that the service imports at runtime.
COPY --chown=root:root backend/ ./backend/
COPY --chown=root:root ml/ ./ml/
COPY --chown=root:root rag/ ./rag/
COPY --chown=root:root mcp/ ./mcp/
COPY --chown=root:root alembic/ ./alembic/
COPY --chown=root:root alembic.ini pyproject.toml requirements.txt ./
COPY --chown=root:root models/ ./models/

# Writable volume for local storage; only used when STORAGE_BACKEND=local.
RUN mkdir -p /app/data/reports \
    && chown -R remedy:remedy /app/data \
    && chmod -R a-w /app/backend /app/ml /app/rag /app/models

USER remedy

EXPOSE 8000

# Liveness only. Readiness (which checks DB/Redis/model/storage) is polled by
# the orchestrator via /ready, so a slow dependency never restarts the pod.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Single process behind the orchestrator's replica count; no --reload, and
# access logs are suppressed because the app emits its own structured logs.
CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT} --no-access-log --proxy-headers --forwarded-allow-ips='*'"]
