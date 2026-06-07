FROM python:3.13-slim

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

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
