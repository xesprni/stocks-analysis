#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

require_docker
ensure_runtime_dirs

log "Deploying service (build + up)..."
compose up -d --build
show_status
wait_for_health 180

log "Deploy completed. URL: http://127.0.0.1:8000"
