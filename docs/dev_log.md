# Development Log

An honest, chronological record of engineering changes to IntelliDocs AI: what
changed, why, and how it was verified. Newest entries first. Metrics here are
local demo measurements on the synthetic dataset, not benchmark claims.

---

## 2026-06-06 — Phase 3 readiness review before Phase 4

**Context.** Reviewed the latest Phase 3 deep-review fixes and investigated
whether the project is ready to move to a Phase 4.

**Confirmed fixes.**
- Support check now includes lexical grounding overlap, so it can reject a valid
  citation attached to an unrelated answer.
- `/evaluation/run` is asynchronous and forced offline; results are retrieved
  with `GET /evaluation/{evaluation_id}`.
- `data/` is copied into the backend image for in-container evaluation runs.
- Celery canvas construction is reviewable and no longer runs the real document
  pipeline inside a process-local worker store.
- Sequential `steps` and fan-out-style `branches` no longer duplicate the same
  stages.
- `STREAMING_ENABLED` is wired for `/qa/stream`, and stream events now share the
  final `run_id`.
- Deleted settings/code from the earlier review are actually gone:
  `USE_CELERY_WORKER`, `OBSERVABILITY_BACKEND`, `PRIVACY_PURPOSE` and
  `text_for_purpose`.

**Remaining issues before a broad Phase 4.**
- There is no Phase 4 scope in the implementation guide. A new phase should be
  defined before implementation starts.
- Document metadata/status/extraction outputs are still process-local. This is
  the main blocker to enabling real Celery dispatch.
- Upload bytes are still represented as `content_hex` in the Celery canvas
  scaffold. Real async processing should pass durable upload storage references.
- Worker imports are Docker/test-safe, but plain local worker commands need
  `PYTHONPATH=backend` until the package layout is refactored.
- Evaluation results are async but still process-memory only; they disappear on
  restart.
- No Redis/Celery integration test currently launches a real broker/worker.

**Readiness decision.**
- Phase 3 is demo-ready and internally cleaner after the latest fixes.
- The project is **not ready for a broad Phase 4** until that phase is defined.
  If Phase 4 is added, the first scope should be durable document state,
  durable upload storage, feature-flagged Celery dispatch, and optional
  integration tests.

**Tests / verification.**
- `ruff format --check .`: clean after formatting `backend/app/api/routes_qa.py`.
- `ruff check .`: clean.
- `ENABLE_LLM=false EMBEDDING_BACKEND=hash VECTOR_STORE_BACKEND=memory uv run pytest`:
  **42 passed, 1 skipped**.
- Offline eval: completed; hit@5 1.0 · citation 1.0 · rejection 0.8 · support
  check 1.0 · extraction 1.0.
- `uv lock --check`: clean.
- `docker compose config --quiet`: clean.

---

## 2026-06-06 — Phase 3 deep review: all findings fixed (high/medium/low)

**Context.** A second, independent Phase 3 review verified the earlier self-review
and found issues it missed (a tautological trust gate, a cost/DoS hole, an
inverted Celery canvas, duplicated status structures, dead config). All fixed.

**High.**
- **Support check can now actually reject.** It was structurally a no-op: on the
  success path, citation-integrity is guaranteed by `map_citations`, so the gate
  could only ever pass (`support_check_pass_rate` was 1.0 by construction). Added
  a deterministic **grounding** layer (`critic.py`): the answer must share
  ≥ `SUPPORT_CHECK_MIN_OVERLAP` content tokens with its cited chunk text, so an
  answer that cites context it did not use is rejected. Lexical, not semantic —
  documented as such.
- **`/evaluation/run` is no longer a sync cost/DoS hole.** It now returns
  `202 {evaluation_id}` and runs **asynchronously** (`GET /evaluation/{id}` for
  the result), is **forced offline** (never makes paid LLM calls regardless of
  `.env` — it previously used ambient settings), guards an empty corpus
  (`status: no_dataset`), and guards the previously-unguarded extraction
  subscript. `data/` is now shipped in the Docker image so the endpoint isn't
  degenerate in-container. Eval logic was de-duplicated: `scripts/run_evaluation.py`
  now calls the shared `run_offline_evaluation()`.
