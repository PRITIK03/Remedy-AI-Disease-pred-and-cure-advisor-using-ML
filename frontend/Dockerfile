# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Remedy-AI frontend — production multi-stage Next.js image (Phase 9).
#
# Build context is the REPOSITORY ROOT (see docker-compose.yml), matching the
# backend Dockerfile, so both images are built with one shared context.
#
# Stage 1  deps    : install dependencies from the lockfile (npm ci)
# Stage 2  builder : `next build` with production settings
# Stage 3  runner  : standalone server, non-root user, no toolchain
#
# Only NEXT_PUBLIC_* values are baked in at build time; every server-side
# secret is supplied at runtime through the environment. No .env file is ever
# copied into the image (the .dockerignore below enforces this).
# ---------------------------------------------------------------------------

# ---------- Stage 1: dependencies ----------
FROM node:22-alpine AS deps
WORKDIR /app
RUN apk add --no-cache libc6-compat
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# ---------- Stage 2: build ----------
FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# NEXT_PUBLIC_API_URL is public by definition (it ships to the browser).
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
COPY --from=deps /app/node_modules ./node_modules
COPY frontend/ ./
RUN npm run build

# ---------- Stage 3: runtime ----------
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN apk add --no-cache curl \
    && addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# `output: "standalone"` emits a minimal server plus only the traced deps.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3000

# Liveness only; readiness is the backend's /ready endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:3000/ >/dev/null || exit 1

CMD ["node", "server.js"]
