#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

require_docker

log "Restarting service..."
compose restart "${SERVICE_NAME}"
show_status
wait_for_health 120

log "Restart completed."
