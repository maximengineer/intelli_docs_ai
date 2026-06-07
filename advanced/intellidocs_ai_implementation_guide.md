# IntelliDocs AI — Implementation Guide

Version: final staff-review revision

## 1. Goal

This guide describes how to implement IntelliDocs AI as a credible production-style AI document intelligence portfolio project.

The implementation should satisfy two audiences:

- potential employers who want to see business value and a clear demo
- senior/staff AI engineers who want to see reliable architecture, correct trade-offs, and implementation discipline

## 2. Canonical Repository Structure

```text
intellidocs-ai/
  README.md
  CLAUDE.md
  docker-compose.yml
  .env.example
  alembic.ini

  backend/
    app/
      main.py

      api/
        routes_health.py
        routes_documents.py
        routes_status.py
        routes_qa.py
        routes_evaluation.py

      core/
        settings.py
        logging.py
        errors.py
        task_queue.py

      documents/
        parser.py
        layout_parser.py
        privacy.py
        chunker.py
        classifier.py
        extractor.py
        summarizer.py
        confidence.py
        service.py
        schemas.py

      rag/
        embeddings.py
        vector_store.py
        retriever.py
        reranker.py
        generator.py
        critic.py
        citations.py
        cache.py
        service.py
        schemas.py

      llm/
        client.py
        prompt_registry.py
        schemas.py

      evaluation/
        datasets.py
        retrieval_eval.py
        rag_eval.py
        extraction_eval.py
        report.py

      observability/
        metrics.py
        run_logger.py

      storage/
        database.py
        models.py
        repositories.py

    tests/
      test_parser.py
      test_privacy.py
      test_chunker.py
      test_confidence.py
      test_retriever.py
      test_reranker.py
      test_extractor.py
      test_critic.py
      test_citations.py
      test_costing.py
      test_api_documents.py
      test_api_qa.py
      test_streaming.py

    Dockerfile
    requirements.txt

  worker/
    worker.py
    tasks.py

  frontend/
    streamlit_app.py

  prompts/
    classify_document.yaml
    extract_fields.yaml
    summarize_document.yaml
    answer_question.yaml
    support_check.yaml

  data/
    sample_documents/
    evaluation/
      questions.jsonl
      expected_extractions.jsonl
      negative_questions.jsonl

  docs/
    architecture.md
    privacy.md
    evaluation.md
    demo_script.md
    limitations.md

  migrations/
    versions/

  scripts/
    generate_eval_dataset.py
    ingest_sample_data.py
    run_evaluation.py
    seed_database.py
```

Notes:

- Use `core/settings.py` as the only home for `pydantic-settings`.
- Keep prompts outside Python business logic.
- Keep `llm/` as a provider-adapter layer.
- Include citation and streaming tests because these are trust and UX features.

## 3. Tech Stack

| Area | MVP Choice |
|---|---|
| Backend | FastAPI |
| Worker | Celery + Redis |
| Fan-out | Celery group/chord |
| UI | Streamlit |
| Q&A streaming | FastAPI StreamingResponse consumed by Streamlit generator |
| DB | PostgreSQL |
| Vector Search | pgvector |
| Migrations | Alembic |
| Parsing | TXT, DOCX, digital-native PDF with layout-aware parser |
| LLM | OpenAI adapter or local adapter |
| Embeddings | OpenAI embeddings or sentence-transformers |
| Reranker | cross-encoder/BGE reranker or configurable no-op in fast mode |
| Config | pydantic-settings |
| Testing | Pytest |
| Evaluation | offline script, RAGAS/DeepEval optional |
| Deployment | Docker Compose |

## 4. Configuration

Use `pydantic-settings`.

Example settings:

