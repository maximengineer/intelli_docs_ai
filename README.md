# IntelliDocs AI

IntelliDocs AI is a production-style document intelligence system. Upload business documents, extract structured facts, ask questions, and get answers with backend-verified citations, or a clear refusal when the documents don't contain the answer.

## What makes this different

Calling an LLM API is the easy part. Most of the work in this project went into
what happens around that call.

### Backend-verified citations

In many RAG demos the model writes something like "Source: page 3" itself, and
nothing checks it. Here the model only writes placeholders such as
`<cite index="0">`. The backend checks each index against the context it actually
retrieved and maps it to real metadata: document ID, filename, page number,
section, chunk ID and a verbatim snippet. An invalid index produces the
insufficient-information fallback instead of a made-up citation.

### Refusing unsupported questions

Before an answer is returned, the backend checks citation integrity, lexical
grounding and numeric grounding (every number in the answer must appear in the
cited text or the question). If a check fails, the API returns
`insufficient_information` with empty sources. Retrieved context is never shown
as evidence for an answer it does not support.

### Evaluation with real numbers

The evaluation set is adversarial on purpose, with keyword-overlapping distractor
documents and negative questions. It measures retrieval hit rate, citation
coverage over all answerable questions, whether expected facts appear in the
answer, whether the first citation comes from the right document,
unsupported-answer rejection and extraction accuracy. The offline fallback scores
well below 1.0 on several of these, and the numbers below are reported as
measured. There are no confidence scores or benchmark claims.

### Durable async processing

Each document is parsed, privacy-redacted and chunked, then fans out to three
parallel branches (embedding, extraction, summarisation) whose results are
aggregated into Postgres. In Celery mode a separate worker writes that state and
the API reads it. The worker tracks status per branch, retries idempotently,
deduplicates by content hash and passes storage references through Redis instead
of raw file bytes.

### Production-style details

The project also handles upload safety (MIME, size and extension checks, parser
timeouts), pgvector with dimension guards and advisory-lock schema setup, bounded
connection pooling, Celery task time limits, privacy-aware text variants
(`raw`/`ai`/`display`) and Alembic migrations that tolerate schemas the app
created itself.

This is a portfolio implementation built in a production-style way. Its known
limitations are listed in `docs/limitations.md`.

## Business problem

Business teams review invoices, contracts, policies and reports manually. Summaries and Q&A are useful only when the system can show where an answer came from and refuse unsupported questions.

## How it works

The AI sits behind small adapter interfaces (`LLMClient`, `EmbeddingModel`):

- Generation, summarisation and extraction use OpenRouter (cloud, one `OPENROUTER_API_KEY`, OpenAI-compatible, any chat model) or Ollama (local, no key, `make up-ollama`). With neither configured, a deterministic extractive answerer takes over.
- For embeddings, `EMBEDDING_BACKEND=auto` (the settings default) uses OpenRouter embeddings when an `OPENROUTER_API_KEY` is set and zero-dependency hash embeddings otherwise. Docker Compose defaults to `hash` unless `EMBEDDING_BACKEND` is set in your shell or `.env`; the test and offline-evaluation runners always pin `hash`. Local `sentence-transformers` is an explicit opt-in (`EMBEDDING_BACKEND=local`) for real semantic search without a key.

Because of these fallbacks, the tests, CI and a fresh clone without keys all run.

## Demo workflow

```text
Upload documents -> extract facts -> ask questions -> get cited answers -> run evaluation
```

The Streamlit workspace accepts up to 10 TXT, DOCX or digital-native PDF
documents per session. It lists processing state for each document, lets the
user inspect completed results, scopes Q&A to the completed workspace documents
and provides a Remove action that deletes document state, chunks/vectors and any
remaining upload blob through the backend API.

For a step-by-step reviewer walkthrough, see `docs/demo_script.md`.

## Tech stack