- **Celery canvas de-landmined.** The chord header (`parse_privacy_chunk`) no
  longer runs the real pipeline into a process-local, API-invisible
  `DocumentService`. Added `build_document_canvas()` assembling the correct
  `chain → chord(group(branches), aggregate).on_error(...)` shape (reviewable,
  not dispatched until durable state exists). The no-Celery fallback's
  `.delay`/`.s` now raise instead of returning fake signatures / running inline.

**Medium.**
- **Steps vs branches no longer overlap.** `steps` is now the sequential
  pre-fan-out lifecycle (`parsing`, `privacy_processing`, `chunking`); the
  fan-out stages (`embedding`, `extracting`, `summarising`) are tracked only as
  `branches`. Removed the double `_set_step`/`_set_branch` bookkeeping.
- **`STREAMING_ENABLED` is wired**: `/qa/stream` returns 404 when disabled.

**Low.**
- Stream status events now carry the real `run_id` (generated before streaming)
  instead of `"pending"`, so they correlate with the final event.
- Deleted genuinely-dead config/code: `use_celery_worker`, `observability_backend`,
  `privacy_purpose` settings and `text_for_purpose()`/`PrivacyPurpose`.
- Docs (architecture, privacy, evaluation) updated to match: support check =
  integrity + grounding; privacy variants without a runtime purpose switch;
  async evaluation endpoint.

**Tests / verification.**
- Added grounding-rejection and async-evaluation tests; updated step/branch and
  eval-API tests. `pytest`: **42 passed, 1 skipped**. ruff clean. Offline eval
  unchanged in shape (hit@5 1.0 · citation 1.0 · rejection 0.8 · support 1.0 ·
  extraction 1.0); `support_check_pass_rate` 1.0 is now legitimate (extractive
  answers are grounded) rather than tautological. Celery dispatch and durable
  cross-process document state remain intentionally deferred.

---

## 2026-06-06 — Phase 3 critical review

**Context.** A critical review checked the Phase 3 code against the implementation
plan, looking for missing pieces, overclaims, dead configuration, duplicated
paths and refactoring opportunities.

**Findings.**
- **Celery is scaffolded, not true fan-out.** `worker/tasks.py` defines task
  contracts and an errback, but no API path dispatches a Celery group/chord and
  the branch tasks are currently no-op status payload transforms. The real
  upload path remains the in-process `DocumentService` worker thread.
- **Durable worker state is still missing.** Document metadata, extraction
  results and status remain process-local. Running upload processing in a
  separate Celery worker would make backend reads unreliable until document
  metadata/status are persisted.
- **Broker payload design is not production-safe yet.** The worker seed task
  accepts raw file bytes as hex. For real async processing, uploads should be
  stored in durable object/blob storage and tasks should pass document IDs or
  storage keys, not raw document contents through Redis.
- **Streaming is status-then-final, not token streaming.** `/qa/stream` correctly
  avoids streaming unverified answer tokens, but its status events are generic
  and not wired to live retrieval/generation progress. `STREAMING_ENABLED` is
  currently reserved configuration.
- **Support check is citation-integrity checking.** The gate verifies that final
  answers have mapped citations from retrieved context. It does not prove
  semantic entailment and will not catch every cited-but-wrong answer.
- **Purpose-scoped privacy is a helper, not a full data model.**
  `raw`/`ai_processing`/`display` variants exist at the helper level, but the
  service does not persist separate variants or use `PRIVACY_PURPOSE` to choose
  between them.
- **Optional observability is not integrated.** `OBSERVABILITY_BACKEND` is a
  reserved setting only; Langfuse/Phoenix exporters are not wired.
- **Plan structure drift.** The Phase 3 plan lists
  `scripts/generate_eval_dataset.py`, but the implementation intentionally kept
  evaluation manual/synthetic and did not add a dataset generator.
- **Test gaps remain.** Phase 3 tests cover contracts and response shapes, but
  they do not run a real Redis/Celery worker, assert true chord fan-out, or prove
  semantic support checking.

**Recommended fix order.**
1. Persist document metadata/status before enabling Celery as the default upload
   path.
2. Replace broker-passed file bytes with durable upload storage references.
3. Implement a real Celery canvas (`group`/`chord`) only after durable state
   exists.
4. Either wire or remove reserved settings:
   `USE_CELERY_WORKER`, `STREAMING_ENABLED`, `OBSERVABILITY_BACKEND` and
   `PRIVACY_PURPOSE`.