```text
DATABASE_URL
REDIS_URL
OPENAI_API_KEY
LLM_MODEL
LLM_MODEL_VERSION
CRITIC_MODEL
CRITIC_MODEL_VERSION
EMBEDDING_MODEL
EMBEDDING_MODEL_VERSION
EMBEDDING_DIMENSION
PGVECTOR_DISTANCE_METRIC
PGVECTOR_INDEX_TYPE
RERANKER_MODEL
ENABLE_RERANKER
CRITIC_MODE
CRITIC_RERANKER_THRESHOLD
PII_POLICY_VERSION
PARSER_VERSION
COST_PRICE_TABLE_PATH
ENABLE_SEMANTIC_CACHE
RAW_TEXT_RETENTION_MODE
LOG_LEVEL
```

Do not use `os.getenv()` directly in business logic.

## 5. API Design

### 5.1 Liveness

```http
GET /health
```

Returns process liveness only.

### 5.2 Readiness

```http
GET /ready
```

Checks:

- PostgreSQL
- Redis
- pgvector extension
- required config

### 5.3 Upload Document

```http
POST /documents/upload
```

Must return:

```text
202 Accepted
```

Response:

```json
{
  "document_id": "doc_123",
  "task_id": "task_456",
  "status": "queued"
}
```

The endpoint must not parse, embed, or call LLMs synchronously.

### 5.4 Document Status

```http
GET /documents/{document_id}/status
```

During concurrent fan-out, document-level status is `processing`.

Example:

```json
{
  "document_id": "doc_123",
  "status": "processing",
  "needs_review": false,
  "steps": [
    {"name": "parsing", "status": "completed"},
    {"name": "privacy_processing", "status": "completed"},
    {"name": "chunking", "status": "completed"},
    {"name": "embedding", "status": "running"},
    {"name": "classifying", "status": "running"},
    {"name": "extracting", "status": "running"},
    {"name": "summarising", "status": "running"}
  ]
}
```

Do not set document-level status to `embedding` when other parallel branches are also running.

### 5.5 Get Document

```http
GET /documents/{document_id}
```

Returns final classification, extraction, summary, citations, and review status.

### 5.6 Ask Question: Streaming

Preferred for UI:

```http
POST /qa/stream
```

Use FastAPI `StreamingResponse`.

Ordering rule:

- stream status updates immediately
- generate answer server-side
- map citations
- run support check if gate triggers
- only then stream final accepted answer text
- emit final event with sources, metrics, and `run_id`

Example events:

```text
event: status
data: {"status": "retrieving", "run_id": "run_123"}

event: status
data: {"status": "reranking", "run_id": "run_123"}

event: status
data: {"status": "generating", "run_id": "run_123"}

event: status
data: {"status": "verifying", "run_id": "run_123"}

event: token
data: {"text": "Two invoices"}

event: final
data: {"run_id": "run_123", "sources": [...], "metrics": {...}, "status": "success"}
```

A non-streaming `POST /qa` may exist for tests and simple API demos.

### 5.7 Ask Question: Success Response Shape

```json
{
  "run_id": "run_123",
  "answer": "Two invoices are above 10,000 EUR.",
  "sources": [
    {
      "document_id": "doc_123",
      "filename": "invoice_001.pdf",
      "page_number": 2,
      "section_title": "Line Items",
      "chunk_id": "chunk_004",
      "snippet": "Total amount: EUR 12,450..."
    }
  ],
  "metrics": {
    "latency_ms": 2410,
    "candidates_retrieved": 30,
    "context_chunks_used": 5,
    "estimated_cost_usd": 0.0021,
    "price_table_as_of": "2026-06-01"
  },
  "status": "success"
}
```

Metric values in examples are illustrative response shapes, not claimed benchmark results.

### 5.8 Ask Question: Insufficient Information Shape

```json
{
  "run_id": "run_124",
  "answer": "The available documents do not contain enough information to answer this question.",
  "sources": [],
  "retrieved_context": [
    {
      "document_id": "doc_123",
      "filename": "policy_001.pdf",
      "page_number": 1,
      "chunk_id": "chunk_007"
    }
  ],
  "metrics": {
    "latency_ms": 1800,
    "candidates_retrieved": 30,
    "context_chunks_used": 5,
    "estimated_cost_usd": 0.0012,
    "price_table_as_of": "2026-06-01"
  },
  "status": "insufficient_information"
}
```

