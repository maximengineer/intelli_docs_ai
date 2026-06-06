# Development Log

An honest, chronological record of engineering changes to IntelliDocs AI: what
changed, why, and how it was verified. Newest entries first. Metrics here are
local demo measurements on the synthetic dataset, not benchmark claims.

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
- **Storage:** in-memory (documents, chunks and vectors) — Phase 2 brings pgvector.
