# Development Log

An honest, chronological record of engineering changes to IntelliDocs AI: what
changed, why, and how it was verified. Newest entries first. Metrics here are
local demo measurements on the synthetic dataset, not benchmark claims.

---

## 2026-06-07 — Phase 5 review fixes

**Context.** A critical review of the first Phase 5 pass found no blockers, but
it did find reviewer-experience issues: sample questions were broader than the
document upload walkthrough, stream status labels sounded more precise than the
implementation, phase labels still said Phase 4 and README committed a
host-dependent latency number.

**Changes.**
- Scoped Streamlit sample-question buttons to the two uploaded walkthrough
  documents plus one unsupported question.
- Added sample-question captions so reviewers know which upload each question
  expects.
- Replaced fixed processing progress with progress derived from completed and
  running processing steps/branches.
- Renamed Q&A stream status events to generic verified-answer progress labels.
- Updated README and architecture docs from Phase 4 to Phase 5 in progress.
- Removed precise latency from the README's stable evaluation snapshot.
- Clarified in the demo script that the broader corpus is exercised by the
  evaluation command.

**Tests / verification.**
- `uv run ruff check .`: passed.
- `uv run pytest`: **59 passed, 2 skipped** on Python `3.13.13`.
- `UV_CACHE_DIR=.uv-cache uv run python scripts/run_evaluation.py`: completed
  with `document_hit_at_5=1.0`, `citation_coverage=1.0`,
  `unsupported_answer_rejection_rate=0.8`,
  `support_check_pass_rate=1.0`, `extraction_field_accuracy=1.0`,
  `average_latency_ms=8.0`.
- `git diff --check`: passed.

---

## 2026-06-07 — Phase 5 demo polish start

**Context.** Phase 5 is focused on making the finished IntelliDocs AI workflow
easy to review rather than adding another infrastructure layer.

**Changes.**
- Improved the Streamlit demo:
  - clearer document processing status with sequential steps and parallel AI
    branches
  - visible extraction confidence
  - readable extracted fields table
  - clickable sample questions
  - clearer insufficient-information display with no misleading sources
  - expandable source citations with page, section, chunk and snippet metadata
- Rewrote `docs/demo_script.md` around the Docker-first reviewer path.
- Added `docs/resume_bullets.md` with CV-ready bullets tied to implemented
  behavior.
- Linked the demo script and resume bullets from the README.
- Added a dated evaluation snapshot section to `docs/evaluation.md`.
- Fixed offline evaluation forcing so explicit `llm_client=None` means
  deterministic offline fallback, while omitted clients still use configured
  providers.
- Pinned offline CLI evaluation environment before app imports, preventing `.env`
  live-provider settings from causing network attempts during the default
  evaluation command.

**Tests / verification.**
- `uv run ruff check .`: passed.
- `uv run pytest`: **59 passed, 2 skipped** on Python `3.13.13`.
- `UV_CACHE_DIR=.uv-cache uv run python scripts/run_evaluation.py`: completed
  with `document_hit_at_5=1.0`, `citation_coverage=1.0`,
  `unsupported_answer_rejection_rate=0.8`,
  `support_check_pass_rate=1.0`, `extraction_field_accuracy=1.0`,
  `average_latency_ms=8.38`.
- `git diff --check`: passed.

---

## 2026-06-07 — Python 3.13 runtime and dependency refresh

**Context.** A dependency review found that Docker Compose was still using
Redis 7 and pgvector's Postgres 17 image even though Redis 8 and Postgres 18
tags are available. Backend dependency ranges also allowed older package
versions than the current lockfile resolved. The project also still declared
Python `>=3.12`, causing `uv.lock` to resolve unnecessary 3.12 and future 3.14
wheel splits instead of targeting the intended Python 3.13 runtime.

**Changes.**
- Standardised the project on Python 3.13:
  - `pyproject.toml` now requires `>=3.13,<3.14`.
  - `uv.lock` now records `requires-python = "==3.13.*"`.
  - Ruff targets `py313`.
  - Backend and frontend Docker images use `python:3.13-slim`.
  - Added `.python-version` with `3.13.13` for pyenv/uv local consistency.
- Updated Docker Compose runtime services to `redis:8.4-alpine` and
  `pgvector/pgvector:pg18`.
- Updated the Postgres named-volume mount to `/var/lib/postgresql`, which is
  required by the Postgres 18 Docker image layout.
- Replaced broad backend dependency ranges with current exact PyPI pins for
  SQLAlchemy, psycopg, Alembic and Celery.
- Kept the Python Redis client at `redis==6.4.0`, the latest version compatible
  with `celery[redis]==5.6.3` / Kombu's current `<6.5` Redis client constraint.
