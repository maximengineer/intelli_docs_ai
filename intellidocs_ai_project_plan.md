# IntelliDocs AI — Project Plan

Version: pragmatic portfolio build plan

## 1. Purpose

IntelliDocs AI is a portfolio project designed to demonstrate practical, production-style AI engineering for document-heavy business workflows.

The goal is not to build a huge enterprise AI platform. The goal is to build a clean, finished, demoable product that proves strong AI engineering judgment.

IntelliDocs AI should show that the developer can:

- build useful GenAI features
- work with documents, extraction, summarisation and RAG
- design reliable backend workflows
- implement source-grounded answers with trustworthy citations
- measure quality with a small evaluation set
- explain privacy, reliability and production trade-offs clearly

The project should feel finished, not over-scoped.

## 2. One-Sentence Pitch

IntelliDocs AI helps business users upload documents, extract key information, generate summaries and ask source-grounded questions with backend-verified citations and measurable AI quality.

## 3. Core Positioning

This project should communicate:

> I can take a GenAI idea from prototype to a useful, measurable, production-style application.

It should not communicate:

> I tried to build a full enterprise AI platform and left half of it unfinished.

## 4. Target Audience

### Potential Employer

They should quickly see:

- a clear business problem
- a working product
- business value
- clean user flow
- practical AI skills
- ability to ship

### Senior AI Engineer

They should see:

- clean architecture
- sensible scope decisions
- no fake metrics
- deterministic citation mapping
- async processing where it matters
- evaluation and observability
- honest limitations

## 5. Business Problem

Business teams often work with large volumes of documents:

- contracts
- invoices
- reports
- support tickets
- marketing documents
- internal policies

Common problems:

- manual review is slow
- search is unreliable
- key facts are hard to find
- summaries are inconsistent
- AI answers are hard to trust without sources
- quality and failure modes are hard to measure

IntelliDocs AI solves this by providing a small but complete document intelligence workflow.

## 6. Build Strategy

The project should be built in phases.

Do not start by implementing every senior-level feature.

### Phase 1: Working AI Product

Goal: a complete vertical slice that can be demoed.

Features:

- upload documents
- parse TXT, DOCX and digital-native PDF
- extract key fields
- generate document summaries
- ask questions over documents
- return answers with backend-mapped citations
- run a small evaluation script
- provide a clear README and demo script

This phase proves product value.

### Phase 2: Senior Engineering Proof

Goal: show production-style thinking without overbuilding.

Features:

- asynchronous document processing
- PostgreSQL with pgvector
- document status endpoint
- structured logs with run IDs
- reranking
- basic privacy handling
- cost estimation from token logs
- Alembic migrations
- content-hash deduplication
- extraction confidence hard gates

This phase proves engineering maturity.

### Phase 3: Production-Style Hardening

Goal: add polish only after the core demo is strong.

Features:

- Celery group/chord concurrency
- Streamlit streaming Q&A or lightweight streaming UI
- advanced privacy policy with raw/AI/display text variants
- richer RAG evaluation
- optional Langfuse/Phoenix tracing
- human review UI
- AWS deployment notes
- semantic cache as a carefully documented experiment

This phase proves architecture awareness.

### Phase 4: Durable Async Workflow

Status: implemented and Docker integration verified.

Goal: turn the Phase 3 async scaffolding into a real durable workflow without
turning IntelliDocs AI into an unfinished enterprise platform.

This phase exists because Phase 3 deliberately keeps document metadata and
status in process memory while adding Redis/Celery wiring, branch statuses and
async evaluation. Phase 4 should close that architectural gap before adding new
product features.

Features:

- durable document metadata, status, processing steps and branch state
- durable extracted fields, summaries, confidence flags and processing errors
- durable upload storage with task-safe storage keys
- real Celery dispatch behind a feature flag
- Celery chain/chord fan-out after parsing/privacy/chunking
- worker-driven branch status updates
- persisted evaluation run history
- Redis/Celery/Postgres smoke verification outside the fast unit-test gate
- packaging cleanup so local worker commands do not require fragile import setup

Non-goals:

- full enterprise document management
- authentication and role-based access control
- multi-tenant isolation
- semantic cache
- Langfuse/Phoenix integration
- human review workflow
- RAGAS/DeepEval-based scoring
- cloud deployment automation

