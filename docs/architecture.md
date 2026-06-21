# Architecture

IntelliDocs AI has completed the Phase 5 production-style portfolio demo scope.

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

`GET /documents/{document_id}/status` exposes document status, processing
backend, task ID, processing steps and branch statuses. The default API path
stays `thread` for demo reliability, while
`DOCUMENT_PROCESSING_BACKEND=celery` enables real Celery dispatch. In Celery
mode the API queues a canvas using a storage key, not raw file bytes:

```text
seed document from storage key
  -> parse/privacy/chunk
  -> chord(embedding, extraction, summarisation)
  -> aggregate document completion
```

`DELETE /documents/{document_id}` removes a terminal document from durable
state, cascades its chunks/vectors and deletes any remaining upload blob. Active
processing returns `409` so deletion cannot race an in-flight thread or Celery
task.

The Streamlit UI maintains a session-scoped workspace of at most 10 documents.
Every UI Q&A request includes the completed workspace document IDs, preventing
retrieval from unrelated database documents. Removing a document calls the
DELETE endpoint before removing it from session state.

Branch tasks persist their outputs/status in Postgres and return only small
metadata through Redis. The aggregate task performs the single final document
write.

Celery tasks use native soft and hard time limits. The synchronous thread
fallback keeps its local parser timeout, but the distributed worker path also
has Celery-level protection against stuck parser or provider calls.

## Container Workflow

Docker Compose is the primary runtime target for the project. The stack includes:

- `postgres`: PostgreSQL with pgvector.
- `redis`: broker/result backend for Celery.
- `backend`: FastAPI app, health-checked through `/ready`.
- `worker`: Celery worker using the same backend image.
- `frontend`: Streamlit UI built as its own image.
- `tests`: profile-gated test runner using the same backend image.
- `live-tests`: profile-gated HTTP client for the strict provider smoke, built
  from the same backend image but without receiving the provider key.

The backend image copies application code, worker code, prompts, sample data,
scripts, Alembic migrations and `alembic.ini`, so tests, evaluation and migration
checks can run inside containers. The `tests` service intentionally does not
load `.env`; it forces offline deterministic settings so real API keys and host
configuration cannot affect the test suite.

The isolated live-test target is the explicit exception to offline verification:
the backend loads `.env`, forces `ENABLE_LLM=true` plus strict provider mode and
runs against a fresh Postgres volume. The key is not passed to the live-test
client, which calls the real FastAPI upload/status/document/Q&A endpoints. Each
embedding mode gets a separate Compose project so incompatible vector spaces
cannot mix. It is opt-in because it incurs cost and depends on external provider
availability.

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

The LLM-backed path is the primary product path for answer quality. The offline
lexical answerer exists so CI, tests and key-less demos are deterministic; its
known false-positive mode is reported in the evaluation instead of hidden.

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

Vector choices:

- embedding dimension: `1536` (default; must match the embedding model)
- distance metric: cosine, operator class `vector_cosine_ops`, index type `hnsw`

Cosine is the only implemented pgvector metric. Supporting L2/IP would require
changing the SQL operator, operator class and tests together.

The schema is created by Alembic migrations (canonical for managed deploys) and
self-created by `/ready`, the repository, or `PgVectorStore` on first use
(turnkey local demo). Runtime schema creation is serialized with a Postgres
advisory lock so concurrent Celery branches do not deadlock during self-create.
The migrations use `IF NOT EXISTS` for the runtime-created objects, so running
Alembic later against a Docker demo database does not fail on already-existing
tables or indexes.
Readiness verifies the vector column dimension plus the embedding index method
and operator class, because `CREATE INDEX IF NOT EXISTS` will not replace a
stale index with the same name. Changing the embedding model's dimension or the
pgvector index/operator configuration requires a new migration.

`make alembic-sql` verifies offline migration rendering only.
`make alembic-integration-test` uses a unique temporary Docker Compose project
to apply `alembic upgrade head` to a fresh PostgreSQL/pgvector database and
validate the revision, tables, required document columns, vector dimension,
HNSW cosine index and chunk foreign key. Its containers, image, network and
volume are removed on exit, so it does not mutate the normal demo database.

`make celery-integration-test` follows the same isolation rule. It uses a unique
Compose project, fresh database/upload volumes and random host ports; verifies
the successful fan-out path and a durable worker failure; restarts the backend
and confirms completed document state remains readable; then removes temporary
containers, images, networks and volumes. Service logs are emitted before
cleanup when the gate fails.

Postgres access goes through a bounded per-process psycopg connection pool,
configured with `DATABASE_POOL_MIN_SIZE`, `DATABASE_POOL_MAX_SIZE` and
`DATABASE_POOL_TIMEOUT_SECONDS`. This keeps the backend and Celery branches from
opening a new database connection for every repository/vector-store operation.

Privacy text persistence is intentionally scoped. The current privacy policy
redacts high-risk identifiers, stores `ai_text` on the document row for Celery
branches/retry, and stores display-safe chunk text in `document_chunks.text` for
retrieval snippets and citations. The raw upload blob is transient local storage
and is removed after successful processing.

The runtime schema helper and Alembic migrations intentionally duplicate the
small amount of DDL needed for the Docker demo path. Do not make Alembic import
runtime application code; instead keep the duplication constrained to storage
schema creation and verify both paths when changing durable state.

## Observability

The project uses lightweight production-style observability rather than a full
telemetry platform. Standard application logs go to stdout/stderr with timestamp,
level, logger name and message so Docker, VPS or cloud log collection can pick
them up.

Q&A emits structured JSON run events through the `intellidocs.run` logger for
run metrics and failures. The API response also returns run metrics including
latency, candidate/context counts, citation count, model name, token usage
source, estimated cost availability/value, reranker status and support-check
result.

Document ingestion progress is primarily observed through
`GET /documents/{document_id}/status`, which exposes the document status,
sequential processing steps, branch statuses, branch errors, backend and task
ID. `/ready` reports configuration, database, pgvector and Celery connectivity
checks for Docker/runtime diagnostics.

Raw document text, prompts and uploaded file content are not logged. Optional
observability exporters such as OpenTelemetry, Prometheus, Langfuse or Phoenix
are not integrated in this portfolio scope.
