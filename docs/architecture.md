# Architecture

IntelliDocs AI is currently a Phase 5 in-progress production-style portfolio
implementation.

## Ingestion

```text
POST /documents/upload
  -> returns 202 with document_id and task_id
  -> stores upload bytes in a shared local upload store
  -> thread worker or Celery worker parses the file
  -> applies basic privacy variants
  -> chunks text
  -> extracts typed fields
  -> summarises
  -> embeds chunks
  -> updates branch-level status
  -> marks document completed or failed
```

`GET /documents/{document_id}/status` exposes document status plus processing
steps and branch statuses. The default API path stays `thread` for demo
reliability, while `DOCUMENT_PROCESSING_BACKEND=celery` enables real Celery
dispatch. In Celery mode the API queues a canvas using a storage key, not raw
file bytes:

```text
seed document from storage key
  -> parse/privacy/chunk
  -> chord(embedding, extraction, summarisation)
  -> aggregate document completion
```

Branch tasks persist their outputs/status in Postgres and return only small
metadata through Redis. The aggregate task performs the single final document
write.

## Container Workflow

Docker Compose is the primary runtime target for the project. The stack includes:

- `postgres`: PostgreSQL with pgvector.
- `redis`: broker/result backend for Celery.
- `backend`: FastAPI app, health-checked through `/ready`.
- `worker`: Celery worker using the same backend image.
- `frontend`: Streamlit UI built as its own image.
- `tests`: profile-gated test runner using the same backend image.
- `live-tests`: profile-gated provider smoke test using `.env` and the same
  backend image.

The backend image copies application code, worker code, prompts, sample data,
scripts, Alembic migrations and `alembic.ini`, so tests, evaluation and migration
checks can run inside containers. The `tests` service intentionally does not
load `.env`; it forces offline deterministic settings so real API keys and host
configuration cannot affect the test suite.

`live-tests` is the explicit exception: it loads `.env`, forces
`ENABLE_LLM=true`, and runs a small provider-backed smoke test. It is opt-in
because it may incur cost and depends on external provider availability.

## Query

```text
POST /qa
  -> retrieve candidates
  -> rerank candidates
  -> generate answer with <cite index="...">
  -> backend validates citation indexes
  -> support-check gate: citation integrity + lexical grounding overlap
  -> return real source metadata and run metrics
```

The support-check gate has two deterministic layers: citation integrity (cited
chunk IDs must belong to retrieved context) and grounding (the answer must share
content tokens with the chunk text it cites, so an answer that cites context it
did not use is rejected). It is lexical, not semantic entailment.

`POST /evaluation/run` starts a forced-offline evaluation asynchronously and
returns an `evaluation_id`; poll `GET /evaluation/{evaluation_id}` for the
result. It never makes paid LLM calls regardless of `.env`.

The citation mapper is the trust boundary. LLMs never provide document IDs,
chunk IDs, filenames, or page numbers directly.

`POST /qa/stream` is Streamlit-compatible NDJSON status-then-final streaming.
The status events are generic progress markers for the verified-answer contract;
the backend only streams the final answer after retrieval, citation mapping and
support checking. It intentionally does not stream answer tokens before
verification.

## Storage

The default local test path is fully in-memory. Docker runs with
`VECTOR_STORE_BACKEND=postgres`, which now enables durable document state as
well as pgvector retrieval:

- `backend/app/rag/vector_store.py` (`PgVectorStore`)
- `backend/app/storage/database.py` (readiness + runtime schema self-create)
- `backend/app/storage/repositories.py` (in-memory and Postgres document stores)
- `backend/app/storage/upload_store.py` (shared local upload blobs)
- `backend/app/storage/models.py` (SQLAlchemy records for Alembic)
- `migrations/versions/0001_phase2_pgvector.py`
- `migrations/versions/0002_phase4_document_state.py`

Durable Postgres state includes documents, extracted fields, summaries,
processing steps, branch statuses, chunks, embeddings and evaluation runs.
`GET /documents/{id}` and `GET /documents/{id}/status` read from the repository
on every call in Postgres mode, so backend reads see writes made by a separate
Celery worker process.

Vector choices (configurable via `POSTGRES_VECTOR_*`):

- embedding dimension: `1536` (default; must match the embedding model)
- distance metric: cosine, operator class `vector_cosine_ops`, index type `hnsw`

The schema is created by Alembic migrations (canonical for managed deploys) and
self-created by `/ready`, the repository, or `PgVectorStore` on first use
(turnkey local demo). Runtime schema creation is serialized with a Postgres
advisory lock so concurrent Celery branches do not deadlock during self-create.
The migrations use `IF NOT EXISTS` for the runtime-created objects, so running
Alembic later against a Docker demo database does not fail on already-existing
tables or indexes.
Changing the embedding model's dimension requires a new migration.

The runtime schema helper and Alembic migrations intentionally duplicate the
small amount of DDL needed for the Docker demo path. Do not make Alembic import
runtime application code; instead keep the duplication constrained to storage
schema creation and verify both paths when changing durable state.
