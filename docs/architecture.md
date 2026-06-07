# Architecture

IntelliDocs AI is currently a Phase 3 production-style portfolio implementation.

## Ingestion

```text
POST /documents/upload
  -> returns 202 with document_id and task_id
  -> in-process worker parses the file
  -> applies basic privacy variants
  -> chunks text
  -> extracts typed fields
  -> summarises
  -> embeds chunks
  -> updates branch-level status
  -> marks document completed or failed
```

`GET /documents/{document_id}/status` exposes document status plus processing
steps and branch statuses. Docker Compose includes Redis and a Celery worker
service; the default API path stays in-process for demo reliability, while
`worker/tasks.py` documents the chord header, branch and errback contracts.
The API does not currently dispatch a real Celery group/chord because document
metadata and status are still process-local. Making Celery the default path
requires durable document metadata/status first.

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

`POST /qa/stream` is Streamlit-compatible NDJSON status-then-final streaming. It
emits status events first and only streams the final verified answer after
citation mapping and support checking. It intentionally does not stream answer
tokens before verification.

## Storage

The default local development path is fully in-memory. Phase 2 adds an opt-in
PostgreSQL/pgvector path (`VECTOR_STORE_BACKEND=postgres`) that persists **only
the retrieval slice** — chunks and embeddings:

- `backend/app/rag/vector_store.py` (`PgVectorStore`)
- `backend/app/storage/database.py` (readiness checks)
- `backend/app/storage/models.py` (`ChunkRecord` for Alembic autogenerate)
- `migrations/versions/0001_phase2_pgvector.py`

Document-level metadata (summary, extracted fields, status, processing steps)
remains in the in-memory `DocumentService`. So in Postgres mode, chunks survive a
restart and `/qa` still answers, but `GET /documents/{id}` is only populated for
the current process. Full durable document metadata remains a future production
hardening item.

Vector choices (configurable via `POSTGRES_VECTOR_*`):

- embedding dimension: `1536` (default; must match the embedding model)
- distance metric: cosine, operator class `vector_cosine_ops`, index type `hnsw`

The schema is created by the Alembic migration (canonical for managed deploys)
and self-created by `/ready` or `PgVectorStore` on first use (turnkey local demo); both
define the same single `document_chunks` table with a `vector(N)` column and a
matching HNSW index. Changing the embedding model's dimension requires a new
migration.
