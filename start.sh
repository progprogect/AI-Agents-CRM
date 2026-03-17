#!/bin/sh
set -e

# Run migrations (idempotent; skip if already applied)
echo "Checking DATABASE_URL..."
if [ "$SKIP_MIGRATIONS" = "1" ]; then
  echo "SKIP_MIGRATIONS=1 - skipping migrations"
elif [ -n "$DATABASE_URL" ] || [ -n "$DATABASE_PUBLIC_URL" ]; then
  echo "Running migrations..."
  cd /app/backend && python3 scripts/init_db.py || { echo "MIGRATION FAILED - check Postgres link in Railway Variables"; exit 1; }
  cd /app
  echo "Migrations done."
else
  echo "WARNING: DATABASE_URL and DATABASE_PUBLIC_URL not set - skipping migrations. Link PostgreSQL in Railway."
fi

# Substitute PORT in nginx config
PORT="${PORT:-8000}"
sed "s/__PORT__/$PORT/g" /app/nginx.conf.template > /tmp/nginx.conf

# Start backend in background
cd /app/backend && PYTHONPATH=/app/backend uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend in background (Next.js standalone)
cd /app/frontend && PORT=3000 HOSTNAME=0.0.0.0 node server.js &
FRONTEND_PID=$!

# Wait for backend to be ready (connects to DB in lifespan)
echo "Waiting for backend to be ready..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "Backend is ready"
    break
  fi
  if [ $i -eq 30 ]; then
    echo "ERROR: Backend failed to start after 60s. Check DATABASE_URL and logs."
    exit 1
  fi
  sleep 2
done

# Start nginx in foreground (daemon off is in config)
nginx -c /tmp/nginx.conf &
NGINX_PID=$!

# Wait for nginx; if it exits, we exit
wait $NGINX_PID
