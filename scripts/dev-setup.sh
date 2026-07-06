#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck source=compose-common.sh
source "$ROOT/scripts/compose-common.sh"

copy_if_missing() {
  local src="$1"
  local dest="$2"
  if [ ! -f "$dest" ]; then
    cp "$src" "$dest"
    echo "Created $dest from $src"
  else
    echo "Already exists: $dest (skipped)"
  fi
}

echo "==> Setting up local Docker environment"
compose_warn_legacy

copy_if_missing ".env.docker.example" ".env"
copy_if_missing "backend/.env.example" "backend/.env"
copy_if_missing "frontend/.env.local.example" "frontend/.env.local"

if ! grep -q '^OPENAI_API_KEY=.\+' backend/.env 2>/dev/null; then
  echo ""
  echo "WARNING: Set OPENAI_API_KEY in backend/.env before starting the stack."
fi

if ! grep -q '^SECRET_ENCRYPTION_KEY=.\+' backend/.env 2>/dev/null; then
  echo ""
  echo "Generating SECRET_ENCRYPTION_KEY in backend/.env..."
  if command -v python3 >/dev/null 2>&1; then
    KEY="$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")"
    if grep -q '^SECRET_ENCRYPTION_KEY=' backend/.env; then
      sed -i "s|^SECRET_ENCRYPTION_KEY=.*|SECRET_ENCRYPTION_KEY=${KEY}|" backend/.env
    else
      echo "SECRET_ENCRYPTION_KEY=${KEY}" >> backend/.env
    fi
    echo "SECRET_ENCRYPTION_KEY generated."
  else
    echo "Install Python 3 and run:"
    echo "  python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    echo "Then set SECRET_ENCRYPTION_KEY in backend/.env"
  fi
fi

echo ""
echo "==> Starting Postgres and Redis"
compose_run up -d postgres redis

echo "==> Waiting for Postgres to be healthy"
for i in $(seq 1 30); do
  if compose_run exec -T postgres pg_isready -U "${POSTGRES_USER:-agent}" -d "${POSTGRES_DB:-agent_db}" >/dev/null 2>&1; then
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "ERROR: Postgres did not become healthy in time"
    exit 1
  fi
  sleep 2
done

echo "==> Running database migrations"
compose_run --profile setup run --rm migrate

echo ""
echo "Setup complete."
echo "  1. Edit backend/.env — set OPENAI_API_KEY if not done yet"
echo "  2. Run: ./scripts/dev-up.sh"
echo "  3. Open http://localhost:3000 (admin login: http://localhost:3000/admin/login)"