- Pinned optional/dev dependencies to current releases:
  `sentence-transformers==5.5.1` and `ruff==0.15.16`.
- Updated matching `pyproject.toml`, `uv.lock` and README references.

**Tests / verification.**
- Verified current PyPI versions and Docker Hub tags before editing.
- `uv lock` used CPython `3.13.13` and regenerated the lockfile.
- `uv lock --check`: passed.
- `uv run python --version`: `Python 3.13.13`.
- `uv run ruff check .`: passed.
- `uv run pytest`: **58 passed, 2 skipped** on Python `3.13.13`.
- `docker compose config --quiet`: passed.
- `docker compose pull redis postgres`: pulled `redis:8.4-alpine` and
  `pgvector/pgvector:pg18` successfully.
- `docker compose build backend frontend`: built both Python `3.13-slim` images
  successfully.
- Container import checks passed for backend and frontend on Python `3.13.13`.
- Rebuilt the Docker `tests` image and ran `pytest`: **58 passed, 2 skipped**
  on Python `3.13.13`.
- Verified Redis 8 and Postgres 18 become healthy in a fresh Compose project
  with the corrected Postgres 18 volume mount.
- `git diff --check`: passed.

---

## 2026-06-07 — Implementation guide numbering cleanup

**Context.** The implementation guide mixed phase headings with a separate
numbered outline, which made `## 4. Phase 1 API Design` look like Phase 4 even
though the real Phase 4 section was earlier in the document.

**Changes.**
- Made the phases the primary top-level sections:
  - `## 1. Phase 1: Working AI Product`
  - `## 2. Phase 2: Senior Engineering Proof`
  - `## 3. Phase 3: Production-Style Hardening`
  - `## 4. Phase 4: Durable Async Workflow`
- Added `## 5. Phase 5: Demo Polish And Portfolio Readiness`.
- Moved Docker/runtime guidance after the phase roadmap as `## 6. Docker-First Runtime
  And Testing`.
- Renamed the old `## 4. Phase 1 API Design` area to `## 7. API Contracts`.
- Moved API subsections under `7.1`, `7.2` and `7.3`.
- Renumbered the later technical reference sections so the outline is
  sequential and no longer collides with phase numbering.
- Numbered `###` subsections with their parent section prefix (`1.1`, `4.1`,
  `20.1`, etc.).
- Scanned project docs for stale references to the old section numbers.
- Added matching Phase 5 scope to the project plan.

**Tests / verification.**
- Documentation-only change; heading scan verified the new outline.

---

## 2026-06-07 — Phase 1-4 readiness review fixes

**Context.** A final pre-Phase 5 review found mostly operational rough edges:
Docker readiness could over-report health, Celery readiness did not prove a
worker was alive, the live smoke could dedupe on repeat runs, and a few paths
needed cleanup before adding new scope.

**Changes.**
- Docker backend healthcheck now fails unless `/ready` returns JSON
  `status=ready`.
- `/ready` now rejects invalid Celery+memory configuration and checks for a
  responding Celery worker when `DOCUMENT_PROCESSING_BACKEND=celery`.
- Upload submission failures now return a structured `503` with `document_id`,
  filename, failed status and error details.
- Live provider smoke now uses unique synthetic document content and filename on
  every run, so it cannot pass by hitting completed-document deduplication.
- Streamlit document polling now waits longer and shows an explicit still-
  processing message instead of silently stopping.
- Shared parse/privacy/chunk preparation is now a single helper used by both the
  sync/thread path and the Celery seed task path.
- `make celery-integration-test` supports `KEEP_STACK=true` for users who do not
  want the target to shut down an already-running Compose stack.
- The hermetic Docker `tests` service no longer depends on Postgres/Redis.
- Architecture docs now spell out the intentional runtime-schema/Alembic DDL
  boundary.

**Tests / verification.**
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed.
- `uv run pytest`: **58 passed, 2 skipped**.
- `make config`: passed.
- `make config-all`: passed.
- `make celery-integration-test`: **1 passed** in Docker Compose against
  Redis/Celery/Postgres with worker-aware readiness.

---

## 2026-06-07 — Phase 1-4 review fixes

**Context.** A cross-phase review found no local lint/test failures, but it did
find durable-state and Docker/Celery reliability gaps that could hide behind the
fast hermetic gate.

**Changes.**
- Forced offline evaluation now uses isolated in-memory document/vector storage
  plus a temporary upload store, even when Docker/Postgres settings are active.
- Reprocessing now clears stale branch `result_json` instead of preserving old
  Celery branch outputs.
