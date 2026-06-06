# IntelliDocs AI

IntelliDocs AI is a production-style portfolio implementation for document intelligence. It lets a user upload documents, extract key facts, generate concise summaries, ask source-grounded questions, and run a small offline evaluation without relying on fake metrics.

The AI sits behind small adapter interfaces (`LLMClient`, `EmbeddingModel`):

- **Generation / summarisation / extraction** → **OpenRouter** (one `OPENROUTER_API_KEY`, OpenAI-compatible, pick any chat model). Falls back to a deterministic extractive answerer with no key.
- **Embeddings / retrieval** → **local `sentence-transformers`** by default: real semantic search that runs offline, costs nothing and keeps document text on your machine. Falls back to a zero-dependency hash embedder when the optional extra isn't installed.

Because of the fallbacks, the tests, CI and a key-less clone always run.

## Business Problem

Business teams often need to review invoices, contracts, policies and reports manually. Summaries and Q&A are useful only when the system can show where an answer came from and refuse unsupported questions.

## Demo Workflow

```text
Upload documents -> extract facts -> ask questions -> get cited answers -> run evaluation
```

## Tech Stack

- FastAPI backend
- Streamlit UI
- Pydantic schemas
- TXT, DOCX and digital-native PDF parsing
- LLM behind an adapter: OpenRouter (OpenAI-compatible) for generation/extraction/summaries, with a deterministic offline fallback
- Embeddings behind an adapter: local `sentence-transformers` (default), OpenRouter embeddings, or a hash fallback; in-memory vector search with embeddings precomputed at upload
- Backend-enforced citation mapping (validates the LLM-chosen indexes)
- Pytest tests (LLM paths covered with a fake client — no real network calls); ruff-linted
- Docker Compose

## Run Locally

```bash
cp .env.example .env
docker compose up --build
```

Open:

- API: `http://localhost:8000/health`
- UI: `http://localhost:8501`

By default the app runs offline with no API key (hash embeddings + extractive answerer).

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

Run:

```bash
uv run python scripts/run_evaluation.py
```

The evaluation set is intentionally adversarial: 13 documents including keyword-overlapping distractors (multiple invoices, two service agreements, an operational vs. a financial Q2 report) so retrieval has to discriminate, plus negative questions whose keywords appear in the corpus but whose specific facts do not.

Current snapshot — **offline, no API key** (extractive answerer; `EMBEDDING_BACKEND=hash`):

```json
{
  "embedding_backend": "hash",
  "llm_enabled": false,
  "documents_loaded": 13,
  "document_hit_at_5": 1.0,
  "citation_coverage": 1.0,
  "unsupported_answer_rejection_rate": 0.8,
  "extraction_field_accuracy": 1.0,
  "average_latency_ms": 1.35
}
```

The `0.8` rejection rate is real and instructive: the offline lexical answerer is fooled by one keyword-dense but unanswerable question (*"What is the late fee percentage on the Acme invoice?"* — the invoice mentions a late fee but never a percentage). The LLM-backed path (`ENABLE_LLM=true`) is designed to refuse these, but its numbers are not committed here because they require an API key and are non-deterministic.

Local semantic embeddings (`EMBEDDING_BACKEND=local`) score **identically** on this set (only latency changes, ~18 ms). That is expected, not a bug: these questions share literal keywords with their answer docs, so lexical retrieval already finds them, and the offline answerer is lexical in both runs. The semantic advantage shows up where this offline eval can't reach it — on paraphrased queries with no shared keywords (proven by `test_local_embeddings`) and in *answering* once the LLM is enabled. These are local demo measurements, not benchmark claims.

## Architecture

Phase 1 keeps the architecture intentionally small:

```text
FastAPI upload -> parser -> extractor -> summarizer -> chunker -> embed at upload -> in-memory vector index
Question -> retriever (embed query, cosine search) -> answer generator -> citation mapper -> API response
```

All AI calls go through a thin provider adapter (`LLMClient` / `EmbeddingModel`), so the same pipeline runs on OpenRouter or on deterministic offline fallbacks selected by config.

The citation mapper is the trust boundary. The generator only emits placeholders such as `<cite index="0">`; the backend validates each index against the retrieved context and maps it to real document ID, filename, page, section, chunk ID and snippet metadata. An out-of-range index (which a real model can produce) is rejected and downgraded to the insufficient-information fallback rather than shown.

## Limitations

See `docs/limitations.md`. A chronological record of engineering changes and
plan-vs-reality deviations is in `docs/dev_log.md`.

## Future Improvements

- asynchronous processing and document status endpoint
- PostgreSQL with pgvector
- reranking
- structured logs with richer run metadata
- privacy policy variants
- extraction confidence hard gates
- Alembic migrations
- Streamlit-compatible verified streaming

## Resume Bullets

- Built IntelliDocs AI, a production-inspired document intelligence portfolio project using Python, FastAPI, Streamlit, RAG and structured (Pydantic-validated) extraction.
- Designed a provider-adapter layer (OpenRouter, OpenAI-compatible) with deterministic offline fallbacks, so summaries, extraction and cited answers run with or without an API key and tests use a mocked client.
- Implemented backend-verified citation mapping that validates LLM-chosen indexes against retrieved context, preventing citation hallucination, with an insufficient-information fallback for unsupported questions.
- Created an adversarial offline evaluation (distractor documents, keyword-overlapping negatives) measuring retrieval hit-rate, citation coverage, unsupported-answer rejection and extraction accuracy — reporting real, non-perfect numbers.
