# Offline evaluation image: contains no Codex executable or host credentials.
FROM ghcr.io/astral-sh/uv:0.6.5@sha256:562193a4a9d398f8aedddcb223e583da394ee735de36b5815f8f1d22cb49be15 AS uv
FROM mcr.microsoft.com/playwright:v1.50.1-noble@sha256:ac7053180325ef75d31774c458d0bb9b55ac153ae1be3d104b80c6c1bb6a067c
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV UV_LINK_MODE=copy UV_NO_CACHE=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/app/apps/control-plane:/app/packages/contracts/src \
    AWS_EC2_METADATA_DISABLED=true
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --python 3.12
COPY workers/playwright/package.json workers/playwright/package.json
RUN cd workers/playwright && npm install --ignore-scripts --no-audit --no-fund
COPY apps/control-plane apps/control-plane
COPY apps/dashboard/app apps/dashboard/app
COPY workers/playwright/src workers/playwright/src
COPY workers/playwright/tsconfig.json workers/playwright/tsconfig.json
COPY packages/contracts packages/contracts
COPY tests tests
COPY migrations migrations
COPY benchmark benchmark
COPY benchmarks benchmarks
COPY scripts scripts
COPY observability observability
COPY docker/codex-bridge docker/codex-bridge
COPY docs docs
COPY alembic.ini docker-compose.yml docker-compose.codex.yml .env.example ./
RUN mkdir -p /app/benchmarks/exports && chown -R pwuser:pwuser /app/benchmarks/exports \
    && test ! -e /usr/local/bin/codex && touch /offline-evaluation
USER pwuser
ENTRYPOINT ["uv", "run", "--no-sync", "python", "benchmark/vision/codex/offline_suite.py"]
