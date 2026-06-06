# Architecture

IntelliDocs AI is currently a Phase 2 production-style portfolio implementation.

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
  -> marks document completed or failed
```

`GET /documents/{document_id}/status` exposes document status plus processing
steps. This is intentionally simpler than Celery; durable fan-out is a Phase 3
concern.

## Query

```text
POST /qa
  -> retrieve candidates
  -> rerank candidates
  -> generate answer with <cite index="...">
  -> backend validates citation indexes
  -> return real source metadata and run metrics
```

The citation mapper is the trust boundary. LLMs never provide document IDs,
chunk IDs, filenames, or page numbers directly.

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
the current process. **Durable document state is a Phase 3 concern** — this is a
deliberate scope line, not an oversight.

Vector choices (configurable via `POSTGRES_VECTOR_*`):

- embedding dimension: `1536` (default; must match the embedding model)
- distance metric: cosine, operator class `vector_cosine_ops`, index type `hnsw`

The schema is created by the Alembic migration (canonical for managed deploys)
and self-created by `/ready` or `PgVectorStore` on first use (turnkey local demo); both
define the same single `document_chunks` table with a `vector(N)` column and a
matching HNSW index. Changing the embedding model's dimension requires a new
migration.