- Celery dispatch failures now mark the document failed, record the error and
  clean the upload blob instead of leaving a queued document behind.
- `/ready` now checks Redis broker/result-backend TCP reachability when Celery
  mode is enabled.
- The Celery integration test uses unique content per run, so it cannot pass by
  hitting completed-document deduplication.
- Alembic migrations now tolerate schemas already self-created by the Docker
  runtime path.
- Cleaned stale port defaults, stale vector-store docs, upload content-hash keys,
  status ordering and unused/dead cleanup helpers.

**Tests / verification.**
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed.
- `uv run pytest`: **54 passed, 2 skipped**.
- `make celery-integration-test`: **1 passed** in Docker Compose against
  Redis/Celery/Postgres, then the target shut the stack down.

---

## 2026-06-07 — Phase 4 critique fixes

**Context.** Applied fixes from a follow-up critical review of Phase 4. The main
finding was a race in the Celery upload path: the API initialized the document
row, dispatched Celery, then initialized the row again to store the Celery task
ID. If the worker started between dispatch and the second init, that second init
could wipe worker-written `ai_text` and reset branch state.

**Changes.**
- Removed the destructive post-dispatch `init_document` call. The API now
  initializes once before enqueue and records Celery's returned task ID through a
  targeted repository update.
- Restored sync `upload()` content-hash dedup by checking for a completed
  existing document before initializing/resetting state.
- Added `backend/app/documents/processing_backend.py` so the documented
  `thread|celery` switch is represented in code instead of being inline-only.
- Added an opt-in Celery integration test:
  `backend/tests/integration/test_celery_document_processing.py`.
- Added `make celery-integration-test` to start the Docker Celery path and run
  the integration test through the backend image.
- Added completed-upload blob cleanup. Failed documents keep their stored blob
  for retry/debug, but completed documents delete the local upload blob.
- Tightened the Celery chord errback so it marks the document failed when called
  with a document ID.
- Added comments documenting the intentional shared ownership of
  `document_chunks`: the repository owns text/metadata, and `PgVectorStore`
  fills embeddings after chunks are saved.
- Updated limitations to name the connection-per-call Postgres behavior as a
  portfolio/demo scaling limitation.

**Tests / verification.**
- `uv run pytest`: **49 passed, 2 skipped**.
- Docker integration target was added but not run in this pass.

---

## 2026-06-07 — Phase 4 durable async workflow implemented

**Context.** Implemented the narrow Phase 4 scope: durable document state first,
then real Celery dispatch behind a feature flag, all verified through Docker
Compose.

**Changes.**
- Added durable document state:
  - `documents`
  - `processing_steps`
  - `document_branches`
  - `evaluation_runs`
  - `document_chunks.document_id` foreign key with `ON DELETE CASCADE`
- Added Alembic `0002_phase4_document_state` and kept the Docker runtime
  self-create path aligned with it.
- Added a `DocumentRepository` abstraction with in-memory and Postgres
  implementations. In Postgres mode, document/status reads hit the database on
  every request, so backend reads see worker writes.
- Added local durable upload storage using content-hash storage keys. Docker
  shares `/app/data/uploads` between backend, worker and live-test containers via
  a named volume.
- Added `DOCUMENT_PROCESSING_BACKEND=thread|celery`.
  - `thread` remains the default.
  - `celery` requires `VECTOR_STORE_BACKEND=postgres`.
- Replaced the Phase 3 Celery scaffold with real dispatch:
  `seed_document_from_storage -> chord(embedding, extracting, summarising) ->
  aggregate_document`.
- Branch tasks persist outputs/status in Postgres and return only small metadata
  through Redis; raw upload bytes are never sent through Redis.
- Persisted async evaluation runs in Postgres mode while keeping the fast test
  path in-memory and offline.
- Added explicit Compose `ENABLE_LLM` override support so Docker runs can be
  forced offline even when `.env` contains real provider credentials.

**Issue found during verification.**
- The first Celery smoke test exposed a real distributed-runtime bug: concurrent
  branch workers could deadlock while each process tried to run runtime schema
  evolution. Fixed by serialising schema self-create/evolution with a Postgres
  advisory lock and caching repository schema readiness per process.

**Tests / verification.**
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed.
- `uv run pytest`: **46 passed, 1 skipped**.
- `uv run alembic upgrade head --sql`: emitted `0001` + `0002` SQL.
- `docker compose --profile test build tests`: rebuilt the backend test image.
- `docker compose --profile test run --rm tests`: **46 passed, 1 skipped**.
- `docker compose --profile test run --rm tests alembic upgrade head --sql`:
  emitted the Phase 4 schema SQL in the container.
