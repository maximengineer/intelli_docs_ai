# IntelliDocs AI — Implementation Guide

Version: pragmatic implementation plan

## 1. Goal

This guide explains how to implement IntelliDocs AI without over-scoping it.

The implementation strategy is:

1. Build a thin vertical slice first.
2. Make it demoable.
3. Add senior engineering features only after the product works.
4. Keep the architecture honest and explainable.

## 2. Implementation Philosophy

Prefer:

- working product over perfect architecture
- small vertical slice over incomplete platform
- deterministic citation mapping over flashy agent logic
- simple evaluation over fake metrics
- clear README over hidden complexity

Avoid:

- overbuilding infrastructure before RAG works
- making every production-style feature mandatory
- adding frameworks without need
- claiming enterprise readiness

## 3. Phased Implementation

## Phase 1: Working AI Product

### Goal

A reviewer can upload a document, see extracted information, ask questions and receive cited answers.

### Features

- FastAPI backend
- Streamlit UI
- document upload
- TXT, DOCX and digital-native PDF parsing
- document summary
- key field extraction
- document chunking
- embeddings
- vector search
- RAG Q&A
- deterministic citation mapping
- insufficient-information fallback
- basic evaluation script
- Docker Compose
- README

### Phase 1 Repository Structure

```text
intellidocs-ai/
  README.md
  CLAUDE.md
  docker-compose.yml
  .env.example

  backend/
    app/
      main.py

      api/
        routes_health.py
        routes_documents.py
        routes_qa.py

      core/
        settings.py
        logging.py
        errors.py

      documents/
        parser.py
        chunker.py
        extractor.py
        summarizer.py
        schemas.py
        service.py

      rag/
        embeddings.py
        vector_store.py
        retriever.py
        generator.py
        citations.py
        service.py
        schemas.py

      llm/
        client.py
        prompt_registry.py
        schemas.py

      evaluation/
        datasets.py
        retrieval_eval.py
        extraction_eval.py
        report.py

    tests/
      test_parser.py
      test_chunker.py
      test_extractor.py
      test_citations.py
      test_api_qa.py

    requirements.txt
    Dockerfile

  frontend/
    streamlit_app.py

  prompts/
    extract_fields.yaml
    summarize_document.yaml
    answer_question.yaml

  data/
    sample_documents/
    evaluation/
      questions.jsonl
      expected_extractions.jsonl
      negative_questions.jsonl

  docs/
    demo_script.md
    limitations.md

  scripts/
    run_evaluation.py
    seed_database.py
```

This structure is intentionally smaller than the final architecture.

### Phase 1 — Implementation Notes (as built · 2026-06-06)

> Status: **complete and verified.** Full chronological record in `docs/dev_log.md`.

Built as planned, with these deviations and additions:

- **LLM behind an adapter** (OpenRouter, OpenAI-compatible). Generation,
  summarisation and extraction are LLM-backed, each with a deterministic offline
  fallback so tests, CI and a key-less demo still run. Extraction uses JSON mode +
  Pydantic validation (no regex JSON parsing). Prompt YAMLs are loaded via the
  prompt registry.
- **Embeddings default to `auto`**: OpenRouter embeddings when a key is present,
  otherwise the zero-dependency hash embedder. Local `sentence-transformers`
  remains the recommended real semantic offline path, but is explicit opt-in via
  `EMBEDDING_BACKEND=local` and the `local-embeddings` extra.