Those can be later experiments, but they should not block the durable async
workflow.

This phase proves production workflow judgment: durable state first, distributed
workers second, advanced polish later.

Remaining Phase 4 polish: run the committed `make celery-integration-test`
target regularly in the Docker environment; keep it outside the fast hermetic
gate.

### Phase 5: Demo Polish And Portfolio Readiness

Status: in progress.

Goal: make IntelliDocs AI easy to review, demo and explain after the core
engineering work is complete.

Phase 5 should not add another infrastructure layer. The project already proves
the core AI/product and production-style engineering claims. This phase should
make those claims obvious to a reviewer through a polished demo flow, clear docs
and honest evaluation evidence.

Features:

- Streamlit UX polish for the upload -> extract -> ask -> cite -> evaluate flow
- curated synthetic sample documents and sample questions
- final demo script with exact Docker commands and talking points
- dated evaluation snapshot from the synthetic dataset
- README polish, architecture summary and limitations review
- resume bullets tied to implemented, verified behavior

Non-goals:

- authentication and user accounts
- multi-tenant access control
- human review workflow
- Langfuse/Phoenix
- semantic cache
- RAGAS/DeepEval
- cloud deployment automation
- new database tables unless required by a polishing bug

This phase proves product judgment: a finished, understandable demo beats a
larger but harder-to-review platform.

## 7. Recommended MVP

The MVP should be smaller than the full architecture.

### MVP Must Have

- FastAPI backend
- simple Streamlit UI
- document upload
- TXT, DOCX and digital-native PDF parsing
- document summary
- key field extraction
- RAG question answering
- deterministic citation mapping
- small evaluation dataset
- offline evaluation script
- Docker Compose
- clean README
- demo script
- honest limitations

### MVP Should Have

- asynchronous processing with one background worker task
- PostgreSQL with pgvector
- source snippets in citations
- basic structured logs
- simple privacy redaction for emails, phones and account-like numbers
- `run_id` in Q&A responses
- insufficient-information fallback

### MVP Can Skip Initially

- Celery chord
- SSE token streaming
- semantic caching
- advanced human review UI
- Langfuse/Phoenix
- AWS deployment
- complex multi-agent workflows
- full enterprise security model

## 8. Architecture Principles

Use these principles throughout the project:

- build a working vertical slice first
- make Docker Compose the primary runtime and verification target
- prefer explicit readable code over unnecessary frameworks
- avoid over-engineering
- do not fake metrics
- do not claim full production readiness
- keep citations backend-enforced
- make limitations visible
- test core trust features
- keep the demo simple and reliable

## 8.1 Docker-First Development And Testing

Local host tooling can vary too much across machines, especially with
PostgreSQL, pgvector, Redis, Celery, FastAPI and Streamlit all involved.
IntelliDocs AI should therefore treat Docker Compose as the source of truth for
running and verifying the application.

Required Compose services:

- `postgres`: PostgreSQL with pgvector.
- `redis`: Celery broker/result backend.
- `backend`: FastAPI app.
- `worker`: Celery worker service.
- `frontend`: Streamlit UI.
- `tests`: deterministic offline test runner.
- `live-tests`: opt-in provider/API-key smoke runner.

Testing tiers:

- Default tests must run offline, deterministically and without API keys:

```bash
docker compose --profile test run --rm tests
```

- Evaluation and migration checks should also run in containers:

```bash
docker compose --profile test run --rm tests python scripts/run_evaluation.py
docker compose --profile test run --rm tests alembic upgrade head --sql
```

- Live provider testing should be opt-in and allowed to use `.env`:

```bash
docker compose --profile live-test run --rm live-tests
```

Live tests may incur provider cost and can be non-deterministic. They are for
smoke-testing configured API keys and provider-backed paths, not for the normal
fast test gate.

## 9. Product Workflow

### MVP Workflow

1. User uploads a document.
2. Backend stores document metadata.
3. Background processing parses document text.
4. System extracts key fields.
5. System generates a summary.
6. System chunks and embeds document text.
7. User asks a question.
8. System retrieves relevant chunks.
9. System generates an answer using only retrieved context.
10. LLM emits citation placeholders such as `<cite index="0">`.
11. Backend maps placeholders to real citation metadata.
12. System returns answer, citations, metrics and `run_id`.

