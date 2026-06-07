# IntelliDocs AI Resume Bullets

Use these only for the behavior currently implemented and verified in the repo.

- Built IntelliDocs AI, a production-inspired document intelligence portfolio
  project using Python 3.13, FastAPI, Streamlit, Docker Compose, PostgreSQL with
  pgvector, Redis and Celery.
- Implemented upload-to-answer document workflows for TXT, DOCX and
  digital-native PDF files, including parsing, privacy redaction, chunking,
  summarisation, structured field extraction, embeddings and RAG Q&A.
- Designed backend-verified citation mapping where the LLM emits context
  indexes and the backend maps them to trusted document, page, chunk and snippet
  metadata, with safe refusal for invalid or unsupported evidence.
- Added deterministic offline fallbacks for generation and embeddings, so tests,
  CI and key-less demos run without external provider calls while live OpenRouter
  smoke tests remain opt-in.
- Built durable async processing with document status polling, branch-level
  processing state, PostgreSQL persistence and optional Celery/Redis fan-out.
- Created a small adversarial synthetic evaluation measuring document hit rate,
  citation coverage, unsupported-answer rejection, support-gate pass rate,
  extraction field accuracy and latency without claiming benchmark performance.
- Documented limitations and trade-offs honestly, including the lexical offline
  fallback's known false-positive mode and the project boundary between
  production-inspired portfolio code and a real enterprise platform.