Retrieved context may be returned for debugging, but it must not be presented as supporting citation evidence.

### 5.9 Evaluation

Recommended MVP:

```bash
python scripts/run_evaluation.py
```

Optional API:

```http
POST /evaluation/run
```

If implemented, it must return `202 Accepted` with `evaluation_id`.

Results:

```http
GET /evaluation/{evaluation_id}
```

Do not run multi-question LLM evaluation synchronously inside an HTTP request.

## 6. Database Model

### Document

```text
document_id
filename
file_type
content_hash
uploaded_at
status
needs_review
task_id
document_type
summary
processing_error
parser_version
privacy_policy_version
embedding_model_name
embedding_model_version
```

### ProcessingStep

```text
step_id
document_id
step_name
status
started_at
finished_at
latency_ms
attempt_count
error_type
error_message
is_critical
```

### Chunk

```text
chunk_id
document_id
chunk_index
raw_text_ref
ai_text
display_text
token_count
page_number
section_title
is_table
embedding
embedding_model_name
embedding_model_version
embedding_dimension
embedding_created_at
metadata_json
```

Notes:

- `raw_text_ref` can point to temporary/local storage or be null if raw text is discarded.
- Do not persist full raw text forever without a documented retention policy.

### QueryRun

```text
run_id
question
normalized_question
answer
document_filter_json
cache_scope_key
candidate_chunk_ids
context_chunk_ids
citation_placeholders_json
mapped_citations_json
latency_ms
estimated_cost_usd
price_table_as_of
model_name
critic_model_name
embedding_model_name
embedding_model_version
status
created_at
error_message
critic_invoked
critic_supported
```

### ModelCall

```text
model_call_id
run_id
purpose
model_name
model_version
prompt_version
input_tokens
output_tokens
estimated_cost_usd
latency_ms
status
created_at
```

### EvaluationResult

```text
evaluation_id
dataset_name
status
document_recall_at_k
document_hit_at_k
context_precision
context_recall
answer_relevance
faithfulness
citation_coverage
unsupported_answer_rejection
extraction_accuracy
average_latency_ms
failure_rate
reranker_enabled
embedding_model_version
created_at
completed_at
```

## 7. Asynchronous Processing and Celery DAG

Use Celery + Redis for MVP.

Worker flow:

```text
process_document(document_id):
  set document.status = parsing
  parse document

  set document.status = privacy_processing
  create raw_text, ai_text, display_text according to privacy policy

  set document.status = chunking
  create structural chunks

  set document.status = processing

  run Celery group/chord:
    - embed_chunks(document_id)
    - classify_document(document_id)
    - extract_fields(document_id)
    - summarize_document(document_id)

  aggregate_document_results(document_id):
    - inspect branch statuses
    - store final summary/extraction/classification
    - set completed / failed
    - set needs_review when required
```

Do not use `asyncio.gather` inside Celery prefork workers.

If switching to ARQ later, use ARQ-native async tasks and `asyncio.gather`.

### Failure Semantics

Critical branch failures:

- embedding fails after retries -> document `failed`
- parsing/privacy/chunking fails -> document `failed`

Reviewable branch failures:

- extraction fails validation -> `completed`, `needs_review = true`
- summarisation fails -> `completed`, `needs_review = true`
- classification ambiguous -> `completed`, `needs_review = true`

Chord errback must mark the document as failed or review-needed rather than leaving it stuck in `processing`.

## 8. Parsing

MVP supports:

- TXT
- DOCX
- digital-native PDF

Out of scope:

- scanned PDF OCR

Parser output should preserve:

- page number if available
- headings
- sections
- tables
- reading order
- line items

Prefer Markdown-like intermediate representation.