- **Vector search precomputes embeddings at upload** (in-memory store).
- **Citations**: the LLM picks `<cite index>` values; the backend validates them
  and maps to real metadata. Invalid/missing → insufficient-information fallback
  (the guide's `needs_review` option is deferred to Phase 2).
- **Status string is `completed`** (not the `processed` in the example below).
- **Adversarial eval**: 13 docs incl. keyword-sharing distractors/negatives.
  Offline backend: hit@5 1.0 · citation 1.0 · rejection **0.8** · extraction 1.0.
  The 0.8 is a genuine limitation of the lexical fallback, kept honest.
- **Tests**: 24 passing (LLM paths mocked; local-embeddings test gated on the
  optional extra). `ruff`-clean.
- **Pulled forward from Phase 2**: content-hash deduplication.

## Phase 2: Senior Engineering Proof

Add after Phase 1 works.

### Features

- asynchronous processing
- status endpoint
- PostgreSQL with pgvector
- Alembic migrations
- structured logs with `run_id`
- reranking
- basic privacy handling
- cost estimation from token usage
- file deduplication
- extraction confidence hard gates

### Additional Structure

```text
backend/app/api/routes_status.py
backend/app/documents/privacy.py
backend/app/documents/confidence.py
backend/app/rag/reranker.py
backend/app/rag/critic.py
backend/app/rag/cache.py
backend/app/observability/run_logger.py
backend/app/storage/database.py
backend/app/storage/models.py

migrations/
```

### Phase 2 — Implementation Notes

> Status: **implemented as senior engineering proof.**

Implemented:

- async upload contract: `POST /documents/upload` returns `202 Accepted` with
  `document_id` and `task_id`
- `GET /documents/{document_id}/status`
- `GET /ready`
- opt-in PostgreSQL/pgvector retrieval store for chunks + embeddings, with
  Alembic migration
- structured run metrics with `run_id`
- lexical reranking hook
- basic privacy variants (`raw_text`, `ai_text`, `display_text`)
- cost estimation from configured token price table
- content-hash deduplication
- extraction confidence hard gates and `needs_review`

Deviation: async processing uses an in-process worker, not a durable external
queue. Celery/Redis fan-out remains Phase 3.

Storage scope: Phase 2 persists the retrieval slice only. Document metadata,
status, summaries and extracted fields remain in-memory; durable document state
is Phase 3 scope.

Readiness fixes before Phase 3:

- Docker Compose forces `EMBEDDING_BACKEND=hash` for the no-key pgvector demo.
- Hash embeddings size themselves to `POSTGRES_VECTOR_DIMENSION` when
  `VECTOR_STORE_BACKEND=postgres`, so indexing does not fail the pgvector
  dimension guard.
- `/ready` creates and verifies the pgvector extension, `document_chunks` table,
  HNSW index and configured vector dimension in Postgres mode.
- Q&A metrics report `offline-heuristic` whenever no LLM client is actually
  active, even if `.env` requested a provider-backed model.

Verification gate:

- `ruff format --check .`: clean.
- `ruff check .`: clean.
- `ENABLE_LLM=false EMBEDDING_BACKEND=hash VECTOR_STORE_BACKEND=memory uv run pytest`:
  **35 passed, 1 skipped**.
- Offline eval: hit@5 1.0 · citation 1.0 · rejection 0.8 · extraction 1.0.
- `alembic upgrade head --sql`: emits `embedding vector(1536)` plus the HNSW
  cosine index.
- `docker compose config`: backend resolves `EMBEDDING_BACKEND=hash` and
  `VECTOR_STORE_BACKEND=postgres`.

## Phase 3: Production-Style Hardening

Add only if the project is already demoable.

### Features

- Celery + Redis
- Celery group/chord fan-out
- branch-level processing status
- Streamlit-compatible streaming Q&A
- support-check gate
- richer evaluation
- purpose-scoped privacy variants
- optional Langfuse/Phoenix
- AWS deployment notes

### Additional Structure

```text
worker/
  worker.py
  tasks.py

backend/app/api/routes_evaluation.py
scripts/generate_eval_dataset.py
docs/architecture.md
docs/privacy.md
docs/evaluation.md
```

### Phase 3 — Implementation Notes

> Status: **implemented as production-style hardening.**

Implemented:

- Redis service and Celery worker scaffold in Docker Compose.
- Celery task module with parse/chunk seed, branch task names, aggregate task and
  chord errback contract.
- Branch-level document status for embedding, extraction and summarisation.
- `POST /qa/stream` NDJSON endpoint for Streamlit-compatible verified streaming.
- Backend support-check gate after citation mapping with citation-integrity and
  lexical-grounding checks before final answers are returned or streamed.
- Async `POST /evaluation/run` plus `GET /evaluation/{evaluation_id}`; API
  evaluation is forced offline and returns richer metrics including
  support-check pass rate.
- Privacy variants (`raw`, `ai_text`, `display_text`) with policy version
  `phase3-purpose-v1`.
- AWS deployment notes and evaluation documentation.

Scope line: the API still defaults to the in-process upload path for demo
reliability. Redis/Celery wiring is present and runnable, but fully durable
cross-process document metadata/status remains future production hardening.

Critical review:

- Celery/Redis is currently infrastructure and task-contract scaffolding. The
  API does not dispatch a real Celery group/chord because document
  metadata/status are still process-local.
- `worker/tasks.py` should not become the default upload path until document
  metadata, status and extracted fields are persisted durably.
- Raw file bytes should not be passed through Redis for production async
  processing; store uploads durably and pass a storage key/document ID instead.
- `/qa/stream` is verified status-then-final streaming, not token streaming.
  That is intentional because unsupported answer tokens must not be streamed
  before citation/support verification.
- The support-check gate is citation-integrity plus lexical grounding, not a
  semantic entailment evaluator.
- Privacy variants are produced by the helper, but document-level metadata and
  variants are not persisted durably.
- `STREAMING_ENABLED` is wired for `/qa/stream`; optional observability exporters
  remain future work.
- `scripts/generate_eval_dataset.py` remains intentionally absent; evaluation
  data is small, synthetic and manually reviewed rather than generated as a
  golden dataset.
- Local worker imports require `PYTHONPATH=backend` outside Docker/pytest until
  the package layout is refactored.

Recommended fix order:

1. Persist document metadata/status and extraction outputs.
2. Store uploads durably and pass task-safe storage references through Celery.
3. Implement the real Celery canvas (`group`/`chord`) behind a feature flag.
4. Add semantic support checking only if it improves trust without making fake
   confidence claims.
5. Add Docker/Redis/Celery integration tests outside the default unit gate.

Verification gate:

- `ruff format --check .`: clean.
- `ruff check .`: clean.
- `ENABLE_LLM=false EMBEDDING_BACKEND=hash VECTOR_STORE_BACKEND=memory uv run pytest`:
  **42 passed, 1 skipped**.
- Offline eval: hit@5 1.0 · citation 1.0 · rejection 0.8 · support check 1.0 ·
  extraction 1.0.
- `docker compose config`: Redis and worker services resolve successfully.

## Docker-First Runtime And Testing

The project should be developed and verified primarily through Docker Compose.
Local `uv` commands remain useful for fast iteration, but they are secondary to
the containerized path because the real app uses multiple services: FastAPI,
Streamlit, PostgreSQL/pgvector, Redis and Celery.

### Compose Services

Required services:

- `postgres`: PostgreSQL with pgvector.
- `redis`: broker/result backend for Celery.
- `backend`: FastAPI app image.
- `worker`: Celery worker using the backend image.
- `frontend`: Streamlit app image.
- `tests`: profile-gated offline test runner using the backend image.
- `live-tests`: profile-gated provider/API-key smoke runner using the backend
  image.

### Docker Image Requirements

Backend image must include:

- backend application code
- worker package
- prompts
- sample/evaluation data
- scripts
- Alembic migrations
- `alembic.ini`

Frontend image must install Streamlit dependencies at build time, not on every
container start.

The Docker build context must exclude `.env`, virtualenvs, caches, ignored
planning files and local metadata through `.dockerignore`.

### Commands

Preferred Makefile wrappers:

```bash
make up
make down
make test
make eval
make alembic-sql
make live-test
make live-test-embeddings
```

Run `make help` for the full command list.

Underlying Compose commands:

Run the app stack:

```bash
docker compose up --build backend worker frontend
```

Default host ports are intentionally uncommon to avoid local conflicts:

- backend: `http://localhost:7777`
- frontend: `http://localhost:9999`

Use alternate host ports when defaults are already occupied:

```bash
BACKEND_PORT=18000 FRONTEND_PORT=18501 docker compose up --build backend worker frontend
```

Run deterministic offline tests:

```bash
docker compose --profile test run --rm tests
```

Run offline evaluation in the backend image:

```bash
docker compose --profile test run --rm tests python scripts/run_evaluation.py
```

Run Alembic SQL generation in the backend image:

```bash
docker compose --profile test run --rm tests alembic upgrade head --sql
```

Run live provider smoke testing:

```bash
docker compose --profile live-test run --rm live-tests
```

Require provider embeddings during the live smoke:

```bash
LIVE_EMBEDDING_BACKEND=openrouter LIVE_REQUIRE_PROVIDER_EMBEDDINGS=true \
  docker compose --profile live-test run --rm live-tests
```

### Testing Policy

- `tests` must not load `.env`.
- `tests` must force deterministic settings:
  - `ENABLE_LLM=false`
  - `EMBEDDING_BACKEND=hash`
  - `VECTOR_STORE_BACKEND=memory`
- `live-tests` may load `.env` and use real API keys.
- `live-tests` should stay small and focused because it can incur provider cost.
- Do not claim provider-backed behavior is verified unless `live-tests` has
  actually been run.
- Do not claim Redis/Celery/Postgres integration is verified unless the
  containerized service path has actually been run.

### Verified Container Commands

Latest verified commands:

- `make help`, `make config`, `make config-all`: completed after adding the
  Makefile and Docker profiles.
- `docker compose --profile test run --rm tests`: **42 passed, 1 skipped**.
- `docker compose --profile test run --rm tests python scripts/run_evaluation.py`:
  completed on the synthetic dataset.
- `docker compose --profile test run --rm tests alembic upgrade head --sql`:
  emitted the pgvector schema.
- `BACKEND_PORT=18000 FRONTEND_PORT=18501 docker compose up -d --build backend worker frontend`:
  backend, worker, frontend, Postgres and Redis started successfully.
- Backend `/health` and `/ready` passed in-container.
- Celery worker responded to `inspect ping`.
- Streamlit frontend returned HTTP 200 on the host-published port.
- The full app stack has not yet been re-run on the new default host ports
  `7777` and `9999`; run `make up` before claiming that path verified.

## Phase 4: Durable Async Workflow

Add only after Phase 3 remains demo-ready and the codebase is clean.

### Goal

Turn Phase 3's async scaffolding into a real durable processing workflow.

Phase 3 intentionally keeps document metadata/status in process memory while
adding Redis/Celery wiring and branch-status contracts. Phase 4 should close
that gap before adding observability, human review, semantic cache or richer
external evaluation frameworks.

Phase 4 may reintroduce repository/model code that was deliberately removed in
the Phase 2 review. That is not a contradiction: it was dead code before durable
document state existed, and becomes justified only when document metadata,
status and extracted fields are actually persisted and read at runtime.

### Architecture Decisions (binding)

These resolve ambiguities found in review. Treat them as decided, not optional.

1. **Durability and execution are independent axes — do not couple them.**
   - *Durability* is controlled by `VECTOR_STORE_BACKEND=postgres` + `DATABASE_URL`.
     In `memory` mode document state stays in-process (the hermetic default/test path).
   - *Execution* is controlled by `DOCUMENT_PROCESSING_BACKEND=thread|celery`.
   - The first, fully verifiable milestone is **thread + postgres** (durable state,
     no Celery). `celery` is added only after that works, and `celery` mode
     **requires** postgres durability (reject/auto-correct `celery` + `memory`).

2. **Document state goes through a `DocumentRepository` abstraction.**
   - One interface, two implementations: in-memory (current behaviour, used by
     `memory` mode and the fast tests) and postgres. Select it from the existing
     `VECTOR_STORE_BACKEND` — do **not** add a third storage-backend setting.
     `DocumentService` depends on the interface, not on dicts.
   - This deliberately couples document-state durability to the vector-store
     backend. Centralize that coupling in settings or repository construction
     (for example, a derived `durable_document_state_enabled` helper) so the
     rest of the code does not scatter `VECTOR_STORE_BACKEND == "postgres"`
     checks.

3. **In postgres mode, reads hit the repository — never a stale local cache.**
   - The current `_documents`/`_statuses`/`_chunks` dicts become *only* the
     in-memory repository implementation. In postgres mode `get`, `get_status`
     and search read from the database every call, so the API process sees writes
     made by a separate Celery worker. A write-through dict cache in postgres mode
     is a bug (it goes stale cross-process).

4. **New tables are created the same way `document_chunks` already is.**
   - Extend the runtime self-create (the `ensure_*_schema` path used by `/ready`
     and the stores) to also create `documents`, `processing_steps`,
     `document_branches` and `evaluation_runs`. Alembic `0002` stays the canonical
     schema for managed deploys. The backend container does **not** run
     `alembic upgrade` on startup, so self-create is what makes the Docker demo
     work — keep the two definitions in sync (same columns/indexes).
   - Runtime self-create must also handle existing Docker volumes created by
     earlier phases. Do not rely only on `CREATE TABLE IF NOT EXISTS`; add safe
     `ALTER TABLE`/constraint checks for stale schemas or make `/ready` fail
     loudly with a clear schema-migration error.

5. **`documents` ↔ `document_chunks` relationship.**
   - Re-add the `document_chunks.document_id` → `documents.document_id` foreign key
     with `ON DELETE CASCADE`. Write ordering: the seed inserts the `documents`
     row (status `parsing`) before any chunk. `remove(document_id)` deletes the
     document row and lets the cascade drop chunks.
   - Deletion ownership belongs to `DocumentRepository`/`DocumentService`.
     `PgVectorStore.remove()` must not remain an independent public delete path
     that deletes chunks directly in postgres mode; either delegate document
     deletion to the repository or make chunk-only deletion private/internal.

6. **Concurrent fan-out writes are isolated.**
   - Branch tasks update only their own per-branch status row and return only
     small metadata/result IDs through Redis. Avoid pushing large summaries,
     extracted JSON, raw text or sensitive content through the Celery result
     backend. The **aggregate** task performs the single atomic write of
     `summary`, `extracted_fields`, `extraction_confidence`, `needs_review` and
     the terminal `completed`/`failed` status. Branches never write shared
     document columns concurrently (no last-write-wins races).

7. **Idempotency.** `task_acks_late=True` is already set, so tasks may be
   redelivered. Every write must be idempotent: chunk upserts (already), document
   upserts keyed by `document_id`, per-branch status upserts, and a re-runnable
   aggregate.
   - Upload blob deletion must respect this. Do not delete the stored blob until
     the aggregate has reached a terminal state, or until enough parsed/chunked
     state is durably persisted for every retry path to resume without the
     original bytes.

8. **Testing boundary.** The fast gate remains hermetic and must not require
   Postgres, Redis, Celery or a live provider. It should cover the repository
   contract through the in-memory implementation, upload-store behavior and
   processing-backend selection. Postgres repository SQL, runtime schema
   self-create/evolution and the Celery canvas are exercised by Docker integration
   tests. Phase 4 is not complete until that Docker path has been run, even if
   those tests remain outside the default fast gate.

### Required Features

- Persist document metadata:
  - document ID
  - filename
  - content hash
  - lifecycle status
  - created/updated timestamps
  - summary
  - document type
  - extraction confidence
  - needs-review flag
  - privacy policy version
  - processing error
- Persist extracted fields as structured JSON or typed columns.
- Persist processing steps and branch statuses.
- Add durable upload storage:
  - local filesystem storage for the Docker/local demo, under a configured uploads dir
  - storage key **derived from the content hash**, so identical re-uploads dedupe
    to one blob and one `document_id` (consistent with existing content-hash dedup)
  - no raw file bytes in Redis task payloads — pass only the storage key /
    `document_id`, and keep Celery return values small
  - retention: keep the blob until aggregate completion or until all retry paths
    can resume from durable parsed/chunked state; after that it may be deleted
    because reads use persisted chunks + metadata; parser temp files are still
    cleaned up as today
- Add a processing backend switch:

```text
DOCUMENT_PROCESSING_BACKEND=thread|celery
```

- Keep `thread` as the safe default until Celery path is verified.
- Implement real Celery dispatch behind the feature flag.
- Use a task-safe Celery canvas:

```text
seed document from storage key
  -> parse/privacy/chunk
  -> chord(
       embedding branch,
       extraction branch,
       summarisation branch
     )
  -> aggregate document completion
```

- Update branch statuses from worker tasks.
- Persist evaluation runs:
  - evaluation ID
  - status
  - started/completed timestamps
  - result JSON
  - error
- Add optional integration test target for Postgres + Redis + Celery.
- Clean up worker imports so local commands do not require fragile
  `PYTHONPATH=backend` setup.

Verification boundary: the fast local gate should stay hermetic and not require
Postgres, Redis or a live Celery worker. Full cross-process behavior belongs in
optional Docker integration tests, and should not be claimed as verified unless
those tests have actually been run.

### Non-Goals

Do not use Phase 4 for:

- authentication or multi-tenant access control
- enterprise security/compliance claims
- Langfuse/Phoenix
- semantic cache
- human review UI
- RAGAS/DeepEval scoring
- AWS automation beyond existing deployment notes

Those are later add-ons only if the durable workflow is stable.

### Additional Structure

```text
backend/app/storage/
  models.py          # re-add DocumentRecord, ProcessingStepRecord,
                     # DocumentBranchRecord, EvaluationRunRecord (alongside ChunkRecord)
  repositories.py    # DocumentRepository interface + in-memory + postgres impls
  upload_store.py

backend/app/documents/
  processing_backend.py

migrations/versions/
  0002_phase4_document_state.py

backend/tests/
  test_phase4_document_state.py
  test_phase4_upload_store.py
  test_phase4_processing_backend.py
```

Optional integration tests:

```text
backend/tests/integration/
  test_celery_document_processing.py
```

### Recommended Implementation Order

1. Add SQLAlchemy models, Alembic `0002`, and matching runtime self-create/schema
   evolution for `documents`, `processing_steps`, `document_branches`,
   `evaluation_runs`; re-add the `document_chunks` → `documents` FK (cascade).
2. Add a `DocumentRepository` interface with in-memory and postgres
   implementations, selected by `VECTOR_STORE_BACKEND`.
3. Make `DocumentService` depend on the repository; in postgres mode read straight
   from it (no stale local cache), keeping the current thread worker path.
4. **Verify the thread + postgres milestone in Docker**: upload through the API,
   restart the backend container, read the document/status back from Postgres.
5. Add durable upload storage (content-hash key) and replace `content_hex` task
   payloads with storage keys.
6. Add `DOCUMENT_PROCESSING_BACKEND=thread|celery` (thread default; `celery`
   requires postgres).
7. Wire real Celery dispatch behind the flag: `chain(seed -> chord(branches) ->
   aggregate)`; branches update only their branch row, the aggregate writes the
   document fields once.
8. Persist evaluation runs (lowest priority — the eval is a dev tool).
9. Add focused unit tests (repository contract through in-memory implementation,
   upload store, processing-backend selection).
10. Add Docker/Redis/Celery/Postgres integration tests for postgres repository
    SQL, schema self-create/evolution and real Celery dispatch. Keep them outside
    the fast default gate if needed, but run them before marking Phase 4 complete.
11. Packaging cleanup so worker imports do not need `PYTHONPATH=backend`.

### Definition of Done

Phase 4 is complete when:

- the thread + Postgres path is durable on its own (no Celery required)
- uploaded documents remain readable after backend restart in Postgres mode
- existing Docker volumes from earlier phases either self-evolve safely or fail
  `/ready` with a clear schema error
- document status and branch status are stored durably
- the API process returns document state written by a separate worker process
  (no stale in-process cache in Postgres mode)
- Celery processing can be enabled with a feature flag
- Celery tasks do not pass raw document bytes or large/sensitive result payloads
  through Redis
- `/documents/{id}` and `/documents/{id}/status` work for Celery-processed
  documents
- evaluation run results can be retrieved after completion
- normal unit tests remain fast and hermetic
- Docker integration tests verify the Redis/Celery/Postgres path before Phase 4
  is marked complete
- docs clearly state what is durable and what is still portfolio-scoped

### Phase 4 Readiness

> Status: **defined, not implemented.**

Phase 4 should start with durable document state. New product features should
wait until the durable async workflow is working, tested and documented.

## 4. Phase 1 API Design

### Health

```http
GET /health
```

```json
{
  "status": "alive"
}
```

### Upload Document

For Phase 1, this can be synchronous or simple background processing.

```http
POST /documents/upload
```

Response:

```json
{
  "document_id": "doc_123",
  "filename": "invoice_001.pdf",
  "status": "processed"
}
```

Phase 2 should change this to async `202 Accepted`.

### Get Document

```http
GET /documents/{document_id}
```

Response:

```json
{
  "document_id": "doc_123",
  "filename": "invoice_001.pdf",
  "summary": "This invoice is from Example Ltd for EUR 12,450.",
  "document_type": "invoice",
  "extracted_fields": {
    "vendor": "Example Ltd",
    "amount": 12450,
    "currency": "EUR"
  }
}
```

### Ask Question

```http
POST /qa
```

Request:

```json
{
  "question": "Which invoices are above 10,000 EUR?"
}
```

Response:

```json
{
  "run_id": "run_123",
  "answer": "One invoice is above 10,000 EUR.",
  "sources": [
    {
      "document_id": "doc_123",
      "filename": "invoice_001.pdf",
      "page_number": 1,
      "section_title": "Invoice Summary",
      "chunk_id": "chunk_001",
      "snippet": "Total amount: EUR 12,450"
    }
  ],
  "status": "success"
}
```

### Insufficient Information

```json
{
  "run_id": "run_124",
  "answer": "The available documents do not contain enough information to answer this question.",
  "sources": [],
  "status": "insufficient_information"
}
```

## 5. Phase 2 API Changes

### Async Upload

```http
POST /documents/upload
```

Returns:

```text
202 Accepted
```

```json
{
  "document_id": "doc_123",
  "task_id": "task_456",
  "status": "queued"
}
```

### Status

```http
GET /documents/{document_id}/status
```

MVP async status:

```json
{
  "document_id": "doc_123",
  "status": "processing",
  "steps": [
    {"name": "parsing", "status": "completed"},
    {"name": "embedding", "status": "running"},
    {"name": "extracting", "status": "pending"}
  ]
}
```

### Readiness

```http
GET /ready
```

Checks:

- database
- vector store
- required config

In Postgres mode, `/ready` also creates/verifies the pgvector retrieval schema:
extension, `document_chunks`, vector dimension and HNSW index.

## 6. Phase 3 API Additions

### Streaming Q&A

```http
POST /qa/stream
```

Use only after normal `/qa` is reliable.

Ordering:

1. stream status events
2. generate answer server-side
3. map citations
4. run support check if needed
5. stream final accepted answer

Do not stream unsupported answer tokens before verification.

## 7. Document Parsing

### Supported Types

Phase 1:

- TXT
- DOCX
- digital-native PDF

Out of scope:

- scanned PDF OCR

### Recommended Libraries

- `python-docx` for DOCX
- `pdfplumber` or `pymupdf4llm` for PDF
- simple parser for TXT

### Parser Output

Use a common internal structure:

```python
class ParsedDocument(BaseModel):
    document_id: str
    text: str
    pages: list[ParsedPage]
    metadata: dict
```

For Phase 1, do not overbuild layout parsing. Preserve page numbers and basic section boundaries where possible.

## 8. Chunking

Start simple but avoid obviously bad chunking.

Rules:

- keep table-like text together when possible
- keep headings with their section text
- include page number metadata
- include chunk index
- include source filename

Recommended starting values:

```text
chunk_size = 800 tokens
chunk_overlap = 100 tokens
```

Improve later with structural chunking.

## 9. Extraction

Use structured outputs with Pydantic validation.

Example invoice schema:

```python
class InvoiceFields(BaseModel):
    vendor: str | None = None
    amount: float | None = None
    currency: str | None = None
    invoice_date: str | None = None
    payment_due_date: str | None = None
```

Example contract schema:

```python
class ContractFields(BaseModel):
    party_name: str | None = None
    effective_date: str | None = None
    renewal_terms: str | None = None
    risk_level: Literal["low", "medium", "high", "unknown"] = "unknown"
```

Phase 2 should add confidence hard gates:

- schema invalid
- required field missing
- critical plausibility check fails

## 10. Summarisation

Use a short business-friendly summary format:

```text
- What this document is
- Key facts
- Risks or actions
```

Keep summaries concise.

## 11. RAG Pipeline

### Phase 1

1. Embed chunks.
2. Store vectors.
3. Retrieve top chunks.
4. Generate answer from context.
5. Use citation placeholders.
6. Backend maps citations.
7. Return answer and sources.

### Phase 2

Add:

- pgvector
- pgvector dimension/readiness checks
- metadata filters
- reranking
- evaluation report
- run logs

### Phase 3

Add:

- support-check gate
- streaming
- cost estimation
- cache scope key

## 12. Deterministic Citations

This is a core feature.

### Prompt Context

Pass context like:

```text
[0] filename: invoice_001.pdf, page: 1
Text: Total amount: EUR 12,450

[1] filename: invoice_002.pdf, page: 1
Text: Total amount: EUR 8,200
```

### LLM Instruction

```text
Use citation tags like <cite index="0">.
Do not invent filenames, document IDs, page numbers or chunk IDs.
Use only indexes from the provided context.
```

### Backend Mapping

Backend parses:

```text
<cite index="0">
```

and maps it to:

```json
{
  "document_id": "doc_123",
  "filename": "invoice_001.pdf",
  "page_number": 1,
  "chunk_id": "chunk_001",
  "snippet": "Total amount: EUR 12,450"
}
```

### Failure Rules

- no citation placeholders -> return answer with `needs_review` or run support check
- invalid index -> fallback or needs review
- citation index out of range -> fallback or needs review

## 13. Evaluation

### Phase 1 Evaluation

Create:

```text
questions.jsonl
negative_questions.jsonl
expected_extractions.jsonl
```

Keep it small:

- 20 normal questions
- 5 negative questions
- 10 to 20 documents

Metrics:

```text
document_hit_at_5
unsupported_answer_rejection_rate
citation_coverage
extraction_field_accuracy
average_latency_ms
```

### Example Question

```json
{
  "question_id": "q_001",
  "question": "Which invoices are above 10,000 EUR?",
  "expected_document_ids": ["doc_001"],
  "expected_facts": ["EUR 12,450"],
  "expected_response_type": "answer"
}
```

### Negative Question

```json
{
  "question_id": "nq_001",
  "question": "Which document mentions a Singapore office?",
  "expected_response_type": "insufficient_information"
}
```

### Dataset Generation

Later add:

```text
scripts/generate_eval_dataset.py
```

Use an LLM to generate candidate questions, then manually review before committing.

## 14. Privacy

### Phase 1

Use synthetic documents only.

Redact simple high-risk patterns before logging or display:

- emails
- phone numbers
- account-like numbers

Do not log raw sensitive content.

### Phase 2

Add:

- `raw_text`
- `ai_text`
- `display_text`
- privacy policy version
- raw text retention policy

### Phase 3

Add:

- tokenized placeholders
- richer PII policy
- production privacy notes

## 15. Cost Tracking

Do not build complex cost accounting first.

### Phase 1

Optional:

- log model name
- log approximate tokens if available

### Phase 2

Add:

- `ModelCall` table or log records
- input/output tokens
- price table with `as_of_date`
- estimated cost per run

For local models:

```text
API cost = $0.00
local compute cost is not estimated
```

## 16. Async Processing

### Phase 1

Can be simple.

Option A:

- synchronous upload for fastest demo

Option B:

- one background task

### Phase 2

Use one worker task:

```text
process_document(document_id):
  parse
  extract
  summarise
  chunk
  embed
  mark completed
```

This proves async processing without distributed complexity.

### Phase 3

Use Celery group/chord:

```text
parse -> privacy -> chunk -> group(embed, classify, extract, summarize) -> aggregate
```

Do not introduce Celery chord until the simple worker version works.

## 17. Status Model

### Phase 1

Simple:

```text
uploaded
processing
completed
failed
```

### Phase 2/3

Document-level:

```text
queued
parsing
privacy_processing
chunking
processing
completed
failed
```

Branch-level:

```text
embedding
classifying
extracting
summarising
```

`needs_review` is a boolean, not a lifecycle state.

## 18. pgvector

Use pgvector after the basic RAG flow works.

Document:

```text
embedding_model
embedding_dimension
distance_metric
operator_class
index_type
```

Example:

```text
embedding_model = local-hash-embedding for the no-key Docker demo; text-embedding-3-small for OpenRouter embeddings
embedding_dimension = 1536
distance_metric = cosine
operator_class = vector_cosine_ops
index_type = hnsw
```

Changing embedding dimension requires a database migration.

## 19. File Upload Safety

Implement early:

- max file size
- allowed extensions
- allowed MIME types
- safe filename handling
- parser timeout
- temp file cleanup
- corrupt file handling

This is simple and valuable.

## 20. Testing Plan

### Phase 1 Tests

- parser tests
- chunker tests
- extraction schema tests
- citation mapping tests
- insufficient-information test
- QA endpoint test

### Phase 2 Tests

- async upload test
- status endpoint test
- pgvector retrieval test
- pgvector dimension/readiness regression test
- evaluation script test
- cost estimation test
- privacy redaction test

### Phase 3 Tests

- streaming test
- Celery chord failure test
- critic gate test
- reranker on/off test

## 21. Observability

### Phase 1

Use structured logs:

- run ID
- document ID
- endpoint
- status
- latency
- error

### Phase 2

Add:

- candidates retrieved
- context chunks used
- model name
- token counts
- estimated cost
- citation count

### Phase 3

Add:

- branch statuses
- queue wait time
- critic invoked
- cache scope key
- reranker status

## 22. Development Milestones

### Milestone 1: Project Skeleton

- FastAPI app
- Streamlit app
- health endpoint
- Docker Compose
- settings
- README skeleton

### Milestone 2: Document Upload and Parsing

- upload endpoint
- parser for TXT, DOCX, PDF
- sample documents
- basic UI upload

### Milestone 3: Extraction and Summary

- structured extraction
- summary generation
- document result screen

### Milestone 4: RAG and Citations

- chunking
- embeddings
- retrieval
- answer generation
- backend citation mapping

### Milestone 5: Evaluation

- small eval dataset
- offline evaluation script
- metrics report

### Milestone 6: Production-Style Add-ons

- async processing
- pgvector
- structured logs
- reranking
- privacy handling

### Milestone 7: Demo Polish

- screenshots
- demo script
- limitations
- resume bullets
- short video

## 23. README Requirements

README should include:

1. what the project does
2. business problem
3. demo workflow
4. architecture diagram
5. tech stack
6. how to run locally
7. sample questions
8. evaluation results
9. limitations
10. future improvements
11. resume bullets

Use language:

```text
production-style
production-inspired
portfolio implementation
```

Avoid:

```text
enterprise-ready
GDPR-ready
SOC2-ready
fully production-grade
```

## 24. Definition of Done

A reviewer should be able to:

1. run the app locally
2. upload sample documents
3. see extracted fields and summaries
4. ask questions
5. receive cited answers
6. ask an unsupported question
7. see safe fallback
8. run evaluation
9. understand architecture
10. understand limitations

## 25. Final Implementation Advice

Build the smallest impressive version first.

The winning demo is:

```text
Upload documents -> extract facts -> ask questions -> get cited answers -> run evaluation.
```

Everything else is secondary.
