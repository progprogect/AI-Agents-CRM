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

# Wait for both to be ready
sleep 3

# Start nginx in foreground (keeps container running)
nginx -c /tmp/nginx.conf -g "daemon off;" &
NGINX_PID=$!

# Wait for nginx; if it exits, we exit
wait $NGINX_PID