## 9. Privacy Processing

### Text Variants

Create three variants:

1. `raw_text`
   - original text
   - local-only during processing by default
   - discarded or stored with retention policy

2. `ai_text`
   - privacy-processed text
   - used for embeddings and external LLM calls

3. `display_text`
   - safe citation text
   - shown to users

### Default Privacy Policy

Redact before external calls:

- emails
- phone numbers
- bank accounts
- tax IDs
- national IDs
- credit-card-like numbers
- sensitive personal identifiers

Preserve by default for retrieval usefulness:

- organization names
- vendor names
- contract party names

State clearly that preserved names may be sent to external embedding providers when external embeddings are used.

## 10. Chunking

Use structural chunking.

Rules:

- split by headings/sections first
- keep tables intact where possible
- keep invoice line items together
- keep contract clauses together
- apply token limits after structural splitting
- include metadata on every chunk

Avoid destroying table rows.

## 11. Embeddings and pgvector

When embedding:

- use configured embedding model
- store model name and version
- store dimension
- use query embedding with matching model version
- do not mix incompatible embedding versions in retrieval

Document:

- vector dimension
- distance metric
- index type
- operator class

Example:

```text
embedding_model = text-embedding-3-small
embedding_dimension = 1536
distance_metric = cosine
operator_class = vector_cosine_ops
index_type = hnsw
```

Changing embedding dimension requires a database migration, not only re-indexing.

Evaluation reports must state:

- embedding model/version
- reranker enabled/disabled
- index/search mode if relevant

## 12. Corpus Scope and Cache Key

Compute cache scope key:

```text
cache_scope_key = hash(
  embedding_model_name,
  embedding_model_version,
  sorted(document_ids matching active filter),
  prompt_version,
  generation_model_version,
  privacy_policy_version
)
```

Exact-normalized cache key:

```text
normalized_question
canonical_document_filter_json
cache_scope_key
```

Normalization should be conservative:

- lowercase
- trim
- collapse whitespace
- normalize Unicode
- canonicalize JSON filter ordering

Do not strip semantically significant numbers, negations, or comparison operators.

## 13. Retrieval

RAG retrieval steps:

1. Normalize question.
2. Compute cache scope key.
3. Embed query with matching embedding model version.
4. Apply metadata filters.
5. Retrieve candidate chunks.
6. Rerank candidates.
7. Select context chunks.
8. Generate answer with citation placeholders.
9. Backend maps citations deterministically.
10. Run support check if gate triggers.
11. Return answer with citations or fallback.

### Metadata Filtering

Use filters such as:

- document type
- document ID
- upload date
- embedding model version
- review status

For demo scale, exact vector search with metadata filters is acceptable.

For larger scale, document the sharp edges:

- selective filters can reduce ANN recall
- planner may choose exact scan
- partial indexes may be needed
- over-fetching may be needed

## 14. Reranking

Recommended default:

```text
candidates_retrieved = 30
context_chunks_used = 5
```

Make this configurable.

For CPU-only demo environments, allow fast mode:

```text
ENABLE_RERANKER=false
```

If disabled, state it in logs, README, and evaluation report.

## 15. Answer Generation and Citation Placeholders

### Prompt Context Format

Pass context chunks as an enumerated list:

```text
[0] filename: invoice_001.pdf, page: 2, section: Line Items
Text: Total amount: EUR 12,450...

[1] filename: invoice_002.pdf, page: 1, section: Summary
Text: Total amount: EUR 8,200...
```

### LLM Citation Rule

Instruct the LLM:

```text
Use citation tags such as <cite index="0"> to reference the provided context.
Do not invent document IDs, chunk IDs, filenames, or page numbers.
Use only indexes from the context list.
```

### Backend Mapping Logic

1. Parse `<cite index="X">` tags.
2. Validate X is within context array bounds.
3. Replace or enrich citation tags with actual metadata:
   - document ID
   - filename
   - page number
   - section title
   - chunk ID
   - snippet
