#!/bin/sh
set -e

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

# Start nginx in foreground (keeps container running)
nginx -c /tmp/nginx.conf -g "daemon off;" &
NGINX_PID=$!

# Wait for nginx; if it exits, we exit
wait $NGINX_PID