### Later Production-Style Workflow

1. Upload returns `202 Accepted`.
2. Worker processes documents asynchronously.
3. Branches can fan out after chunking.
4. Reranker improves context quality.
5. Support-check gate verifies risky answers.
6. Streaming UI shows progress.
7. Evaluation report tracks quality over time.

## 10. Critical Trust Features

### 10.1 Deterministic Citation Mapping

Do not ask the LLM to output database IDs, page numbers or chunk IDs.

Instead:

1. Backend passes context chunks as an ordered list.
2. LLM references context using `<cite index="0">`.
3. Backend maps the index to real metadata:
   - document ID
   - filename
   - page number
   - section title
   - chunk ID
   - snippet

This prevents citation hallucination.

### 10.2 Insufficient Information Fallback

The system must safely respond when documents do not contain the answer.

Response status:

```text
insufficient_information
```

Standard answer:

```text
The available documents do not contain enough information to answer this question.
```

### 10.3 No Fake Metrics

Metrics must be either measured or clearly marked as illustrative.

Do not invent:

- confidence scores
- cost estimates
- accuracy numbers
- production claims

## 11. Privacy Design

### MVP Privacy Handling

Use a simple, honest policy:

- redact emails
- redact phone numbers
- redact account-like numbers
- use synthetic documents only
- do not log raw sensitive content
- preserve organisation/vendor names for retrieval usefulness

### Later Privacy Hardening

Introduce three text variants:

- `raw_text`: original local text, temporary or retention-controlled
- `ai_text`: privacy-processed text for embeddings and LLM calls
- `display_text`: safe text for citations

Document the trade-off:

- redacting too much can reduce retrieval quality
- preserving organisation/vendor names improves search but may send those names to embedding providers

## 12. Retrieval and RAG

### MVP RAG

Use:

- structural chunking where practical
- embeddings
- pgvector or local vector store
- top-k retrieval
- answer generation from context
- backend-mapped citations

### Senior Add-On

Add:

- metadata filtering
- reranking
- configurable candidate count
- context chunk count
- evaluation metrics
- support-check gate

Recommended defaults:

```text
candidates_retrieved = 30
context_chunks_used = 5
```

## 13. Reranking

Reranking is valuable but not required for the first demo.

Use it after the basic RAG flow works.

If enabled:

- log whether reranking was on
- include reranker status in evaluation report
- make it configurable for CPU-only demo mode

```text
ENABLE_RERANKER=false
```

is acceptable for the first working version.

## 14. Support Check

The support check is defense-in-depth, not a perfect hallucination solution.

Do not run it on every query in the MVP.

Invoke it when:

- citations are missing
- retrieved context is weak
- reranker score is low
- the question is high-risk
- the answer appears unsupported

Use a smaller, cheaper model when possible.

## 15. Q&A UX

### MVP

A standard `/qa` endpoint is enough.

It returns:

- `run_id`
- answer
- citations
- status
- metrics

### Later Polish

Add `/qa/stream` for progress updates.

Important:

- do not stream unverified answer tokens before support check
- stream status first
- stream final accepted answer after verification

For Streamlit, use one of:

- `httpx.stream` generator with `st.write_stream`
- polling
- separate lightweight HTML/JS page for streaming

## 16. Document Processing Status

### MVP Status

Use simple document statuses:

```text
uploaded
processing
completed
failed
```

### Senior Version

Use document-level lifecycle:

```text
queued
parsing
privacy_processing
chunking
processing
completed
failed
```

Branch-level statuses are separate:

```text
embedding
classifying
extracting
summarising
```

Do not use a single document status to pretend multiple concurrent branches are sequential.

## 17. Evaluation Plan

### MVP Evaluation Dataset

Start small:

- 10 to 20 documents
- 20 normal questions
- 5 negative questions
- expected document IDs
- expected facts
- expected extracted fields

### MVP Metrics

Report:

- `document_hit_at_5`
- `unsupported_answer_rejection_rate`
- `citation_coverage`
- `extraction_field_accuracy`
- `average_latency_ms`

This is enough for the first version.