4. If citation index is invalid, mark answer as needing review or fallback.

## 16. Streaming and Verification

Default safe ordering:

```text
retrieve -> rerank -> generate full answer server-side -> map citations -> support-check if needed -> stream answer text -> final event
```

Do not stream unverified answer tokens before the support decision.

If provisional streaming is later implemented, the UI must clearly mark text as provisional and remove it if verification fails.

## 17. Support Check

Treat critic as defense-in-depth, not perfect hallucination prevention.

### Heuristic Gate

Do not run critic on every query by default.

Invoke critic when:

- top reranker score or score margin is weak
- context coverage is weak
- no citation placeholders are produced
- user asks high-risk legal/financial/compliance question
- answer contains claims not obviously tied to cited chunks

Thresholds must be tuned using the evaluation set and revisited if the reranker changes.

### Model Selection

Use smaller, faster, cheaper model for critic checks.

Do not use the expensive primary generation model for routine verification.

### Structured Critic Output

Ask for:

```json
{
  "supported": true,
  "unsupported_claims": [],
  "justification": "The answer is supported by context chunks 0 and 1."
}
```

Validate with Pydantic.

If unsupported:

```text
The available documents do not contain enough information to answer this question.
```

Include critic model call in cost estimation when invoked.

## 18. Classification

MVP:

- few-shot LLM classification
- constrained enum
- Pydantic validation
- low temperature to reduce variance

Do not claim deterministic output from temperature alone.

Classic ML classifier is optional future work only if backed by a real evaluation set.

## 19. Extraction

Use structured outputs and Pydantic validation.

Do not parse LLM JSON with regex.

For extraction tasks:

- low temperature reduces variance
- tests should not assume bit-exact natural language output
- tests should assert schema validity and value constraints

## 20. Extraction Confidence

Define confidence as a derived review heuristic.

Hard gates:

- schema invalid -> `needs_review = true`
- required fields missing -> `needs_review = true`
- critical plausibility check fails -> `needs_review = true`

Example score:

```text
required_field_completeness = required_present / required_total
value_plausibility_score = checks_passed / checks_total
source_support_score = values_supported / values_checked
optional_field_quality = optional_present / optional_total

confidence =
  0.40 * required_field_completeness
+ 0.20 * value_plausibility_score
+ 0.25 * source_support_score
+ 0.15 * optional_field_quality
```

`source_support_score` should use normalized/fuzzy matching against local source text by default.

If an LLM judge is used, log it as a model call and include it in cost.

## 21. Cost Estimation

Use a config price table.

Compute cost from actual logged token counts.

Sum all model calls in a run:

- classification
- extraction
- summarisation
- answer generation
- support check if invoked
- evaluation calls if applicable

Show:

- `estimated_cost_usd`
- `price_table_as_of`

For local models, show API cost as `$0.00` by design and document that compute cost is out of scope.

## 22. Evaluation

### Dataset Generation Strategy

Do not write the golden dataset entirely by hand.

Add:

```text
scripts/generate_eval_dataset.py
```

Suggested flow:

1. Use synthetic sample documents.
2. Use a strong LLM to generate candidate questions, expected facts, and negative questions.
3. Manually verify expected facts against the source documents.
4. Prefer a different judge model from the generation model where practical.
5. Commit reviewed JSONL files as the golden dataset.

### Dataset Schema

`questions.jsonl`:

```json
{
  "question_id": "q_001",
  "question": "Which contracts mention automatic renewal?",
  "expected_document_ids": ["doc_001"],
  "expected_facts": ["automatic renewal", "12 months"],
  "expected_response_type": "answer"
}
```

`negative_questions.jsonl`:

```json
{
  "question_id": "nq_001",
  "question": "Which document mentions a Singapore office?",
  "expected_response_type": "insufficient_information"
}
```

`expected_extractions.jsonl`:

