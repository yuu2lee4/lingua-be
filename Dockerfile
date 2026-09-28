# ============================================================
# Stage 1: Python dependencies
# ============================================================
FROM python:3.13-slim-bookworm AS py-builder

RUN apt-get update && apt-get install -y build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-cache --no-dev

# ============================================================
# Stage 2: Frontend build (bookworm-slim for glibc compat)
# ============================================================
FROM node:22-bookworm-slim AS fe-builder

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ .

ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8080/api/v1
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

RUN pnpm build

# ============================================================
# Stage 3: Production (single container, 3 services)
# ============================================================
FROM python:3.13-slim-bookworm AS production

RUN apt-get update && apt-get install -y \
    ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (for Next.js standalone server)
COPY --from=fe-builder /usr/local/bin/node /usr/local/bin/node

WORKDIR /app

# --- Python backend ---
COPY --from=py-builder /app/.venv /app/.venv
COPY app ./app
COPY data ./data
COPY examples ./examples
COPY xxl_lark_translation.py ./

# --- Frontend standalone ---
COPY --from=fe-builder /app/public /app/frontend/public
COPY --from=fe-builder /app/.next/standalone /app/frontend
COPY --from=fe-builder /app/.next/static /app/frontend/.next/static

# --- Entrypoint ---
COPY scripts/entrypoint.sh /app/entrypoint.sh
COPY scripts/entrypoint-api.sh /app/entrypoint-api.sh
COPY scripts/entrypoint-xxl.sh /app/entrypoint-xxl.sh
COPY grace_stop.sh /app/grace_stop.sh

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000

EXPOSE 8080 9991 3000

CMD ["/app/entrypoint-api.sh"]