5. Add a semantic support critic or rename the current gate as citation-integrity
   checking in user-facing docs.
6. Add integration tests for Docker/Redis/Celery only if they can run reliably
   outside the normal unit-test gate.

**Documentation changes.**
- Updated architecture, limitations and implementation-plan notes to avoid
  overstating Phase 3 scope.

---

## 2026-06-06 — Phase 3 production-style hardening

**Context.** Phase 2 was clean enough to add production-style hardening without
turning the project into an unfinished platform.

**Changes.**
- Added Redis and a Celery worker service to Docker Compose.
- Added `worker/` with Celery app creation, branch task names, aggregate task and
  chord errback contract. Imports remain safe in test environments.
- Added branch-level document status for embedding, extraction and summarisation.
- Added `POST /qa/stream` NDJSON streaming for Streamlit; it emits status events
  first and only emits the final answer after backend citation/support checks.
- Added deterministic support-check gate after citation mapping.
- Added `POST /evaluation/run` and moved shared evaluation logic into the app.
- Added support-check pass rate to the offline evaluation report.
- Added purpose-scoped privacy helper and bumped privacy policy to
  `phase3-purpose-v1`.
- Added AWS deployment notes and richer evaluation docs.

**Scope line.**
- The API still defaults to the in-process upload path for demo reliability.
  Redis/Celery wiring is present and runnable, but fully durable cross-process
  document metadata/status remains future production hardening.

**Tests / verification.**
- `ruff format --check .`: clean.
- `ruff check .`: clean.
- `ENABLE_LLM=false EMBEDDING_BACKEND=hash VECTOR_STORE_BACKEND=memory uv run pytest`:
  **40 passed, 1 skipped**.
- Offline eval: hit@5 1.0 · citation 1.0 · rejection 0.8 · support check 1.0 ·
  extraction 1.0.
- `alembic upgrade head --sql`: still emits the pgvector `vector(1536)` schema
  and HNSW cosine index.
- `docker compose config`: confirms Redis and worker services plus backend
  `EMBEDDING_BACKEND=hash` / `VECTOR_STORE_BACKEND=postgres`.

---

## 2026-06-06 — Phase 2 readiness blockers fixed before Phase 3

**Context.** A Phase 2 readiness review found the local test gate was clean, but
the Docker/pgvector path still had runtime footguns that would make Phase 3
work build on an unstable base.

**Changes.**
- Docker Compose now forces `EMBEDDING_BACKEND=hash` for the Postgres/pgvector
  demo path, avoiding an optional `sentence-transformers` install or model
  download inside the backend container.
- Hash embeddings now size themselves to `POSTGRES_VECTOR_DIMENSION` when
  `VECTOR_STORE_BACKEND=postgres`, so the no-key pgvector demo does not fail the
  vector dimension guard on first upload.
- `/ready` now creates and verifies the pgvector extension/table/HNSW index in
  Postgres mode, so the service can report ready before the first upload.
- Q&A metrics now label a response as `offline-heuristic` whenever no LLM client
  is actually active, even if `.env` requested an LLM but provider init failed.
- README, architecture and limitations docs now describe hash as the key-less
  default, local semantic embeddings as opt-in, and the pgvector dimension
  contract explicitly.

**Tests / verification.**
- Added regression tests for Postgres-mode hash embedding dimensions and
  heuristic metric labeling.
- `ruff format --check .`: clean.
- `ruff check .`: clean.
- `ENABLE_LLM=false EMBEDDING_BACKEND=hash VECTOR_STORE_BACKEND=memory uv run pytest`:
  **35 passed, 1 skipped**.
- Offline eval remains honest and unchanged in shape: hit@5 1.0 · citation 1.0 ·
  rejection 0.8 · extraction 1.0.
- `alembic upgrade head --sql` emits `embedding vector(1536)` plus the HNSW
  cosine index.
- `docker compose config` confirms backend `EMBEDDING_BACKEND=hash` and
  `VECTOR_STORE_BACKEND=postgres`. It also prints local `.env` values, so live
  API keys must stay uncommitted and should be rotated if shared.

---

## 2026-06-06 — Phase 2 deep review: all findings fixed (high/medium/low)

