#!/usr/bin/env bash
# 墨读 · 公版书库 启动脚本
set -euo pipefail
cd "$(dirname "$0")"
: "${PORT:=8000}"
: "${HOST:=0.0.0.0}"
exec python3 -m uvicorn app:app --host "$HOST" --port "$PORT"
