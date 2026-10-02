# Code Review Findings — 2026-10-02

Tracker for the full code review of IntelliDocs AI run on 2026-10-02 (baseline:
commit `5a8f718`, `uv run pytest` 115 passed / 5 skipped, `ruff check` clean).

Each finding has an ID, location, evidence, planned fix and acceptance check.
"Verified" means it was reproduced with a scratch script; "by reading" means it
was found in the code or config but not executed.

Status values: `open`, `in progress`, `fixed`, `won't fix`.

**Closed 2026-10-02.** All findings are fixed except M-11 (won't fix, not
reproduced). A self-review of the change set then fixed eight follow-ups (see
"Self-review addendum" at the end). Final gates: `uv run pytest` 147 passed /
5 skipped, `make test` 145 / 6, `make eval`, `make alembic-integration-test` and
`make celery-integration-test` passing, ruff clean. Details per fix are in
`docs/dev_log.md`.

References to "the guide" and "the plan" below mean
`intellidocs_ai_implementation_guide.md` and `intellidocs_ai_project_plan.md`:
local working documents that are gitignored, so they are not in the repository.

For every fix, follow the guide's change discipline (Appendix U.4): smallest code
change, a focused test, `uv run pytest` + `ruff check .` + `ruff format --check .`,
a `docs/dev_log.md` entry, and README/docs updates when behaviour or claims change.

## Fix Order

Answer-quality fixes (H-1, M-6) come before the evaluation change (H-2), so the
README evaluation snapshot is regenerated once, after all of them.

| # | ID | Title | Status |
|---|---|---|---|
| 1 | H-1 | Support-check grounding accepts unrelated answers | fixed |
| 2 | M-5 | Raw section titles bypass privacy redaction | fixed |
| 3 | H-3 | Thread-mode documents stuck after backend restart | fixed |
| 4 | M-12 | Postgres search returns chunks of unfinished/failed documents | fixed |
| 5 | H-4 | Worker and backend can use different embedding backends | fixed |
| 6 | M-6 | Chunker drops line breaks | fixed |
| 7 | H-2 | `citation_coverage` is 1.0 by construction; `expected_facts` unused | fixed |
| 8 | M-9 | `dd.mm.yyyy` dates redacted as phone numbers | fixed |
| 9 | M-7 | Q&A metrics mislabel model on fallback; Ollama cost unknown | fixed |
| 10 | M-8 | Ollama timeouts vs Celery/UI limits | fixed |
| 11 | M-10 | DOCX tables are dropped by the parser | fixed |
| 12 | M-11 | Filtered HNSW search may return too few chunks | won't fix |
| 13 | M-13 | Small local models break JSON-schema and citation contracts | fixed |
| 14 | L-1 … L-13 | Low-severity cleanups | fixed |

---

## High

### H-1 — Support-check grounding accepts unrelated answers

- **Status:** fixed (2026-10-02). Function words are excluded from grounding
  overlap (`core/text.py: FUNCTION_WORDS, content_tokens`), and a new numeric
  grounding layer (`SUPPORT_CHECK_NUMERIC_GROUNDING`, default on) rejects
  numbers that appear in neither the cited chunks nor the question. Four tests
  were added in `test_phase3_hardening.py`. The offline eval is unchanged because
  the extractive answerer quotes chunk sentences verbatim.
