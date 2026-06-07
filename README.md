# IntelliDocs AI

IntelliDocs AI is a production-style portfolio implementation for document intelligence. It lets a user upload documents, extract key facts, generate concise summaries, ask source-grounded questions, and run a small offline evaluation without relying on fake metrics.

The AI sits behind small adapter interfaces (`LLMClient`, `EmbeddingModel`):

- **Generation / summarisation / extraction** → **OpenRouter** (one `OPENROUTER_API_KEY`, OpenAI-compatible, pick any chat model). Falls back to a deterministic extractive answerer with no key.
- **Embeddings / retrieval** → zero-dependency hash embeddings by default, with opt-in local `sentence-transformers` for real semantic search or OpenRouter embeddings when configured.

Because of the fallbacks, the tests, CI and a key-less clone always run.

## Business Problem

Business teams often need to review invoices, contracts, policies and reports manually. Summaries and Q&A are useful only when the system can show where an answer came from and refuse unsupported questions.

## Demo Workflow

```text
Upload documents -> extract facts -> ask questions -> get cited answers -> run evaluation
```

For a literal reviewer walkthrough, see `docs/demo_script.md`.

## Tech Stack

- FastAPI backend
- Streamlit UI
- asynchronous upload processing with document status polling
- Pydantic schemas
- TXT, DOCX and digital-native PDF parsing
- LLM behind an adapter: OpenRouter (OpenAI-compatible) for generation/extraction/summaries, with a deterministic offline fallback
- Embeddings behind an adapter: local `sentence-transformers`, OpenRouter embeddings, or a hash fallback; vector search with embeddings precomputed at upload
- Backend-enforced citation mapping (validates the LLM-chosen indexes)
- PostgreSQL/pgvector vector-store runtime path with Alembic migration
- durable document state in PostgreSQL with a feature-flagged Celery/Redis
  processing path
- Streamlit-compatible verified Q&A streaming
- support-check gate, structured run metrics, lexical reranking, privacy text variants and extraction confidence gates
- Pytest tests (LLM paths covered with a fake client — no real network calls); ruff-linted
- Docker Compose

## Run With Docker Compose

```bash
cp .env.example .env
make up
```

Open:

- API: `http://localhost:7777/health`
- Readiness: `http://localhost:7777/ready`
- UI: `http://localhost:9999`

If those host ports are already in use, override them without changing the
container network:

```bash
BACKEND_PORT=18000 FRONTEND_PORT=18501 make up
```

By default the app runs offline with no API key (hash embeddings + extractive answerer).

Docker Compose runs the backend with `VECTOR_STORE_BACKEND=postgres`, backed by
the `pgvector/pgvector:pg18` service, and forces `EMBEDDING_BACKEND=hash` so the
container does not need a model download or optional torch install. In this mode
document metadata, summaries, extracted fields, processing status, chunks and
evaluation runs are durable in Postgres. Local `uvicorn` development defaults to
`VECTOR_STORE_BACKEND=memory` unless you opt into Postgres in `.env`.

Postgres 18 stores data under a versioned subdirectory, so Compose mounts the
named volume at `/var/lib/postgresql`. If you previously ran the project with
the old Postgres 17 volume layout, start from a fresh demo volume or perform a
proper `pg_upgrade`; do not expect a pg17 data directory to boot directly as
pg18.

The frontend is also built as a Docker image, so Streamlit dependencies are
installed at build time rather than on every container start.

Postgres and Redis are intentionally not published to host ports by default.
Backend, worker and tests use them over the Compose network, which avoids
conflicts with any local Postgres or Redis already running on the host.

Run the test suite inside Docker, using the same backend image:

```bash
make test
```

Run the offline evaluation inside Docker:

```bash
make eval
```

Check Alembic SQL generation inside Docker:

```bash
make alembic-sql
```

Run the opt-in Celery/Postgres integration test against a Docker stack:

```bash
make celery-integration-test
```

The `tests` service does not load `.env`; it forces deterministic offline
settings (`ENABLE_LLM=false`, `EMBEDDING_BACKEND=hash`,
`VECTOR_STORE_BACKEND=memory`) so API keys and host-specific settings do not
affect test behavior. The Celery integration target is separate because it
starts the distributed Docker path and is slower than the hermetic gate.

Run a live provider smoke test inside Docker:

```bash
make live-test
```

The `live-tests` service **does** load `.env`, forces `ENABLE_LLM=true`, and
runs one synthetic document through provider-backed LLM initialization,
document processing and cited Q&A. It defaults to hash embeddings to keep the
smoke cheap and focused on the LLM path. To also require provider embeddings:

```bash
make live-test-embeddings
```

Live tests are opt-in because they can incur provider cost and are less
deterministic than the offline test suite.

Run `make help` for all Docker workflow commands, including logs, status,
shutdown and Compose config validation.

The default upload processor is the simpler thread worker:

```bash
DOCUMENT_PROCESSING_BACKEND=thread make up
```

To exercise real Celery dispatch through Redis:

```bash
DOCUMENT_PROCESSING_BACKEND=celery ENABLE_LLM=false make up
```

Celery mode requires `VECTOR_STORE_BACKEND=postgres` and passes only a storage
key/document ID through Redis, not raw upload bytes.

