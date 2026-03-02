#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/local_common.sh"

TAIL_LINES="${1:-200}"

if [[ ! "${TAIL_LINES}" =~ ^[0-9]+$ ]]; then
  die "Tail lines must be a number. Example: ./bin/logs-local.sh 300"
fi

if [[ ! -f "${BACKEND_LOG_FILE}" ]]; then
  die "Log file does not exist yet: ${BACKEND_LOG_FILE}"
fi

tail -n "${TAIL_LINES}" -f "${BACKEND_LOG_FILE}"