- FastAPI backend
- Streamlit UI
- asynchronous upload processing with document status polling
- Pydantic schemas
- TXT, DOCX and digital-native PDF parsing
- LLM behind an adapter: OpenRouter (cloud API) or Ollama (local, no key) for generation/extraction/summaries, with a deterministic offline fallback
- Embeddings behind an adapter: local `sentence-transformers`, OpenRouter embeddings, or a hash fallback; vector search with embeddings precomputed at upload
- Backend-enforced citation mapping (validates the LLM-chosen indexes)
- PostgreSQL/pgvector vector-store runtime path with Alembic migration
- durable document state in PostgreSQL with a feature-flagged Celery/Redis
  processing path
- Streamlit-compatible verified Q&A streaming
- support-check gate, structured run metrics, lexical reranking, privacy text variants and extraction confidence gates
- Pytest tests (LLM paths use a fake client and make no network calls), linted with ruff
- Docker Compose

## Run with Docker Compose

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

By default the Docker stack runs offline with no API key (`ENABLE_LLM=false`, hash
embeddings + extractive answerer).

### Run with local Ollama LLM (no API key)

To run with a self-hosted LLM instead of a cloud API:

```bash
make up-ollama
```

This starts an Ollama container, pulls the `phi4-mini` model (~2.5 GB download
on first run) before the app starts, then starts the stack with LLM-backed
summaries, extraction and cited Q&A answers, all running locally on CPU with no
API key. The model is cached in a Docker volume, so later starts are fast.

CPU inference is slow. Timings measured on 2026-10-02 (phi4-mini, 12-core CPU,
no GPU; local measurements, not benchmarks):

| Call | Time |
|---|---|
| model load | ~11 s |
| field extraction, small invoice | ~22 s |
| cited Q&A over retrieved sample chunks | ~30-75 s |
| summary at the 12,000-character input cap | ~255 s |

`make up-ollama` therefore raises `LLM_TIMEOUT_SECONDS` to 300, disables
retries, widens the Celery task limits and gives the UI longer Q&A and
status-polling timeouts. The default cloud settings (30 s timeout, 2 retries)
would time out on every CPU call and silently fall back to the offline
heuristics. Small local models also follow output contracts less reliably, so the
prompts were hardened after measuring phi4-mini: extraction sends a compact key list
instead of a JSON Schema (the model had echoed the schema), out-of-set labels
become `"unknown"` instead of discarding the whole extraction, and the answer
prompt shows one citation example. In a rerun, phi4-mini answered the Northwind
renewal and Globex total questions correctly with citations, the numeric
grounding check rejected an answer containing an invented "20,000", and a
cited refusal was returned as `insufficient_information`. Use a larger model or
a GPU for better answers; a cloud model is the primary quality path.

To use a different model:

```bash
OLLAMA_MODEL=gemma3:4b make up-ollama
```

Switching between Ollama and OpenRouter needs no code changes: the same
`LLMClient` talks to both through their OpenAI-compatible APIs.

Docker Compose runs the backend with `VECTOR_STORE_BACKEND=postgres`, backed by
the `pgvector/pgvector:pg18` service. It takes `EMBEDDING_BACKEND` from your shell
or `.env` and defaults to `hash` when unset, so the no-key container needs no model
download or optional torch install. The backend and worker share one environment
block, so they always embed the same way. Vectors from different embedding
backends are not comparable: after switching `EMBEDDING_BACKEND` on an existing
volume, reset it with `docker compose down -v` or remove and re-upload the
documents. In this mode document metadata, summaries, extracted fields,
processing status, chunks and evaluation runs are durable in Postgres. Local `uvicorn` development defaults to
`VECTOR_STORE_BACKEND=memory` unless you opt into Postgres in `.env`.

Postgres 18 stores data under a versioned subdirectory, so Compose mounts the
named volume at `/var/lib/postgresql`. If you previously ran the project with
the old Postgres 17 volume layout, start from a fresh demo volume or perform a
proper `pg_upgrade`; do not expect a pg17 data directory to boot directly as
pg18.

Both images install pinned dependencies from `uv.lock`; the backend image has
no Streamlit or test tools, and the frontend image has only the UI dependencies.
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

Apply the migrations to an isolated fresh PostgreSQL/pgvector database and
validate the resulting revision, tables, columns, vector index and foreign key:

```bash
make alembic-integration-test
```

This integration target uses a unique temporary Compose project and removes its
containers, image, network and volume on exit. Unlike `make alembic-sql`, it
proves that the migrations execute successfully against PostgreSQL.

