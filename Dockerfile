# Unified Dockerfile: Backend + Frontend in one service
# Single Railway service serving both via nginx

# === Frontend stage ===
FROM node:20-alpine AS frontend-deps
RUN apk add --no-cache libc6-compat
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY --from=frontend-deps /app/node_modules ./node_modules
COPY frontend/ .
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production
RUN npm run build

# === Final stage: python base + node + nginx ===
FROM python:3.11-slim
RUN apt-get update && apt-get install -y \
    curl \
    nginx \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend and install deps (reuse from stage for layer cache)
COPY backend/requirements.txt /app/backend/
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend/app/ /app/backend/app/

# Copy frontend standalone (node image already has node)
COPY --from=frontend-builder /app/public /app/frontend/public
COPY --from=frontend-builder /app/.next/standalone /app/frontend/
COPY --from=frontend-builder /app/.next/static /app/frontend/.next/static

# Copy nginx config and start script
COPY nginx.conf.template /app/
COPY start.sh /app/
RUN chmod +x /app/start.sh

EXPOSE 8000

ENV PORT=8000

HEALTHCHECK --interval=15s --timeout=10s --start-period=120s --retries=5 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["/app/start.sh"]
