#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/local_common.sh"

load_env_if_exists
ensure_runtime_dirs

if [[ "${SKIP_UV_SYNC:-0}" != "1" ]]; then
  sync_backend_deps
else
  log "Skipping uv sync (SKIP_UV_SYNC=1)"
fi

build_frontend_assets

if is_running; then
  log "Existing backend detected, stopping first"
  stop_backend
fi

start_backend "${MARKET_REPORTER_RELOAD:-0}"
wait_for_health 120
show_backend_status

log "Local deploy completed. URL: http://127.0.0.1:${BACKEND_PORT}"
