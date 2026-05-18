FROM node:20-alpine AS base

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Install dependencies (workspace-aware)
# ─────────────────────────────────────────────────────────────────────────────
FROM base AS deps
WORKDIR /repo

# Copy root workspace manifests
COPY package.json package-lock.json ./

# Copy each app/package manifest so npm ci resolves workspace deps
COPY apps/admin-app/package.json ./apps/admin-app/
COPY apps/user-app/package.json ./apps/user-app/
COPY packages/shared/package.json ./packages/shared/

RUN npm ci

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 (dev): Hot-reload dev server — docker-compose uses this target
# ─────────────────────────────────────────────────────────────────────────────
FROM base AS dev
WORKDIR /repo/apps/admin-app

COPY --from=deps /repo/node_modules /repo/node_modules
COPY . /repo

EXPOSE 3001
ENV PORT=3001
ENV HOSTNAME="0.0.0.0"
ENV WATCHPACK_POLLING=true

CMD ["npm", "run", "dev"]

# ─────────────────────────────────────────────────────────────────────────────
# Stage 3: Build the application
# ─────────────────────────────────────────────────────────────────────────────
FROM base AS builder
WORKDIR /repo/apps/admin-app

COPY --from=deps /repo/node_modules /repo/node_modules
COPY . /repo

RUN npm run build

# ─────────────────────────────────────────────────────────────────────────────
# Stage 4: Production runner
# ─────────────────────────────────────────────────────────────────────────────
FROM base AS runner
WORKDIR /repo/apps/admin-app

ENV NODE_ENV=production

COPY --from=builder /repo/apps/admin-app/.next/standalone ./
COPY --from=builder /repo/apps/admin-app/.next/static ./.next/static
COPY --from=builder /repo/apps/admin-app/public ./public

EXPOSE 3001
ENV PORT=3001
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
