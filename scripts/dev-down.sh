#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=compose-common.sh
source "$ROOT/scripts/compose-common.sh"

if [ "${1:-}" = "--volumes" ] || [ "${1:-}" = "-v" ]; then
  echo "Stopping stack and removing volumes (database will be reset)"
  compose_run down -v --remove-orphans
else
  compose_run down --remove-orphans
fi
