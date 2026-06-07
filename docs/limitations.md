# Limitations

IntelliDocs AI is a production-style portfolio implementation, not an enterprise-ready platform.

- The default local development path is fully in-memory, so data is lost on restart. With `VECTOR_STORE_BACKEND=postgres`, document metadata, summaries, extracted fields, status, processing steps, chunks, embeddings and evaluation runs persist to PostgreSQL/pgvector and survive backend restarts.
- Docker Compose defaults to the thread upload path for demo reliability. `DOCUMENT_PROCESSING_BACKEND=celery` enables real Celery chain/chord dispatch through Redis, but the committed integration test is opt-in and requires a running Docker stack.
- The durable upload store is local filesystem storage for the Docker/local demo. A production deployment would replace it with object/blob storage and a retention policy.
- The Postgres repository and vector store currently open a fresh database connection per operation instead of using a connection pool. This is acceptable for the portfolio demo and smoke tests, but it is the obvious scaling limitation for heavier API/worker traffic.
- The pgvector schema uses a dimensioned `vector(POSTGRES_VECTOR_DIMENSION)` column (default 1536) with a matching HNSW cosine index. Docker uses hash embeddings sized to that configured pgvector dimension so the no-key demo works. For a real semantic embedding model, the dimension must match the active model; changing the embedding model requires updating the setting and running a new migration. Indexing rejects vectors whose length does not match, to fail fast on a mismatch.
- AI runs through a provider adapter. With an `OPENROUTER_API_KEY` it uses real LLM generation/extraction and semantic embeddings; with no key it falls back to deterministic local implementations: hash (lexical, non-semantic) embeddings and an extractive, non-generative answerer.
- The offline extractive answerer has a known false-positive mode: on keyword-dense but unanswerable questions it can return a cited-but-irrelevant sentence instead of refusing. This is visible in the evaluation as an `unsupported_answer_rejection_rate` below 1.0. The LLM-backed path is designed to refuse these.
- The live OpenRouter path is exercised in tests via a mocked client; the committed evaluation snapshot is the offline backend only (the live path needs a key and is non-deterministic, so it is not committed as a fixed number).
- The support-check gate verifies citation integrity and lexical grounding overlap: final answers must have mapped citations from retrieved context and share content tokens with cited chunks. It is not a semantic entailment checker, so a cited-but-wrong answer can still pass the gate.
- The evaluation does not deeply score answer *correctness* (only retrieval hit, citation presence, support-check pass rate, unsupported-answer rejection and extraction field accuracy), so an answer that cites the wrong-but-plausible document is only partially penalised by these metrics.
- Purpose-scoped privacy variants are produced by the redaction helper and the AI-processing text is persisted for worker branches. The service still does not persist a full enterprise-style set of separate `raw`, `ai_processing` and `display` variants.
- `STREAMING_ENABLED` is wired for `/qa/stream`; optional observability exporters are not integrated.
- The worker package imports cleanly in Docker and tests because `PYTHONPATH` includes `/app` and `/app/backend`. Plain local worker commands still need equivalent import paths unless the package layout is refactored further.
- Fast tests cover API shapes, status branches, support-gate contracts, repository behavior and worker task contracts. They do not launch Redis/Celery by default; the Celery/Postgres integration test is opt-in.
- The parser timeout uses a worker thread; it returns control to the caller on timeout but cannot forcibly kill an already-running parse, so a pathologically slow parse can leave a background thread until it finishes.
- TXT, DOCX and digital-native PDF parsing are supported; scanned PDF OCR is out of scope.
- Upload safety is basic: file size (capped before fully buffering), extension, MIME type and parser timeout checks are implemented, but antivirus scanning is out of scope.
- Evaluation data is intentionally small and synthetic, and was manually reviewed before being committed.
- Metrics are measured by the local evaluation script and should not be treated as benchmark claims.
