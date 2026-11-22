# Local `claude -p` proposal bridge. Same hardening as docker/codex-bridge.
FROM node:22-slim AS claude
RUN npm install --global @anthropic-ai/claude-code@2.1.328 \
    && cp "$(npm root --global)/@anthropic-ai/claude-code/bin/claude.exe" /claude \
    && DISABLE_AUTOUPDATER=1 /claude --version

FROM ghcr.io/astral-sh/uv:0.6.5@sha256:562193a4a9d398f8aedddcb223e583da394ee735de36b5815f8f1d22cb49be15 AS uv
FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
COPY --from=uv /uv /uvx /bin/
COPY --from=claude /claude /usr/local/bin/claude
RUN useradd --uid 1000 --create-home --home-dir /bridge-home bridge \
    && mkdir -p /codex-jobs /bridge-secrets \
    && chown -R bridge:bridge /bridge-home /codex-jobs
WORKDIR /app
ENV UV_LINK_MODE=copy UV_NO_CACHE=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/apps/control-plane:/app/packages/contracts/src \
    HOME=/bridge-home DISABLE_AUTOUPDATER=1
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen
COPY apps/control-plane ./apps/control-plane
COPY packages/contracts ./packages/contracts
USER bridge
RUN claude --version
ENTRYPOINT ["claude"]
CMD ["--version"]
