#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

require_docker

TAIL_LINES="${1:-200}"

if [[ ! "${TAIL_LINES}" =~ ^[0-9]+$ ]]; then
  die "Tail lines must be a number. Example: ./bin/logs.sh 300"
fi

compose logs --tail "${TAIL_LINES}" -f "${SERVICE_NAME}"
