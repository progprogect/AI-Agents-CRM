#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=compose-common.sh
source "$ROOT/scripts/compose-common.sh"

if [ ! -f ".env" ] || [ ! -f "backend/.env" ] || [ ! -f "frontend/.env.local" ]; then
  echo "Local env files missing. Run ./scripts/dev-setup.sh first."
  exit 1
fi

compose_warn_legacy
compose_v1_workaround
compose_run up -d --build "$@"
