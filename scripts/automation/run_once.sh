#!/usr/bin/env bash
set -euo pipefail

echo "[run_once] Rebuild and run scheduler (one cycle)"
export RUN_ONCE=true

docker-compose up -d --build scheduler
echo "[run_once] Scheduler started (RUN_ONCE=true). Tail logs..."
docker-compose logs -f scheduler

echo "[run_once] Done. To run again, rerun this script."