Run the opt-in Celery/Postgres integration test against a Docker stack:

```bash
make celery-integration-test
```

This target uses a unique Compose project, fresh Postgres/upload volumes and
random host ports, so it cannot mutate or stop the normal demo stack. It checks
worker/broker readiness, successful fan-out processing, durable worker failure,
persisted Celery task metadata and document state after a backend restart. On
failure it prints service logs before cleanup; set `KEEP_STACK=true` to preserve
the uniquely named stack for manual inspection.

The `tests` service does not load `.env`; it forces deterministic offline
settings (`ENABLE_LLM=false`, `EMBEDDING_BACKEND=hash`,
`VECTOR_STORE_BACKEND=memory`) so API keys and host-specific settings do not
affect test behavior. The Celery integration target is separate because it
starts the distributed Docker path and is slower than the hermetic gate.

Run a live provider smoke test inside Docker:

```bash
make live-test
```

The isolated live backend loads `.env` and forces `ENABLE_LLM=true`; the
`live-tests` HTTP client does not receive the provider key. It runs one synthetic
document through the real FastAPI upload/status/document/Q&A contracts. The
backend runs in strict provider mode, so extraction,
summarisation and Q&A cannot silently fall back to heuristics. The target uses a
fresh isolated Postgres volume, prints stage progress and provider token/cost
metadata, applies an overall timeout, and removes every temporary Docker
resource. It defaults to hash embeddings to keep the smoke cheaper and focused
on the LLM path. To also require provider embeddings:

```bash
make live-test-embeddings
```

`make live-test-embeddings` uses a separate fresh database, so hash and provider
vectors are never mixed. Live tests are opt-in because they incur provider cost
and are less deterministic than the offline test suite. Override the five-minute
deadline with `LIVE_TEST_TIMEOUT_SECONDS=<seconds>` when needed.

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

**Generative LLM answers/summaries/extraction (local, no key):**

```bash
make up-ollama                       # pulls phi4-mini (~2.5 GB) on first run
```

**Generative LLM answers/summaries/extraction (cloud API):**

```bash
# in .env:
ENABLE_LLM=true
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...        # https://openrouter.ai/keys
LLM_MODEL=deepseek/deepseek-v4-flash
PRICE_TABLE_AS_OF=2026-06-21
LLM_INPUT_PRICE_PER_1M_TOKENS=0.0983
LLM_OUTPUT_PRICE_PER_1M_TOKENS=0.1966
```

Token prices are model-specific and can change; verify them in OpenRouter before
changing the model or relying on estimated cost output.

For local Python development:

```bash
uv sync                             # add --extra local-embeddings for semantic search
uv run uvicorn app.main:app --app-dir backend --reload
UV_CACHE_DIR=.uv-cache INTELLIDOCS_API_URL=http://127.0.0.1:8000 uv run streamlit run frontend/streamlit_app.py
```

## Sample questions

- `Which invoice is above 10,000 EUR?` (needs the LLM path; the offline extractive answerer cannot compare amounts and refuses)
- `What are the renewal terms in the Northwind service agreement?`
- `Which vendor supplied ergonomic equipment?`
- `How many remote work days are allowed each week?`
- `What is the largest operational risk for Q2?`
- `What is the largest financial risk in Q2?` (a different document; tests whether retrieval can tell the two Q2 reports apart)
- `Which document mentions a Singapore office?` (unsupported, so it returns the fallback)

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

Snapshot from **2026-10-02**, offline with no API key (Python 3.13.14,
extractive answerer, `EMBEDDING_BACKEND=hash`). `make eval` and `uv run` give
identical results:

```json
{
  "embedding_backend": "hash",
  "llm_enabled": false,
  "documents_loaded": 13,
  "questions_evaluated": 7,
  "negative_questions_evaluated": 5,
  "expected_extractions_evaluated": 8,
  "retrieval_questions_scored": 7,
  "extraction_rows_scored": 8,
  "missing_expected_filenames": [],
  "document_hit_at_5": 1.0,
  "citation_coverage": 0.857,
  "answer_fact_recall": 0.714,
  "first_citation_document_accuracy": 0.714,
  "unsupported_answer_rejection_rate": 0.8,
  "support_check_pass_rate": 0.857,
  "extraction_field_accuracy": 1.0
}
```

