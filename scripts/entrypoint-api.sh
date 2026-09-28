#!/usr/bin/env bash
# 仅启动 Backend API (FastAPI :8080)
set -e

export LOG_JSON_STDOUT=1
mkdir -p /app/logs

echo "[entrypoint-api] Starting backend on :8080 ..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers "${BACKEND_WORKERS:-1}"
