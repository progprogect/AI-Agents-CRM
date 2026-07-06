#!/usr/bin/env bash
# Shared Docker Compose helpers for dev scripts.
# Source this file; do not execute directly.

if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
  COMPOSE_LEGACY=0
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
  COMPOSE_LEGACY=1
else
  echo "ERROR: docker compose or docker-compose not found" >&2
  echo "Install Docker Compose v2: sudo apt install docker-compose-v2" >&2
  exit 1
fi

compose_warn_legacy() {
  if [ "$COMPOSE_LEGACY" = 1 ]; then
    echo ""
    echo "WARNING: Using legacy docker-compose v1."
    echo "  docker-compose 1.29 is incompatible with Docker Engine 28+ and may fail with:"
    echo "  KeyError: 'ContainerConfig'"
    echo ""
    echo "  Recommended: sudo apt install docker-compose-v2"
    echo "  Then re-run this script (scripts auto-detect 'docker compose')."
    echo ""
  fi
}

# docker-compose v1 fails when recreating containers on Docker 28+.
# Remove app containers first so 'up' creates fresh ones instead of merging old metadata.
compose_v1_workaround() {
  if [ "$COMPOSE_LEGACY" = 1 ]; then
    $COMPOSE rm -f -s backend frontend 2>/dev/null || true
  fi
}

compose_run() {
  # shellcheck disable=SC2086
  $COMPOSE "$@"
}
