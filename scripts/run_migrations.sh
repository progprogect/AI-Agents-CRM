#!/bin/sh
# Run PostgreSQL migrations. Use from project root.
# Option 1 (Railway): railway run ./scripts/run_migrations.sh
# Option 2 (local):   DATABASE_URL='postgresql://...' ./scripts/run_migrations.sh

set -e
cd "$(dirname "$0")/.."
cd backend

if [ -z "$DATABASE_URL" ] && [ -z "$DATABASE_PUBLIC_URL" ]; then
  echo "Error: DATABASE_URL or DATABASE_PUBLIC_URL must be set"
  exit 1
fi

echo "Running migrations..."
python3 scripts/init_db.py
echo "Done."