- Docker default ports verified:
  - backend `/health`: alive
  - backend `/ready`: ready, Postgres/pgvector ready
  - frontend `http://localhost:9999`: HTTP 200
- Thread + Postgres milestone verified:
  - uploaded `invoice_brightwave.txt`
  - document reached `completed`
  - restarted backend
  - `GET /documents/{id}` still returned summary, extracted fields and status
    from Postgres.
- Celery + Postgres milestone verified:
  - restarted backend/worker with `DOCUMENT_PROCESSING_BACKEND=celery`
  - uploaded `invoice_globex.txt`
  - worker completed embedding/extracting/summarising branches
  - API read the worker-written completed document
  - restarted backend
  - `GET /documents/{id}` still returned the Celery-processed document from
    Postgres.

**Current caveats.**
- Docker integration checks were run manually as smoke tests, not yet as a
  committed automated integration test target.
- Live provider smoke was not run in this pass to avoid provider cost.

---

## 2026-06-07 — Docker Compose test workflow

**Context.** The project should be operated and verified as Docker Compose
services rather than relying on a fragile local Python/Postgres/Redis/Celery
setup.

**Changes.**
- Added `.dockerignore` so local caches, `.env`, ignored plans and virtualenvs
  are not sent in the Docker build context.
- Backend image now includes scripts, Alembic migrations and `alembic.ini`, not
  just app/runtime code.
- `PYTHONPATH` inside the image now includes `/app` and `/app/backend`, so both
  `app.*` and `worker.*` imports work consistently.
- Added a backend `/ready` healthcheck in Compose.
- Frontend now waits for the backend healthcheck instead of only container start.
- Added a dedicated frontend Dockerfile so Streamlit dependencies install at
  image build time instead of on every container start.
- Added a profile-gated `tests` Compose service that runs `pytest` inside the
  backend image with deterministic offline settings and without loading `.env`.
- Added a profile-gated `live-tests` Compose service plus
  `scripts/run_live_smoke.py` for opt-in provider-backed smoke testing with
  `.env`.
- Added a Makefile with Docker workflow targets for start/stop, logs, offline
  tests, evaluation, Alembic SQL and live provider smoke testing.
- Changed default host-published Compose ports to `7777` for the backend and
  `9999` for the frontend to reduce conflicts with common local services.
- Synced the project plan and implementation guide to make Docker Compose the
  primary runtime/verification target and document the offline/live test split.
- Added live-test controls to `.env.example`.

**Container commands.**
- App stack: `make up`.
- Stop stack: `make down`.
- Tests: `make test`.
- Offline eval in container: `make eval`.
- Alembic SQL check in container: `make alembic-sql`.
- Live provider smoke: `make live-test`.
- Full target list: `make help`.

**Verification.**
- `docker compose --profile test run --rm tests`: **42 passed, 1 skipped**.
- Container offline eval completed with the synthetic dataset.
- Container Alembic SQL generation emitted the pgvector `document_chunks` schema.
- Full stack started in Docker using alternate host ports
  (`BACKEND_PORT=18000 FRONTEND_PORT=18501`); the committed Compose/Makefile
  defaults are `7777`/`9999`.
- Backend `/health` and `/ready` passed in-container; `/ready` reported
  Postgres/pgvector ready.
- Celery worker responded to `celery inspect ping`.
- Streamlit frontend returned HTTP 200 on the host-published port.
- Caveat: the Postgres/pgvector, Celery and frontend results above are from this
  session's Docker run, not from the always-on offline gate (which never starts
  those services). Re-run the `make`/`--profile` container targets to reconfirm
  before relying on them.

---

## 2026-06-07 — Phase 4 critique reviewed

**Context.** Reviewed an external critique of the newly defined Phase 4 scope,
ignoring comments about uncommitted work as requested.

**Outcome.**
- The critique agrees with the current direction: Phase 4 is now defined enough
  to implement as a narrow durable async workflow.
- Added an implementation-guide note that reintroducing document repositories
  and models is correct in Phase 4 because they become live runtime code, not
  dead Phase 2 scaffolding.
- Added an implementation-guide verification boundary: fast local tests should
  remain hermetic, while Redis/Celery/Postgres behavior should be verified by
  optional Docker integration tests and not overclaimed if those tests have not
  been run.

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
- Phase 4 scope has now been defined in the project plan and implementation
  guide as a narrow durable async workflow, not a broad product-feature phase.
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
- The project is **not ready for a broad Phase 4**. It is ready to start the
  newly defined narrow Phase 4 only if the first implementation scope is durable
  document state, durable upload storage, feature-flagged Celery dispatch and
  optional integration tests.

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
