#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${PROJECT_ROOT}/run"
LOG_DIR="${PROJECT_ROOT}/logs"
PID_FILE="${RUN_DIR}/market-reporter.pid"
BACKEND_LOG_FILE="${LOG_DIR}/market-reporter.log"

BACKEND_HOST="${MARKET_REPORTER_API_HOST:-0.0.0.0}"
BACKEND_PORT="${MARKET_REPORTER_API_PORT:-8000}"
HEALTH_URL="http://127.0.0.1:${BACKEND_PORT}/api/health"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

load_env_if_exists() {
  if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    # shellcheck disable=SC1090
    set -a && source "${PROJECT_ROOT}/.env" && set +a
  fi
}

require_cmd() {
  local name="$1"
  command -v "${name}" >/dev/null 2>&1 || die "Required command not found: ${name}"
}

ensure_runtime_dirs() {
  mkdir -p "${PROJECT_ROOT}/config" "${PROJECT_ROOT}/data" "${PROJECT_ROOT}/output"
  mkdir -p "${RUN_DIR}" "${LOG_DIR}"
}

read_pid() {
  if [[ -f "${PID_FILE}" ]]; then
    tr -d ' \n\r\t' <"${PID_FILE}"
    return
  fi
  printf ''
}

is_running() {
  local pid
  pid="$(read_pid)"
  if [[ -z "${pid}" ]]; then
    return 1
  fi
  kill -0 "${pid}" >/dev/null 2>&1
}

start_backend() {
  local reload_flag="${1:-0}"

  if is_running; then
    die "Backend is already running (pid=$(read_pid))."
  fi

  require_cmd uv
  ensure_runtime_dirs

  local cmd=(uv run market-reporter serve --host "${BACKEND_HOST}" --port "${BACKEND_PORT}")
  if [[ "${reload_flag}" == "1" ]]; then
    cmd+=(--reload)
  fi

  log "Starting backend on ${BACKEND_HOST}:${BACKEND_PORT}"
  (
    cd "${PROJECT_ROOT}"
    nohup "${cmd[@]}" >>"${BACKEND_LOG_FILE}" 2>&1 &
    echo $! >"${PID_FILE}"
  )
}

stop_backend() {
  local pid
  pid="$(read_pid)"

  if [[ -z "${pid}" ]]; then
    log "No pid file found; backend already stopped."
    return 0
  fi

  if ! kill -0 "${pid}" >/dev/null 2>&1; then
    log "Stale pid file found (pid=${pid}), cleaning up."
    rm -f "${PID_FILE}"
    return 0
  fi

  log "Stopping backend pid=${pid}"
  kill "${pid}" >/dev/null 2>&1 || true

  local waited=0
  while kill -0 "${pid}" >/dev/null 2>&1; do
    if (( waited >= 20 )); then
      log "Process did not exit in time, sending SIGKILL"
      kill -9 "${pid}" >/dev/null 2>&1 || true
      break
    fi
    sleep 1
    waited=$((waited + 1))
  done

  rm -f "${PID_FILE}"
}

wait_for_health() {
  local timeout="${1:-120}"
  local started_at
  started_at="$(date +%s)"

  while true; do
    if curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
      log "Health check passed: ${HEALTH_URL}"
      return 0
    fi

    if (( $(date +%s) - started_at >= timeout )); then
      die "Health check timeout after ${timeout}s: ${HEALTH_URL}"
    fi
    sleep 2
  done
}

show_backend_status() {
  if is_running; then
    log "Backend running (pid=$(read_pid))"
  else
    log "Backend stopped"
  fi

  if curl -fsS "${HEALTH_URL}" >/dev/null 2>&1; then
    log "Health endpoint: OK (${HEALTH_URL})"
  else
    log "Health endpoint: FAIL (${HEALTH_URL})"
  fi
}

sync_backend_deps() {
  require_cmd uv
  log "Syncing Python dependencies with uv"
  (
    cd "${PROJECT_ROOT}"
    UV_CACHE_DIR=.uv-cache uv sync
  )
}

build_frontend_assets() {
  if [[ "${SKIP_FRONTEND_BUILD:-0}" == "1" ]]; then
    log "Skipping frontend build (SKIP_FRONTEND_BUILD=1)"
    return 0
  fi

  if [[ ! -f "${PROJECT_ROOT}/frontend/package.json" ]]; then
    log "frontend/package.json not found, skipping frontend build"
    return 0
  fi

  require_cmd npm

  log "Installing frontend dependencies"
  (
    cd "${PROJECT_ROOT}/frontend"
    if [[ -f package-lock.json ]]; then
      npm ci
    else
      npm install
    fi
  )

  log "Building frontend assets"
  (
    cd "${PROJECT_ROOT}/frontend"
    npm run build
  )
}

ensure_clean_git_tree() {
  if [[ ! -d "${PROJECT_ROOT}/.git" ]]; then
    die "Not a git checkout: ${PROJECT_ROOT}"
  fi
  if [[ -n "$(git -C "${PROJECT_ROOT}" status --porcelain)" ]]; then
    die "Working tree has local changes. Commit/stash before update."
  fi
}

git_fast_forward_update() {
  ensure_clean_git_tree
  log "Fetching latest changes"
  git -C "${PROJECT_ROOT}" fetch --all --prune
  log "Applying fast-forward update"
  git -C "${PROJECT_ROOT}" pull --ff-only
}
