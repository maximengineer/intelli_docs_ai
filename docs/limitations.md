# Limitations

IntelliDocs AI is a production-style portfolio implementation, not an enterprise-ready platform.

- Phase 1 uses in-memory document and vector storage, so data is lost when the backend restarts.
- AI runs through a provider adapter. With an `OPENROUTER_API_KEY` it uses real LLM generation/extraction and semantic embeddings; with no key it falls back to deterministic local implementations: hash (lexical, non-semantic) embeddings and an extractive, non-generative answerer.
- The offline extractive answerer has a known false-positive mode: on keyword-dense but unanswerable questions it can return a cited-but-irrelevant sentence instead of refusing. This is visible in the evaluation as an `unsupported_answer_rejection_rate` below 1.0. The LLM-backed path is designed to refuse these.
- The live OpenRouter path is exercised in tests via a mocked client; the committed evaluation snapshot is the offline backend only (the live path needs a key and is non-deterministic, so it is not committed as a fixed number).
- The evaluation does not score answer *correctness* (only retrieval hit, citation presence, unsupported-answer rejection and extraction field accuracy), so an answer that cites the wrong-but-plausible document is not penalised by these metrics.
- The parser timeout uses a worker thread; it returns control to the caller on timeout but cannot forcibly kill an already-running parse, so a pathologically slow parse can leave a background thread until it finishes.
- TXT, DOCX and digital-native PDF parsing are supported; scanned PDF OCR is out of scope.
- Upload safety is basic: file size (capped before fully buffering), extension, MIME type and parser timeout checks are implemented, but antivirus scanning is out of scope.
- Evaluation data is intentionally small and synthetic, and was manually reviewed before being committed.
- Metrics are measured by the local evaluation script and should not be treated as benchmark claims.
