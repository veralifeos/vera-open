# ============================================================
# Vera Open — Multi-stage Docker build
# ============================================================
# Default: slim image without embeddings (~300MB)
# With embeddings: docker compose build --build-arg INSTALL_EXTRAS=embeddings-light
# ============================================================

# Stage 1: build
FROM python:3.11-slim AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (cache layer)
COPY pyproject.toml uv.lock* ./

# Build arg for optional extras (embeddings, embeddings-light, financial, all)
ARG INSTALL_EXTRAS=""

# Install dependencies
RUN if [ -n "$INSTALL_EXTRAS" ]; then \
      uv sync --no-dev --frozen --extra "$INSTALL_EXTRAS"; \
    else \
      uv sync --no-dev --frozen; \
    fi

# Copy source code
COPY vera/ vera/
COPY config/ config/
COPY workspace/ workspace/

# Stage 2: runtime
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy venv and app from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/vera /app/vera
COPY --from=builder /app/pyproject.toml /app/pyproject.toml
COPY --from=builder /app/config /app/config
COPY --from=builder /app/workspace /app/workspace

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Create state directory
RUN mkdir -p /app/state /app/state/dedup

# Persistent volumes
VOLUME ["/app/state", "/app/config", "/app/workspace"]

ENTRYPOINT ["python", "-m", "vera"]
CMD ["briefing"]