**Context.** A second, deeper review of the (uncommitted) Phase 2 work found the
persistence/cost features were scaffolded but not wired, plus a concurrency race
and several robustness/footgun issues. All findings implemented.

**High.**
- **Persistence scoped honestly + dead code removed.** Postgres now persists only
  the retrieval slice (chunks + embeddings) in a single self-contained
  `document_chunks` table. Deleted `repositories.py`, `session_scope`, and the
  unused `DocumentRecord`/`ProcessingStepRecord`/`ModelCallRecord` models/tables
  (zero runtime callers). Document metadata/status stay in-memory — documented as
  a deliberate Phase 3 scope line in architecture/limitations.
- **Real token usage.** `OpenRouterLLMClient` now records the provider's
  `response.usage` per-thread; `QAMetrics` gained `input_tokens`/`output_tokens`,
  reported from real usage when the LLM is used and a clearly-approximate
  word-count estimate otherwise.
- **Upload race fixed.** `submit_upload` registers the queued status + task inside
  the same locked section as the dedup/join check (no check-then-act window).
- **Lazy DB + hermetic tests.** `PgVectorStore` schema init is lazy (first use),
  so importing the app never connects; `conftest.py` forces
  `VECTOR_STORE_BACKEND=memory` and clears `DATABASE_URL`.
- **Eval is deterministic by default.** `run_evaluation.py` forces the offline
  path unless `--use-llm` is passed (previously it silently made dozens of paid
  calls when `.env` enabled the LLM).

**Medium.**
- Single schema source: migration + store define the same one table; wired
  `vector(POSTGRES_VECTOR_DIMENSION)` + HNSW index from settings (those settings
  were dead before), with a fail-fast dimension guard at index time.
- Removed the buggy `content_hash = document_id` write (documents stub gone).
- `alembic/env.py` reads `DATABASE_URL` and puts `backend` on `sys.path`.
- Relevance gate now uses the best raw-retrieval cosine, not post-rerank ordering.
- Reranker sort no longer treats a legitimate `rerank_score == 0.0` as missing.

**Low.**
- Deduped the `Vector` pgvector type into `app/storage/pgvector.py`.
- `_pending_document_from_status`/failed path use `ExtractedFields()` not
  `extract_fields("")`.
- `DocumentService` executor is created lazily and shut down via `atexit`.
- Tightened `CARD_RE` (single-separator, 13–19 digits) so it stops shadowing
  phones / over-matching spaced text; documented that `raw_text` is never
  persisted. (`SQLAlchemy` was already in `pyproject` — that finding was a false
  alarm from a case-sensitive grep.)

**Tests / verification.**
- Added `test_qa_metrics.py` (real provider usage surfaced; offline fallback).
- `pytest`: **33 passed, 1 skipped**. ruff clean. Offline eval unchanged
  (hit@5 1.0 · citation 1.0 · rejection 0.8 · extraction 1.0). pgvector SQL paths
  are not exercisable without a live database.

---

## 2026-06-06 — Phase 2 critical review fixes

**Context.** A critical review found Phase 2 correctness gaps: multi-page
privacy redaction could be bypassed during chunking, pgvector was only a
schema scaffold, Docker used the wrong database host for the backend container,
and async task status had race/observability gaps.

**Changes.**
- Redact every parsed page before chunking so multi-page documents do not leak
  raw high-risk identifiers into embeddings or citations.
- Added an opt-in PostgreSQL/pgvector vector-store runtime path selected by
  `VECTOR_STORE_BACKEND=postgres`.
- Updated the Alembic migration and SQLAlchemy metadata to use a real pgvector
  `vector` column instead of JSONB.
- Docker Compose now waits for Postgres health and overrides `DATABASE_URL` to
  the `postgres` service hostname.
- Duplicate in-flight uploads now join the existing task instead of launching
  another worker for the same content hash.
- Queued/processing documents now have a status-aware placeholder response
  rather than returning 404 from `GET /documents/{document_id}`.
- Background worker failures are retained as task errors and reflected in
  document status.
- Removed the no-op `classifying` processing step.
- Corrected Q&A metrics so `candidates_retrieved` counts pre-rerank candidates
  and `context_chunks_used` counts final context.

**Tests / verification.**
- Added tests for multi-page privacy chunking, duplicate async upload joins,
  failed background task visibility, fake classification removal, readiness
  metadata, and Q&A retrieval metrics.