```json
{
  "document_id": "doc_001",
  "expected_fields": {
    "company_name": "Example Ltd",
    "risk_level": "medium"
  }
}
```

If claiming chunk-level retrieval, add expected chunk IDs. Otherwise claim document-level retrieval only.

### Metrics

Recommended:

- `document_recall_at_k`
- `document_hit_at_k`
- context precision
- context recall
- answer relevance
- faithfulness
- citation coverage
- unsupported answer rejection
- extraction schema validity
- extraction field accuracy

## 23. Caching

MVP:

Use exact normalized cache only.

Cache key includes:

- normalized question
- canonical document filter JSON
- cache scope key

Semantic caching is Could-Have and must be conservative.

Do not use a bare cosine threshold like 0.95 as a production claim.

## 24. Streamlit Integration

Streamlit does not automatically consume SSE.

Implementation options:

- use `httpx.stream` inside a generator and connect it to `st.write_stream`
- use polling for status and final answer if streaming is deferred
- use a small HTML/JS page for Q&A streaming while Streamlit handles upload/status

Document the chosen path in README.

## 25. Testing

### LLM Tests

Do not rely on real external LLM calls in unit tests.

Use:

- mocks
- `respx`
- `vcrpy`
- provider adapter interfaces

Snapshot tests can be used for:

- prompt assembly
- structured request payloads
- parsed structured outputs

Do not snapshot raw free-form LLM text as a brittle correctness test.

### Unit Tests

Include:

- parser tests
- privacy tests
- chunker tests
- confidence hard-gate tests
- cost estimation tests
- cache scope key tests
- retriever filter tests
- reranker tests
- citation mapping tests
- critic gate tests
- settings tests

### Integration Tests

Include:

- upload returns 202
- worker processes document
- status endpoint shows document-level `processing` plus branch statuses
- QA stream emits status events
- QA returns backend-mapped citations
- unsupported question returns fallback shape
- evaluation script produces report

## 26. Migrations

Use Alembic.

Changing embedding dimension requires a schema migration.

Avoid relying on `create_all()` for anything beyond a throwaway demo.

## 27. Duplicate Uploads

Compute file content hash.

Recommended dedupe key:

```text
content_hash
embedding_model_name
embedding_model_version
privacy_policy_version
parser_version
```

If exact same processing scope already exists, return existing document record.

If user explicitly forces reprocess, create a new processing record.

## 28. Financial Review Thresholds

If `needs_review` is triggered by amount thresholds:

- specify currency
- normalize amounts where possible
- or use currency-specific thresholds

Unknown currency should trigger review.

## 29. Observability

Use structured logs.

Log:

- run ID
- document ID
- task ID
- document status
- branch statuses
- latency
- candidates retrieved
- context chunks used
- citation placeholder count
- mapped citation count
- critic invoked
- estimated cost
- price table date
- cache scope key

Example values are illustrative.

## 30. Security

Use synthetic documents only.

Do not log raw sensitive content.

Document production requirements:

- auth
- access control
- audit logs
- encryption
- permission-aware retrieval
- retention policy
- PII policy review

## 31. Performance Assumptions

Document demo assumptions:

- CPU-only Docker demo may be slower
- reranking 30 candidates is safer than 50 for local machines
- support check is gated to avoid doubling every query
- OCR is out of scope
- sample PDFs are digital-native
- metrics are from synthetic small-N data unless otherwise stated

## 32. Definition of Done

The project is complete when a reviewer can:

1. clone the repo
2. run Docker Compose
3. upload TXT, DOCX, or digital-native PDF
4. see async processing status
5. see document-level `processing` and branch statuses
6. see classification, extraction, and summary
7. ask questions through streaming UI
8. receive backend-mapped citations
9. ask unsupported questions and receive safe fallback
10. run evaluation offline
11. inspect logs using `run_id`
12. understand privacy policy and raw text retention
13. understand limitations
14. explain business value in under 2 minutes
