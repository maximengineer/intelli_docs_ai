# Dependencies come from uv.lock (the single source of truth), not a hand-kept
# requirements file. Targets:
#   runtime - backend API, Celery worker and live-smoke client (no test tools)
#   test    - runtime + the dev group (pytest) for the offline test service
FROM ghcr.io/astral-sh/uv:0.11.14 AS uv

FROM python:3.13.14-slim AS runtime

COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-install-project --no-default-groups

COPY backend /app/backend
COPY worker /app/worker
COPY prompts /app/prompts
COPY data /app/data
COPY scripts /app/scripts
COPY migrations /app/migrations
COPY alembic.ini /app/alembic.ini

ENV PYTHONPATH=/app:/app/backend
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS test
RUN uv sync --frozen --no-install-project --no-default-groups --group dev
