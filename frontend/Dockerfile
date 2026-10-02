# Installs only the `frontend` dependency group from uv.lock (Streamlit and
# requests); the backend stack is not needed in this image.
FROM ghcr.io/astral-sh/uv:0.11.14 AS uv

FROM python:3.13.14-slim

COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-install-project --no-default-groups --only-group frontend

COPY frontend /app/frontend

ENV INTELLIDOCS_API_URL=http://backend:8000
EXPOSE 8501

CMD ["streamlit", "run", "frontend/streamlit_app.py", "--server.address", "0.0.0.0", "--server.port", "8501"]
