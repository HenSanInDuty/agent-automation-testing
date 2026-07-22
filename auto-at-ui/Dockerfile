FROM ghcr.io/astral-sh/uv:0.6.5 AS uv

FROM python:3.12-slim

WORKDIR /app

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONPATH=/app/apps/control-plane:/app/packages/contracts/src

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY apps/control-plane ./apps/control-plane
COPY packages/contracts ./packages/contracts
COPY alembic.ini ./
COPY migrations ./migrations
COPY docker-entrypoint.sh ./
RUN chmod 755 /app/docker-entrypoint.sh

EXPOSE 7000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uv", "run", "--no-sync", "uvicorn", "main:app", "--app-dir", "apps/control-plane", "--host", "0.0.0.0", "--port", "7000"]
