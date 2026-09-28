#!/usr/bin/env bash
# 一键启动所有开发服务: backend + xxl-executor + frontend
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PIDS=()

cleanup() {
  echo ""
  echo "Stopping all services..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null
  echo "All services stopped."
}
trap cleanup EXIT INT TERM

# Backend (FastAPI)
echo "Starting backend on :8080 ..."
cd "$PROJECT_DIR"
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8080 &
PIDS+=($!)

# XXL-JOB Executor
echo "Starting xxl-executor on :9991 ..."
cd "$PROJECT_DIR"
uv run python xxl_lark_translation.py &
PIDS+=($!)

# Frontend (Next.js)
echo "Starting frontend on :3000 ..."
cd "$PROJECT_DIR/frontend"
pnpm dev --port 3000 &
PIDS+=($!)

echo ""
echo "All services started:"
echo "  Backend:      http://localhost:8080"
echo "  API Docs:     http://localhost:8080/docs"
echo "  XXL Executor: :9991"
echo "  Frontend:     http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services."

wait
