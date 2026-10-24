FROM node:22-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 AS codex
RUN npm install --global @openai/codex@0.164.0 \
    && codex --version

FROM ghcr.io/astral-sh/uv:0.6.5@sha256:562193a4a9d398f8aedddcb223e583da394ee735de36b5815f8f1d22cb49be15 AS uv
FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
COPY --from=uv /uv /uvx /bin/
COPY --from=codex /usr/local/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/ /usr/local/bin/
RUN useradd --uid 1000 --create-home --home-dir /bridge-home bridge \
    && mkdir -p /job /bridge-home/.codex /outside /codex-jobs \
    && chown -R bridge:bridge /job /bridge-home /outside /codex-jobs
WORKDIR /app
ENV UV_LINK_MODE=copy UV_NO_CACHE=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/apps/control-plane:/app/packages/contracts/src \
    HOME=/bridge-home CODEX_HOME=/bridge-home/.codex
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen
COPY --from=codex /usr/local/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/codex-resources /usr/local/codex-resources
COPY apps/control-plane ./apps/control-plane
COPY packages/contracts ./packages/contracts
RUN uv run --no-sync python -m infrastructure.codex_bridge.catalogue
COPY tests ./tests
COPY docker/codex-bridge/fixtures/allowed.txt /job/allowed.txt
COPY docker/codex-bridge/fixtures/sentinel.txt /outside/sentinel.txt
USER bridge
WORKDIR /job
ENTRYPOINT ["codex"]
CMD ["--version"]