---

## 2026-06-06 — Phase 2 senior engineering proof

**Context.** Added the Phase 2 proof points after the Phase 1 gate was clean.

**Changes.**
- Upload endpoint now returns `202 Accepted` with `document_id` and `task_id`.
- Added `/documents/{document_id}/status` with document lifecycle and processing
  step statuses.
- Added `/ready` with config/database/vector-store readiness checks.
- Added basic privacy variants (`raw_text`, `ai_text`, `display_text`) with
  `phase2-basic-v1` redaction policy.
- Added deterministic extraction confidence gates and `needs_review`.
- Added lexical reranker, Q&A metrics, configured cost estimation, and
  structured run logging.
- Added PostgreSQL/pgvector storage scaffolding and Alembic migration.
- Updated Streamlit to poll document status before fetching completed results.

**Tests / verification.**
- `ENABLE_LLM=false EMBEDDING_BACKEND=hash uv run pytest`: **28 passed, 1 skipped**.
- Offline eval: hit@5 1.0 · citation 1.0 · rejection 0.8 · extraction 1.0.

---

## 2026-06-06 — Hermetic Phase 2 readiness gate

**Context.** Before starting Phase 2, the Phase 1 verification gate needed to
run cleanly in a restricted/offline development environment.

**Changes.**
- `routes_documents.py`: made the Phase 1 upload endpoint synchronous. This
  matches the current synchronous processing model and avoids an async
  `UploadFile`/threadpool test hang under the current dependency stack.
- `test_upload_safety.py`: calls the route directly without an async harness.
- `SentenceTransformerEmbeddingModel`: added `local_files_only` support.
- `test_local_embeddings.py`: skips the semantic embedding test unless the
  Hugging Face model is already cached locally, so the suite never attempts a
  network download.

**Tests / verification.**
- `ENABLE_LLM=false EMBEDDING_BACKEND=hash uv run pytest`: **24 passed**.
- `ENABLE_LLM=false EMBEDDING_BACKEND=hash uv run python scripts/run_evaluation.py`:
  hit@5 1.0 · citation 1.0 · rejection 0.8 · extraction 1.0.

---

## 2026-06-06 — OpenRouter LLM + local semantic embeddings, hardening & polish

**Context.** Wired a real provider in (the prior round left the LLM/embedding
layers as scaffolding), chose an embedding strategy, and cleared the
lower-severity review items.

**Provider decision.**
- **LLM (generation / summarisation / extraction): OpenRouter** (OpenAI-compatible,
  one `OPENROUTER_API_KEY`, any chat model). Verified live: `qwen/qwen3.6-plus`
  returned a completion through the adapter.
- **Embeddings: local `sentence-transformers`** (`all-MiniLM-L6-v2`) as the default
  real-retrieval path — offline, free, keeps document text on-box. Chosen over
  OpenRouter embeddings because OpenRouter's model catalogue does not surface
  embedding models, and local retrieval needs no key for a reviewer. OpenRouter
  embeddings and a zero-dependency `hash` embedder remain selectable via
  `EMBEDDING_BACKEND`.

**Changes.**
- `core/settings.py`: `embedding_backend` now `auto|local|openrouter|hash`;
  added `local_embedding_model`; added `resolve_embedding_backend()`
  (`auto` never silently pulls in torch — `local` is an explicit opt-in).
- `rag/embeddings.py`: added `SentenceTransformerEmbeddingModel` (lazy import,
  L2-normalised vectors). Factory falls back to hash if the optional dep/model
  is unavailable.
- `pyproject.toml`: optional extra `local-embeddings` (sentence-transformers);
  CPU-only torch pinned on Linux via `[tool.uv.sources]` so the install stays
  lean (installed torch 2.12.0 CPU). Added `ruff` dev dep + `[tool.ruff]` config.
- **Hermetic tests:** `backend/tests/conftest.py` forces `ENABLE_LLM=false` and
  `EMBEDDING_BACKEND=hash` before app import, so a populated `.env` (with a real
  key) never triggers network calls during the suite.
