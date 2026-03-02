#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"
SERVICE_NAME="market-reporter"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

_detect_compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
    return
  fi
  die "Docker Compose is not available. Install Docker Desktop or docker-compose."
}

COMPOSE_CMD="$(_detect_compose_cmd)"

compose() {
  if [[ "${COMPOSE_CMD}" == "docker compose" ]]; then
    docker compose -f "${COMPOSE_FILE}" "$@"
  else
    docker-compose -f "${COMPOSE_FILE}" "$@"
  fi
}

require_docker() {
  command -v docker >/dev/null 2>&1 || die "Docker is not installed or not in PATH."
  docker info >/dev/null 2>&1 || die "Docker daemon is not running."
}

ensure_runtime_dirs() {
  mkdir -p "${PROJECT_ROOT}/config" "${PROJECT_ROOT}/data" "${PROJECT_ROOT}/output"
}

show_status() {
  compose ps
}

wait_for_health() {
  local timeout="${1:-120}"
  local begin
  begin="$(date +%s)"

  while true; do
    local status
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' "${SERVICE_NAME}" 2>/dev/null || true)"

    if [[ "${status}" == "healthy" ]]; then
      log "Service ${SERVICE_NAME} is healthy."
      return 0
    fi

    if [[ -z "${status}" || "${status}" == "exited" || "${status}" == "dead" ]]; then
      die "Service ${SERVICE_NAME} is not running. Check logs with: ./bin/logs.sh"
    fi

    if (( $(date +%s) - begin >= timeout )); then
      die "Service health check timed out after ${timeout}s (status=${status})."
    fi

    sleep 2
  done
}
