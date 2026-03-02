#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

require_docker

if [[ ! -d "${PROJECT_ROOT}/.git" ]]; then
  die "This script requires a git checkout at ${PROJECT_ROOT}."
fi

if [[ -n "$(git -C "${PROJECT_ROOT}" status --porcelain)" ]]; then
  die "Working tree has local changes. Commit/stash before update."
fi

log "Pulling latest code..."
git -C "${PROJECT_ROOT}" fetch --all --prune
git -C "${PROJECT_ROOT}" pull --ff-only

ensure_runtime_dirs
log "Rebuilding and restarting service..."
compose up -d --build
show_status
wait_for_health 180

log "Update completed."