### Later Metrics

Add:

- context precision
- context recall
- answer faithfulness
- answer relevance
- RAGAS or DeepEval
- reranker on/off comparison

### Dataset Generation

Add:

```text
scripts/generate_eval_dataset.py
```

Suggested flow:

1. Generate candidate questions from synthetic documents using an LLM.
2. Manually review the generated data.
3. Commit reviewed JSONL files as the golden dataset.

## 18. Cost Tracking

Cost tracking is a nice production-style feature, but keep it simple.

### MVP

Log:

- model name
- input tokens
- output tokens
- estimated cost if available

### Later

Use a price table:

```text
model_name
input_price
output_price
as_of_date
```

For local models:

```text
API cost = $0.00
local compute cost is out of scope
```

## 19. File Upload Safety

Add basic upload guardrails:

- max file size
- allowed file extensions
- allowed MIME types
- safe filename handling
- parser timeout
- temporary file cleanup
- corrupt file handling

This is a small feature that shows production awareness.

## 20. Recommended Tech Stack

### MVP Stack

| Area | Choice |
|---|---|
| Backend | FastAPI |
| UI | Streamlit |
| Background Processing | Simple worker task or Celery task |
| Database | PostgreSQL |
| Vector Search | pgvector |
| Parsing | python-docx, pdfplumber/pymupdf4llm, TXT parser |
| LLM | OpenAI or local adapter |
| Embeddings | OpenAI embeddings or sentence-transformers |
| Schemas | Pydantic |
| Config | pydantic-settings |
| Tests | Pytest inside Docker Compose |
| Runtime / Verification | Docker Compose |
| Deployment | Docker image deployable to VPS or AWS |

### Later Add-ons

| Area | Choice |
|---|---|
| Worker Fan-out | Celery group/chord |
| Reranking | BGE/cross-encoder |
| Evaluation | RAGAS/DeepEval |
| Observability | Langfuse/Phoenix |
| Streaming | FastAPI StreamingResponse |
| Migrations | Alembic |

## 21. Repository Deliverables

Final repository should include:

- README.md
- CLAUDE.md
- docker-compose.yml
- Makefile
- `.env.example`
- backend code
- frontend demo
- backend and frontend Dockerfiles
- sample documents
- evaluation dataset
- offline evaluation script
- containerized offline test command
- opt-in live provider smoke test command
- demo script
- architecture docs
- limitations docs
- tests

## 22. Demo Script

A strong 3 to 5 minute demo:

1. Explain business problem.
2. Upload sample documents.
3. Show document summary and extracted fields.
4. Ask a question.
5. Show cited answer.
6. Ask unsupported question.
7. Show safe fallback.
8. Show evaluation report.
9. Show README architecture.
10. Explain limitations.

## 23. Resume Bullets After Completion

Use only after the project is actually built.

```text
Built IntelliDocs AI, an end-to-end AI document intelligence platform using Python, FastAPI, RAG, structured extraction and source-grounded Q&A.

Implemented document parsing, summarisation, field extraction and backend-verified citation mapping for business documents.

Created a small evaluation workflow to measure retrieval quality, citation coverage, unsupported-answer handling and extraction accuracy.

Added production-style design elements including asynchronous processing, structured logs, privacy-aware text handling and Docker-based local deployment.
```

## 24. What to Avoid

Avoid:

- building a generic PDF chatbot
- starting with too much infrastructure
- spending weeks on Celery before RAG works
- adding streaming before the core product works
- overbuilding privacy before the demo is useful
- fake confidence scores
- fake cost estimates
- unsupported benchmark claims
- overusing frameworks
- claiming enterprise readiness
- using real confidential data

## 25. Definition of Done

The project is successful when a reviewer can:

1. clone the repo
2. run it locally
3. upload sample documents
4. see summaries and extracted fields
5. ask questions
6. receive cited answers
7. see safe fallback for unsupported questions
8. run a small evaluation script
9. understand the architecture
10. understand the limitations
11. see how this maps to your CV

## 26. Final Positioning

The strongest version of IntelliDocs AI is not the biggest version.

The strongest version is a clean, finished, demoable AI product that proves:

- product sense
- AI engineering skill
- production awareness
- ability to finish
