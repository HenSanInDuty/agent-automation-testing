FROM node:22-alpine

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/dashboard/package.json ./apps/dashboard/package.json
COPY workers/playwright/package.json ./workers/playwright/package.json
COPY apps/dashboard ./apps/dashboard
RUN pnpm install --frozen-lockfile

ARG NEXT_PUBLIC_CONTROL_PLANE_URL=
ARG CONTROL_PLANE_INTERNAL_URL=http://control-plane:7000
ENV NEXT_PUBLIC_CONTROL_PLANE_URL=${NEXT_PUBLIC_CONTROL_PLANE_URL} \
    CONTROL_PLANE_INTERNAL_URL=${CONTROL_PLANE_INTERNAL_URL} \
    NODE_ENV=production

RUN pnpm --filter @auto-at/dashboard build

WORKDIR /app/apps/dashboard

ENV HOSTNAME=0.0.0.0 \
    PORT=3000

EXPOSE 3000

CMD ["pnpm", "start"]