**Real semantic retrieval (recommended, no key, offline):**

```bash
uv sync --extra local-embeddings   # installs sentence-transformers (CPU torch)
# in .env:
EMBEDDING_BACKEND=local
```

**Generative LLM answers/summaries/extraction (needs a key):**

```bash
# in .env:
ENABLE_LLM=true
OPENROUTER_API_KEY=sk-or-...        # https://openrouter.ai/keys
LLM_MODEL=qwen/qwen3.6-plus         # any OpenRouter chat model
```

For local Python development:

```bash
uv sync                             # add --extra local-embeddings for semantic search
uv run uvicorn app.main:app --app-dir backend --reload
UV_CACHE_DIR=.uv-cache INTELLIDOCS_API_URL=http://127.0.0.1:8000 uv run streamlit run frontend/streamlit_app.py
```

## Sample Questions

- `Which invoice is above 10,000 EUR?`
- `What are the renewal terms in the Northwind service agreement?`
- `Which vendor supplied ergonomic equipment?`
- `How many remote work days are allowed each week?`
- `What is the largest operational risk for Q2?`
- `What is the largest financial risk in Q2?` (distinct doc — tests retrieval discrimination)
- `Which document mentions a Singapore office?` (unsupported → fallback)

## Evaluation

Run in Docker:

```bash
make eval
```

Run locally for faster iteration:

```bash
uv run python scripts/run_evaluation.py
```

The evaluation set is intentionally adversarial: 13 documents including keyword-overlapping distractors (multiple invoices, two service agreements, an operational vs. a financial Q2 report) so retrieval has to discriminate, plus negative questions whose keywords appear in the corpus but whose specific facts do not.

Current snapshot — **2026-06-07, offline, no API key** (Python 3.13,
extractive answerer; `EMBEDDING_BACKEND=hash`):

```json
{
  "embedding_backend": "hash",
  "llm_enabled": false,
  "documents_loaded": 13,
  "document_hit_at_5": 1.0,
  "citation_coverage": 1.0,
  "unsupported_answer_rejection_rate": 0.8,
  "support_check_pass_rate": 1.0,
  "extraction_field_accuracy": 1.0
}
```

The `0.8` rejection rate is real and instructive: the offline lexical answerer is fooled by one keyword-dense but unanswerable question (*"What is the late fee percentage on the Acme invoice?"* — the invoice mentions a late fee but never a percentage). The LLM-backed path (`ENABLE_LLM=true`) is designed to refuse these, but its numbers are not committed here because they require an API key and are non-deterministic.

Latency is host-dependent; rerun `make eval` for the current local value.

Local semantic embeddings (`EMBEDDING_BACKEND=local`) score **identically** on this set (only latency changes, ~18 ms). That is expected, not a bug: these questions share literal keywords with their answer docs, so lexical retrieval already finds them, and the offline answerer is lexical in both runs. The semantic advantage shows up where this offline eval can't reach it — on paraphrased queries with no shared keywords (proven by `test_local_embeddings`) and in *answering* once the LLM is enabled. These are local demo measurements, not benchmark claims.

## Architecture

The current implementation is Phase 5 in progress:

```text
FastAPI upload -> durable upload store -> queued thread/Celery task
  -> parser -> privacy variants -> chunker
  -> branch status -> extract + summarise + embed
  -> aggregate durable document state -> vector index
Question -> retriever -> reranker -> answer generator -> citation mapper -> support gate -> API response + metrics
```

All AI calls go through a thin provider adapter (`LLMClient` / `EmbeddingModel`), so the same pipeline runs on OpenRouter or on deterministic offline fallbacks selected by config. The default local development path remains in-memory for easy use; Docker runs the durable path against PostgreSQL/pgvector with `VECTOR_STORE_BACKEND=postgres`.

The citation mapper is the trust boundary. The generator only emits placeholders such as `<cite index="0">`; the backend validates each index against the retrieved context and maps it to real document ID, filename, page, section, chunk ID and snippet metadata. An out-of-range index (which a real model can produce) is rejected and downgraded to the insufficient-information fallback rather than shown.

## Limitations

See `docs/limitations.md`. A chronological record of engineering changes and
plan-vs-reality deviations is in `docs/dev_log.md`.

## Future Improvements

- richer evaluator-based answer quality scoring
- optional Langfuse/Phoenix integration
- hosted deployment automation

## Resume Bullets

- Built IntelliDocs AI, a production-inspired document intelligence portfolio project using Python, FastAPI, Streamlit, RAG and structured (Pydantic-validated) extraction.
- Designed a provider-adapter layer (OpenRouter, OpenAI-compatible) with deterministic offline fallbacks, so summaries, extraction and cited answers run with or without an API key and tests use a mocked client.
- Implemented backend-verified citation mapping that validates LLM-chosen indexes against retrieved context, preventing citation hallucination, with an insufficient-information fallback for unsupported questions.
- Created an adversarial offline evaluation (distractor documents, keyword-overlapping negatives) measuring retrieval hit-rate, citation coverage, unsupported-answer rejection and extraction accuracy — reporting real, non-perfect numbers.

More detailed CV-ready bullets are in `docs/resume_bullets.md`.