- **Lower-severity polish (from the review):**
  - document status vocabulary `processed` → `completed` (matches the documented
    lifecycle); `schemas.py` + `service.py` + two tests updated.
  - de-duplicated the word-token regex into `core/text.py` (`WORD_RE`), shared by
    the hash embedder and the heuristic answerer.
  - `rag/citations.py`: `map_citations` now returns `supported=False` for an
    uncited answer (was returning `True` for the fallback string and relying on a
    downstream check).
  - `scripts/run_evaluation.py`: report now includes `embedding_backend` and
    `llm_enabled` so a result is self-describing.
  - ruff config added; `ruff check` clean across backend/scripts/frontend.

**Tests / verification.**
- `pytest`: **24 passed** (the gated `test_local_embeddings` now runs — confirms
  vectors are unit-norm and that a keyword-free paraphrase ranks to the correct
  doc).
- Eval, `EMBEDDING_BACKEND=local`, LLM off: hit@5 1.0 · citation 1.0 · rejection
  0.8 · extraction 1.0 · ~18 ms.
- Eval, `EMBEDDING_BACKEND=hash`, LLM off: **identical** metrics · ~1.4 ms.
  This is expected, not a regression — the eval questions share literal keywords
  with their answer docs (so lexical retrieval already finds them) and the
  offline answerer is lexical in both runs. The semantic advantage shows on
  paraphrased queries (the unit test) and in LLM-on answering (not committed:
  needs a key, non-deterministic).
- Live: `get_llm_client().complete(...)` against OpenRouter returned `OK`.

**Security note.** A live OpenRouter key was placed in `.env` (gitignored, not
committed). Treat any shared/pasted key as compromised and rotate it.

---

## 2026-06-05 — Phase 1 review + implement the three recommendations

**Review finding (the core problem).** Phase 1 ran end-to-end and all tests
passed, but there was **no AI in the AI project**: summary/extraction/generation
were heuristic, embeddings were a lexical hash, the `llm/` layer (client, prompt
registry, prompts) was dead code, and the citation trust feature was never
exercised against a model that could hallucinate. The eval reported a perfect
1.0 across every metric — because the dataset was too small/easy to fail.

**Implemented (in dependency order):**

1. **Provider adapter (made the AI real).**
   - `LLMClient` protocol + `OpenRouterLLMClient` + `get_llm_client()` factory
     (returns `None` offline). Removed the old echo stub.
   - LLM-backed `generator.py`, `summarizer.py`, `extractor.py` — extraction uses
     `response_format=json_object` + `ExtractedFields.model_validate_json`
     (Pydantic validation, no regex JSON parsing); each keeps a heuristic fallback.
   - Prompt YAMLs are now actually loaded via a cached prompt registry.
   - The generator emits `<cite index>` and the LLM picks the indexes, so the
     citation validator's out-of-range → fallback branch is now real (and tested).

2. **Vector store + upload hardening.**
   - `InMemoryVectorStore` is stateful: embeddings are computed **once at upload**
     (`index`/`remove`/`search`), not re-embedded per query; revived `StoredVector`.
   - `cosine_similarity` fixed to a true normalised cosine (was a bare dot product).
   - Upload route: `await file.read(max+1)` caps memory before buffering; parsing
     runs via `run_in_threadpool` (no event-loop block); MIME check relaxed for
     `application/octet-stream`. Added content-hash dedup in the service.

3. **Eval with teeth.**
   - Added 8 keyword-overlapping distractor documents (13 total, so hit@5 can
     actually miss) and harder negatives — including one keyword-dense but
     unanswerable question. `unsupported_answer_rejection_rate` dropped to a
     real **0.8** (the lexical answerer false-positives on it).
   - Fixed the stringly-typed extraction equality (numeric-aware compare).

- Tests grew 13 → 23 (LLM paths covered with a mocked client, no network).
- Docs (README, limitations, demo_script) updated honestly, including the 0.8.

---

## Known deviations from the plan / guide

- **Status string:** uses `completed` (plan's lifecycle), not the `"processed"`
  shown in the implementation guide's example response.
- **Embeddings default:** local `sentence-transformers`, not OpenRouter
  `text-embedding-3-small` (still available as a backend).
- **Citation failure rule:** invalid/missing citation → insufficient-information
  fallback (the guide also lists a `needs_review` option, deferred to Phase 2).
- **Storage:** local development defaults to in-memory; Phase 2 adds an opt-in
  pgvector retrieval slice for chunks and embeddings. Durable document metadata
  remains Phase 3 scope.