Values are rounded to three decimals here. What the misses mean:

- `citation_coverage` 0.857 (6 of 7 answerable questions answered with
  citations): the extractive answerer refuses *"Which invoice is above 10,000
  EUR?"* because it cannot compare amounts. Refusing is the safe failure.
- `answer_fact_recall` 0.714: one answer cites the right ergonomic-equipment line
  but not the vendor name, which sits on a different line.
- `first_citation_document_accuracy` 0.714: for *"What is the total amount on
  the Globex invoice?"* the first cited line is another invoice's total. Lexical
  retrieval ranks a keyword-similar invoice above Globex.
- `unsupported_answer_rejection_rate` 0.8: the offline lexical answerer is fooled
  by one keyword-dense but unanswerable question (*"What is the late fee
  percentage on the Acme invoice?"*; the invoice mentions a late fee but never a
  percentage).

The LLM-backed path (`ENABLE_LLM=true`) is designed to handle these cases, but its
numbers are not committed here because they require a provider and are
non-deterministic. Before 2026-10-02, `citation_coverage` was computed over
successful answers only, which made it 1.0 by construction. It now uses all
answerable questions. See `docs/dev_log.md`.

Latency is host-dependent; rerun `make eval` for the current local value.

Local semantic embeddings (`EMBEDDING_BACKEND=local`) scored the same as hash
embeddings on the earlier (2026-06-07) metric set and have not been re-measured
against the 2026-10-02 metrics. That result is expected: these questions share
literal keywords with their answer documents, so lexical retrieval already finds
them, and the offline answerer is lexical in both runs. Semantic embeddings help
with paraphrased queries that share no keywords (covered by
`test_local_embeddings`) and with LLM-written answers, and this offline eval
measures neither. These are local demo measurements, not benchmark claims.

## Architecture

The implementation covers the Phase 5 portfolio-demo scope:

```text
FastAPI upload -> durable upload store -> queued thread/Celery task
  -> parser -> privacy variants -> chunker
  -> branch status -> extract + summarise + embed
  -> aggregate durable document state -> vector index
Question -> retriever -> reranker -> answer generator -> citation mapper -> support gate -> API response + metrics
```

All AI calls go through a thin provider adapter (`LLMClient` / `EmbeddingModel`), so the same pipeline runs on OpenRouter, local Ollama, or deterministic offline fallbacks selected by config. The default local development path remains in-memory for easy use; Docker runs the durable path against PostgreSQL/pgvector with `VECTOR_STORE_BACKEND=postgres`.

The citation mapper is the trust boundary. The generator only emits placeholders such as `<cite index="0">`; the backend validates each index against the retrieved context and maps it to real document ID, filename, page, section, chunk ID and snippet metadata. An out-of-range index (which a real model can produce) is rejected and downgraded to the insufficient-information fallback rather than shown.

## Limitations

See `docs/limitations.md`. A chronological record of engineering changes and
plan-vs-reality deviations is in `docs/dev_log.md`.

## Future improvements

- richer evaluator-based answer quality scoring
- optional Langfuse/Phoenix integration
- hosted deployment automation

## Resume bullets

- Built IntelliDocs AI, a production-inspired document intelligence portfolio project using Python, FastAPI, Streamlit, RAG and structured (Pydantic-validated) extraction.
- Designed a provider-adapter layer (OpenRouter cloud API or local Ollama, both OpenAI-compatible) with deterministic offline fallbacks, so summaries, extraction and cited answers run with or without an API key and tests use a mocked client.
- Implemented backend-verified citation mapping that validates LLM-chosen indexes against retrieved context, so the model never supplies citation metadata itself, with an insufficient-information fallback for unsupported questions.
- Created an adversarial offline evaluation (distractor documents, keyword-overlapping negatives) measuring retrieval hit-rate, citation coverage, unsupported-answer rejection and extraction accuracy, and reported the real, imperfect results.

More detailed CV-ready bullets are in `docs/resume_bullets.md`.
