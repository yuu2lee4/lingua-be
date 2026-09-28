#!/usr/bin/env bash
# K8s 单 Pod 入口: 同时运行 backend + xxl-executor + frontend
set -e

PIDS=()

cleanup() {
  echo "[entrypoint] Received signal, shutting down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null
  echo "[entrypoint] All services stopped."
  exit 0
}
trap cleanup SIGTERM SIGINT

# JSON 日志直接输出到 stdout，供 Grafana/Loki 采集
export LOG_JSON_STDOUT=1

mkdir -p /app/logs

# 1) Backend (FastAPI)
echo "[entrypoint] Starting backend on :8080 ..."
uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers "${BACKEND_WORKERS:-1}" 2>&1 &
PIDS+=($!)

# 2) XXL-JOB Executor
echo "[entrypoint] Starting xxl-executor on :9991 ..."
python3 xxl_lark_translation.py 2>&1 &
PIDS+=($!)

# 3) Frontend (Next.js standalone)
echo "[entrypoint] Starting frontend on :3000 ..."
node /app/frontend/server.js 2>&1 &
PIDS+=($!)

echo "[entrypoint] All services started. PIDs: ${PIDS[*]}"

# 等待任一服务进程退出
wait -n "${PIDS[@]}"
EXIT_CODE=$?
echo "[entrypoint] A service exited with code $EXIT_CODE, stopping all..."
cleanup
exit $EXIT_CODE
