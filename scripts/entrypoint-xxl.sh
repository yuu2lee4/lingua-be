#!/usr/bin/env bash
# 仅启动 XXL-JOB Executor (:9991)
set -e

export LOG_JSON_STDOUT=1
mkdir -p /app/logs

echo "[entrypoint-xxl] Starting xxl-executor on :9991 ..."
exec python3 xxl_lark_translation.py
