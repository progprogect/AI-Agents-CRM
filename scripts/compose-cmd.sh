#!/usr/bin/env bash
# Print the docker compose command (v2 plugin or standalone v1).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=compose-common.sh
source "$ROOT/scripts/compose-common.sh"
echo "$COMPOSE"