- **Location:** [backend/app/rag/critic.py:62](../backend/app/rag/critic.py#L62),
  `support_check_min_overlap=1` in
  [backend/app/core/settings.py:56](../backend/app/core/settings.py#L56)
- **Problem:** `_content_tokens` keeps every token longer than 2 characters, so
  function words ("the", "and", "for") count as grounding overlap. With a minimum
  overlap of 1, almost any English answer passes.
- **Evidence (verified):** the answer *"The moon is made of cheese and the sky is
  green."*, citing an invoice chunk, returns
  `supported=True, reason='citations_supported_by_context'`.
- **Doc impact:** [docs/architecture.md](architecture.md) and the guide (G.5)
  claim the gate rejects answers that cite context they did not use.
- **Fix:** exclude a shared stopword list from content tokens (move `STOPWORDS`
  from `generator.py` into `core/text.py` and extend it with common function
  words). Then check grounding per cited sentence or with a minimum overlap ratio
  instead of a single shared token. Keep it lexical and say so in the docs.
- **Acceptance:** a test where an unrelated cited answer is rejected, a test where
  a genuinely grounded answer passes, and an offline eval rerun with the effect
  recorded.

### H-2 — `citation_coverage` is 1.0 by construction; `expected_facts` unused

- **Status:** fixed (2026-10-02). `citation_coverage` now divides by all
  answerable questions. New metrics: `answer_fact_recall` and
  `first_citation_document_accuracy`. While investigating, the offline answerer
  was found returning section headings as evidence ("SERVICE AGREEMENT" for the
  Northwind renewal question); it now skips headings (the chunker's own heading
  rule). New snapshot (Docker and local identical): hit@5 1.0, citation 0.857,
  fact recall 0.714, first-citation 0.714, rejection 0.8, support 0.857,
  extraction 1.0. README, `docs/evaluation.md`, guide I.3/I.6/B.9,
  limitations, demo script and resume bullets were updated.
- **Location:** [backend/app/rag/service.py:65](../backend/app/rag/service.py#L65),
  [backend/app/evaluation/service.py:135](../backend/app/evaluation/service.py#L135)
- **Problem:** `QAService` only returns `success` when `sources` is non-empty, so
  "cited answers ÷ successful answers" cannot be anything but 1.0 (or 0.0 with no
  answers). The dataset's `expected_facts` are never scored, so wrong-document
  answers are invisible to the metrics.
- **Evidence (verified):** the offline answers to q_001 (">10,000 EUR") and q_006
  ("Globex total") open with the Brightwave/Meridian invoices, yet every metric
  reports 1.0.
- **Fix:** redefine `citation_coverage` as answerable questions that received a
  cited `success` ÷ all answerable questions. Add an `answer_fact_recall` metric
  (expected facts found in the answer, case-insensitive). Optionally add a
  stricter "first cited source is an expected document" check.
- **Acceptance:** unit tests for both metrics. Rerun the offline eval. Update the
  dated snapshot in README, `docs/evaluation.md` and the guide, and explain any
  drop honestly.
- **Note:** this changes the published evaluation numbers. That is intended.

### H-3 — Thread-mode documents stuck after backend restart

- **Status:** fixed (2026-10-02). The fix is a startup recovery step rather than
  the in-process orphan check sketched below: thread tasks die with the API
  process, so at FastAPI startup (lifespan only, never in the Celery worker)
  `DocumentService.recover_interrupted_thread_documents()` marks non-terminal,
  non-Celery documents `failed` with a re-upload message and clears their
  chunks. The new repository method is `list_unfinished_documents()`. Covered
  by two unit tests and verified against real Postgres in an isolated Compose
  project (restart → `failed`, Celery document untouched, `DELETE` → 204).
- **Location:** [backend/app/documents/service.py:135](../backend/app/documents/service.py#L135)
  (join-existing-task branch),
  [backend/app/documents/service.py:482](../backend/app/documents/service.py#L482)
  (delete guard)
- **Problem:** in thread + Postgres mode (the Docker default), a document whose
  thread task was lost in a restart stays `queued`/`parsing`/`processing`
  forever. Re-uploading it "joins" a task that no longer exists. Deleting it
  returns 409.
- **Evidence (by reading):** no code path moves an orphaned thread-backend
  document to a terminal state.
- **Fix:** treat a non-terminal document whose `processing_backend == "thread"`
  and which has no live future in this process as orphaned. Re-upload
  reprocesses it, and delete is allowed. Optionally, also mark orphaned thread
  documents as failed at startup.
- **Acceptance:** an in-memory repository test that simulates a missing future and
  asserts re-upload reprocesses and delete succeeds.

### H-4 — Worker and backend can use different embedding backends

- **Status:** fixed (2026-10-02), together with L-8. Backend and worker now
  share an `x-app-environment` YAML anchor. `docker compose config` shows
  identical values (only `REQUIRE_DATABASE_READY` is API-only). The bug was live
  for this repo's `.env` (`EMBEDDING_BACKEND=openrouter`) in Celery mode. Docs
  that claimed Compose "forces" hash were corrected: it is a
  `${EMBEDDING_BACKEND:-hash}` default.
- **Location:** [docker-compose.yml](../docker-compose.yml): the worker sets
  `EMBEDDING_BACKEND: hash`, the backend sets `${EMBEDDING_BACKEND:-hash}`
- **Problem:** in Celery mode with `EMBEDDING_BACKEND=openrouter`, the worker
  indexes with hash vectors while the backend embeds queries with OpenRouter.
  Both are 1536-dimensional, so the dimension guard does not catch it and
  retrieval silently degrades.
- **Evidence (by reading).**
- **Fix:** use the same `${EMBEDDING_BACKEND:-hash}` for the worker. Consider a
  shared YAML anchor for backend/worker environment (see L-8). Optionally record
  the embedding model name per chunk and reject mismatched queries.
- **Acceptance:** `make config` shows matching values for backend and worker.

### M-12 — Postgres search returns chunks of unfinished/failed documents

- **Status:** fixed (2026-10-02). Found while fixing H-3.
- **Location:** [backend/app/rag/vector_store.py](../backend/app/rag/vector_store.py)
  (`PgVectorStore.search`)
- **Problem:** search did not check document status. Chunks of documents that
  were still processing, or had failed after the embedding step (e.g. a Celery
  embedding branch succeeding while extraction failed), could be retrieved and
  cited by `/qa` calls without `document_ids`.
- **Fix:** search joins `documents` and only returns chunks of `completed`
  documents. The in-memory store (tests/eval/local dev) has no status; its thread
  path removes vectors on failure.
- **Verification:** in an isolated Compose project, an exact-text query for an
  in-flight document's chunk returned only the completed document.

---

## Medium

### M-5 — Raw section titles bypass privacy redaction

- **Status:** fixed (2026-10-02). `_replace_parsed_text` now redacts
  `section_title` too, covered by
  `test_section_titles_derived_from_raw_text_are_redacted`.
- **Location:** [backend/app/documents/service.py:584](../backend/app/documents/service.py#L584)
- **Problem:** `_replace_parsed_text` redacts page text but copies the parser's
  raw `section_title`. The chunker falls back to it, so it reaches chunk rows,
  citations and the UI.
- **Evidence (verified):** a TXT file whose first line is
  `Contact jane.doe@example.com` yields chunk section title
  `Contact jane.doe@example.com`.
- **Fix:** run section titles through `apply_basic_privacy(...).ai_text` as well.
- **Acceptance:** a privacy test asserting no raw email in chunk `section_title`.

### M-6 — Chunker drops line breaks

- **Status:** fixed (2026-10-02). Chunks slice the original section text by
  token spans (`test_chunker_keeps_line_breaks_inside_chunks`). Eval effect,
  recorded for H-2: the offline answerer now picks single lines, so q_001
  ("Which invoice is above 10,000 EUR?") is refused instead of dumping three
  whole invoices, and `support_check_pass_rate` moved from 1.0 to 0.857. The
  heuristic was deliberately not re-tuned to recover the number.
- **Location:** [backend/app/documents/chunker.py:22](../backend/app/documents/chunker.py#L22)
- **Problem:** chunks are rebuilt with `" ".join(tokens)`, which flattens lines.
  Label/value lines and tables collapse into one run, so the offline answerer
  treats an entire invoice as one sentence and cites the whole chunk. This also
  defeats "avoid splitting obvious tables".
- **Evidence (verified):** `INVOICE\nVendor: Acme\nTotal amount: ...` becomes
  `'INVOICE Vendor: Acme Total amount: EUR 1,000.00 Due date: 2026-01-01'`.
- **Fix:** use `TOKEN_RE.finditer` spans and slice the original section text
  from the first token's start to the last token's end, keeping the windowing
  and overlap unchanged.
- **Acceptance:** a chunker test that keeps newlines, the existing chunker tests
  passing, and an offline eval rerun.

### M-7 — Q&A metrics mislabel model on fallback; Ollama cost unknown

- **Status:** fixed (2026-10-02). `generator.generate_answer()` returns
  `GeneratedAnswer(text, used_llm)`. Metrics use the LLM's model name, usage and
  cost only when `used_llm`; otherwise `offline-heuristic` with `$0.00`. This
  also fixes relevance-gate refusals, which previously reported a non-zero
  "estimated cost" for a call that never happened when prices were configured.
  Ollama reports a known `$0.00` API cost. Three new tests are in
  `test_qa_metrics.py`.
- **Location:** [backend/app/rag/service.py:145](../backend/app/rag/service.py#L145),
  [backend/app/rag/generator.py:56](../backend/app/rag/generator.py#L56)
- **Problem:** when the LLM call fails and the heuristic answers, `model_name`
  still reports the LLM model and cost is computed from word-count estimates.
  Ollama runs report `estimated_cost_usd=null` / `cost_estimate_available=false`,
  while the plan specifies "API cost = $0.00" for local models.
- **Fix:** have the generator report which path produced the answer, and label
  heuristic answers `offline-heuristic`. Treat `llm_provider == "ollama"` as a
  known API cost of `0.0` (local compute out of scope), then update guide
  Appendix K.
- **Acceptance:** a test with a failing fake client asserting
  `model_name == "offline-heuristic"`, and a test for the Ollama cost fields.

### M-8 — Ollama timeouts vs Celery/UI limits

- **Status:** fixed (2026-10-02). Measured first (phi4-mini, 12-core CPU, through
  the app's own client): model load 11 s, small-invoice extraction 46 s,
  five-document Q&A 55 s, 12k-char summary 255 s. Even the smallest call
  exceeded the 30 s default timeout, so every Ollama extraction/summary had
  been timing out three times and silently falling back to heuristics. The
  Compose shared env now exposes `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` and
  the Celery limits (defaults unchanged). `make up-ollama` pulls the model
  before starting the app and sets 300 s / 0 retries / Celery 330-360 s / UI
  360 s Q&A and 900 s polling. The frontend reads `QA_TIMEOUT_SECONDS` and
  `STATUS_POLL_SECONDS`, and `make down` also stops the Ollama profile.
  Verified with `make -n` and `docker compose config`. A full end-to-end
  `make up-ollama` UI run was not performed (it would replace the default
  Compose stack).
- **Location:** [backend/app/core/settings.py:58](../backend/app/core/settings.py#L58)
  (Celery 50s soft / 60s hard limit),
  [backend/app/core/settings.py:78](../backend/app/core/settings.py#L78)
  (30s LLM timeout, 2 retries),
  [frontend/streamlit_app.py:405](../frontend/streamlit_app.py#L405) (60s Q&A
  request), [Makefile](../Makefile) `up-ollama`
- **Problem (by reading, not run):** CPU `phi4-mini` on prompts of up to 12,000
  characters can exceed 30s. Three attempts can exceed the Celery hard limit and
  the UI timeout, so extraction, summaries and answers silently fall back to the
  heuristics. `make up-ollama` also starts the backend before the model pull
  finishes.
- **Fix:** set Ollama-specific defaults in Compose (longer `LLM_TIMEOUT_SECONDS`,
  `LLM_MAX_RETRIES=0`), raise the Celery limits when `LLM_PROVIDER=ollama`, make
  the UI Q&A timeout configurable, and pull the model before starting the
  backend. Measure one real run before choosing numbers.
- **Acceptance:** one manual `make up-ollama` run with timings recorded in the
  dev log.

### M-9 — `dd.mm.yyyy` dates redacted as phone numbers

- **Status:** fixed (2026-10-02). `NUMERIC_DATE_RE` protects numeric dates (both
  leading parts 1-31, repeated separator, 2- or 4-digit year) before redaction.
  Covered by `test_basic_privacy_preserves_numeric_dates_but_not_phone_numbers`.
  Accepted trade-off: a phone number written exactly like a date is kept.
- **Location:** [backend/app/documents/privacy.py:10](../backend/app/documents/privacy.py#L10),
  [backend/app/documents/privacy.py:26](../backend/app/documents/privacy.py#L26)
- **Problem:** only ISO dates are protected before phone redaction.
- **Evidence (verified):** `Signed on 05.06.2026` becomes
  `Signed on [REDACTED_PHONE]`.
- **Fix:** also protect `dd.mm.yyyy`, `dd/mm/yyyy` and `dd-mm-yyyy` dates before
  redaction.
- **Acceptance:** a privacy test for each date format, and the existing phone
  redaction tests still passing.

### M-10 — DOCX tables are dropped by the parser

- **Status:** fixed (2026-10-02). The parser walks `doc.iter_inner_content()` and
  emits table rows as `a | b` lines (merged cells deduplicated). The heuristic
  extractor also accepts `Label | value` rows. Tests:
  `test_docx_parser_keeps_tables_in_document_order`,
  `test_heuristic_extractor_reads_docx_table_rows`. Eval unchanged (TXT
  corpus).
- **Location:** [backend/app/documents/parser.py:61](../backend/app/documents/parser.py#L61)
- **Problem:** only `doc.paragraphs` is read, so table cells (where DOCX invoices
  usually hold amounts) are lost.
- **Fix:** iterate the body in document order and emit table rows as
  ` | `-joined cell text.
- **Acceptance:** a parser test with a generated DOCX containing a table.

### M-11 — Filtered HNSW search may return too few chunks

- **Status:** won't fix (2026-10-02): not reproduced. In an isolated Compose
  project with pgvector 0.8.2 and 3,001 chunks, a `document_ids` filter
  on one document returned the target chunk with its exact score (0.158) while
  thousands of keyword-similar chunks existed. `EXPLAIN` shows the planner uses
  the `ix_document_chunks_document_id` btree plus an exact sort, not HNSW, for
  selective filters. The UI caps workspaces at 10 documents. The residual risk
  is a filter covering a large share of the corpus; if that ever matters, use
  `SET LOCAL hnsw.iterative_scan = relaxed_order` (pgvector >= 0.8).
- **Location:** [backend/app/rag/vector_store.py:194](../backend/app/rag/vector_store.py#L194)
- **Problem (by reading):** pgvector applies `document_id = any(...)` after the
  HNSW scan (default `hnsw.ef_search=40`). Workspace-scoped queries over a larger
  corpus can return fewer than `retrieval_candidate_k` chunks, or none.
- **Fix:** enable `SET LOCAL hnsw.iterative_scan = relaxed_order` (pgvector ≥ 0.8)
  for filtered queries, or raise `ef_search` for filtered queries.
- **Acceptance:** a Docker integration check with many documents and a filter on
  one, showing results are returned.

### M-13 — Small local models break JSON-schema and citation contracts

- **Status:** fixed (2026-10-02). Changes:
  - Extraction sends a key list derived from `ExtractedFields` plus an
    all-missing example (`extraction_request`), with prompt v0.2.0.
  - `document_type`/`risk_level` labels are lower-cased, and out-of-set labels
    become `"unknown"` (logged) instead of failing the whole object.
  - The answer prompt (v0.2.0) shows one citation example and forbids `[1]`.
  - Closing `</cite>` tags are stripped from answers.
  - An answer containing the fallback sentence is always
    `insufficient_information`, even with a citation attached.
  - Broken LLM citation contracts log `llm_citation_contract_failed`.
  - L-7's `answer_declined` reason is part of this change.

  phi4-mini rerun: small extractions ~22 s (was ~46 s) with no schema echo
  (Acme 1.0, Remote Work 1.0, Zenith 0.75, Northwind 0.33). The 12k mixed input
  now returns a well-shaped object whose only error was the enum, which is now
  normalised. Q&A: q_002 and q_006 correct and cited; q_001 rejected by numeric
  grounding (invented "20000"); nq_004 was a cited refusal and is now refused.
- **Location:** [backend/app/documents/extractor.py:37](../backend/app/documents/extractor.py#L37)
  (sends the full `model_json_schema()`),
  [prompts/answer_question.yaml](../prompts/answer_question.yaml)
- **Problem (verified with phi4-mini):** on a 12k-char input, extraction
  returned the schema itself (`party_name: {"title": "Party Name", ...}`) and an
  invalid `document_type`. A Q&A answer cited with `[1]` instead of citation
  tags, so the backend correctly refused it. Non-strict mode silently falls
  back to heuristics, so Ollama mode can look LLM-backed while it is not.
- **Fix idea:** send a compact field list with one filled JSON example instead
  of the full JSON Schema, add a one-line citation example to the answer
  prompt, and log/count contract failures per provider so silent fallbacks are
  visible. Re-measure with phi4-mini; do not tune prompts to the eval set.
- **Acceptance:** a unit test for the new extraction prompt shape, plus a
  dated phi4-mini rerun recorded in the dev log.

---

## Low / Refactoring

- [x] **L-1 Dead code.** Fixed: removed `LocalStubLLMClient`, the duplicate `_pending_document_from_status`, `HashEmbeddingModel.version` and the unused `llm_temperature` setting.
- [x] **L-2 Client naming/duplication.** Fixed: `OpenAICompatibleLLMClient` with one construction path; attribution headers are sent only to OpenRouter (tested).
- [x] **L-3 Celery fallback is unreachable.** Fixed: `worker/worker.py` builds the Celery app directly; the unreachable fallback is gone.
- [x] **L-4 Import-time singletons.** Fixed: `get_document_service`, `get_qa_service` and `get_evaluation_service` build lazily (`lru_cache`), so importing modules has no side effects. The API lifespan still builds services at startup (fail fast). Full FastAPI `Depends` injection was not adopted: every caller already uses the accessors and tests monkeypatch them.
- [x] **L-5 Row-by-row inserts.** Fixed: `executemany` in `save_chunks` and `PgVectorStore.index`; verified on real Postgres by `make celery-integration-test`.
- [x] **L-6 Docker dependency source.** Fixed: images built from `uv.lock` (`backend/requirements.txt` removed), backend `runtime`/`test` targets, Streamlit/requests moved to a `frontend` dependency group (local `uv sync` unchanged via `default-groups`), Python `3.13.14-slim`, uv `0.11.14`, `ollama/ollama:0.30.10` (same digest as the cached `latest`).
- [x] **L-7 Misleading support-check reason.** Fixed with M-13: a deliberate refusal
  now reports `answer_declined` instead of `citation_mapping_failed`.
- [x] **L-8 Compose duplication.** Fixed with H-4: backend and worker share the
  `x-app-environment` YAML anchor.
- [x] **L-9 Fragile frontend CSS.** Fixed: the generated CSS class is gone; sidebar cards use `st.container(border=True, gap="xsmall")`. Also replaced the deprecated `use_container_width`.
- [x] **L-10 Phase 5 UI gap.** Fixed: four clickable sample questions (one deliberately unanswerable) fill the question box; covered by `test_frontend_smoke.py`.
- [x] **L-11 Label honesty.** Fixed: the UI metric is "Field completeness" with a tooltip saying it is deterministic, not a model confidence.
- [x] **L-12 Small config/message gaps.** Fixed: settings reject `CHUNK_OVERLAP_TOKENS >= CHUNK_SIZE_TOKENS` (tested); the generator error mentions Ollama.
- [x] **L-13 Model label comes from settings, not the client.** Fixed with L-2: metrics use the client's `model_name` (tested).

---

## Checked And Ruled Out

- `"office"` in the answerer's `STOPWORDS` looked tuned to the "Singapore office"
  negative question. Removing it leaves the offline eval unchanged
  (hit@5 1.0, rejection 0.8), so it is not overfitting.
- The citation placeholder bytes are `<cite index="N">` in code, prompts and docs
  alike. There is no mismatch.

## Self-review addendum (2026-10-02)

A critical pass over the whole uncommitted change set found these defects in the
fixes themselves. All fixed, with tests.

| Area | Defect in the earlier fix | Fix |
|---|---|---|
| H-3 startup recovery | The lifespan hook queried the database unguarded, so with `VECTOR_STORE_BACKEND=postgres` an unreachable database stopped the API from starting, defeating `/ready`. | Recovery is best effort: failures are logged (`interrupted_document_recovery_failed`) and startup continues. |
| H-1 numeric grounding | `NUMBER_RE` read a dotted date `12.05.2026` as `12.05` and `2026`, so an answer rewording it as `12 May 2026` was falsely rejected. | `numeric_values` splits dotted dates into day, month and year, like ISO and slashed dates. |
| M-6 heading skip | The answerer skipped every all-caps line as a heading, including value lines such as `TOTAL AMOUNT DUE: EUR 12,450.00`. | Lines that carry a digit are never skipped as headings. |
| L-5 executemany | Dedenting the pgvector insert SQL left its column list misaligned. | Re-indented; no behaviour change. |
| M-13 / M-10 typing | `info: object` and `table: object` hid the real types. | `ValidationInfo` and a `TYPE_CHECKING` import of `docx.table.Table`. |

| M-7 metrics labels | A relevance-gate refusal (no answerer ran) was labelled `offline-heuristic` with estimated tokens. | `model_name: null`, zero tokens, `token_usage_source: "none"`; the UI shows no model. |

| L-3 worker | `worker/worker.py` kept hardcoded 240/300 s app-wide Celery limits that only the chord errback used. | Taken from the same settings as the per-task limits. |
| Config docs | The four timeout variables Ollama mode depends on were missing from `.env.example`. | Documented there. |

The offline evaluation snapshot is unchanged by these fixes.

