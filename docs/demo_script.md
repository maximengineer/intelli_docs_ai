# IntelliDocs AI Demo Script

Use this as the exact reviewer walkthrough. The default path is Docker-first and
runs without an API key.

## Setup

```bash
cp .env.example .env
make up
```

Open the Streamlit UI at `http://localhost:9999`.

If the host ports are already in use:

```bash
BACKEND_PORT=18000 FRONTEND_PORT=18501 make up
```

Optional live LLM path:

```bash
# in .env
ENABLE_LLM=true
OPENROUTER_API_KEY=sk-or-...
```

Then restart:

```bash
make restart
```

## Walkthrough

1. Upload `data/sample_documents/invoice_acme.txt`.
2. Show the processing status: sequential parse/privacy/chunk steps plus the
   parallel embedding, extraction and summary branches.
3. Show the summary and extracted fields. Point out that extraction confidence
   is a gate signal, not a fabricated certainty claim.
4. Upload `data/sample_documents/contract_northwind.txt`.
5. Ask: `Which invoice is above 10,000 EUR?`
6. Open the source expander and show that citations are backend-mapped from
   retrieved context, not model-invented chunk IDs.
7. Ask: `What are the renewal terms in the Northwind service agreement?`
8. Ask: `Which document mentions a Singapore office?`
9. Show the insufficient-information fallback and explain that unsupported
   questions return no supporting sources.

The Streamlit sample-question buttons intentionally match these uploaded
walkthrough documents. The broader synthetic corpus is exercised by the
evaluation command below.

## Evaluation

Run the deterministic offline evaluation in Docker:

```bash
make eval
```

For local iteration, the equivalent command is:

```bash
ENABLE_LLM=false EMBEDDING_BACKEND=hash VECTOR_STORE_BACKEND=memory uv run python scripts/run_evaluation.py
```

Talking point: the committed offline snapshot has an
`unsupported_answer_rejection_rate` below 1.0. That is intentional and honest:
the lexical fallback is fooled by one keyword-dense but unsupported question.
The project reports this rather than hiding it.

## Engineering Talking Points

- Docker Compose is the primary runtime path: FastAPI, Streamlit, Postgres 18
  with pgvector, Redis 8 and an optional Celery worker.
- The app remains demoable with no API key through deterministic offline
  fallbacks.
- All provider calls sit behind adapter interfaces, so tests do not make real
  LLM calls.
- Citations are validated and mapped by the backend. The model only chooses
  context indexes.
- The support-check gate refuses answers with invalid or unsupported citations.
- The evaluation is small, synthetic and adversarial; metrics are local demo
  measurements, not benchmark claims.

## Shutdown

```bash
make down
```
