# Evaluation

IntelliDocs AI keeps evaluation small, synthetic and repeatable. The committed
offline evaluator is not a benchmark; it is a smoke test for the demo contract.

## Metrics

- `document_hit_at_5`: expected document appears in retrieved context.
- `citation_coverage`: successful answers include at least one mapped citation.
- `unsupported_answer_rejection_rate`: negative questions receive the standard
  insufficient-information fallback.
- `support_check_pass_rate`: cited answers pass the backend support gate, which
  checks citation integrity (citations belong to retrieved context) **and**
  lexical grounding (the answer shares content tokens with its cited chunk text,
  so it can reject an answer that cites context it did not use). It is a
  grounding heuristic, not a semantic correctness score. Offline this is 1.0
  because the extractive answerer copies its sentences from the cited chunks.
- `extraction_field_accuracy`: expected fields match extracted fields.
- `average_latency_ms`: local end-to-end latency for the synthetic eval loop.

The report also includes dataset coverage fields:

- `documents_loaded`
- `questions_evaluated`
- `negative_questions_evaluated`
- `expected_extractions_evaluated`
- `retrieval_questions_scored`
- `extraction_rows_scored`
- `missing_expected_filenames`

These fields make dataset drift visible. A missing `expected_filenames` entry
should not silently disappear into an aggregate score.

## Running

Docker-first path:

```bash
make eval
```

Local iteration path:

```bash
ENABLE_LLM=false EMBEDDING_BACKEND=hash VECTOR_STORE_BACKEND=memory uv run python scripts/run_evaluation.py
```

The API also exposes the evaluator asynchronously:

```http
POST /evaluation/run            -> 202 {evaluation_id, status: "running"}
GET  /evaluation/{evaluation_id} -> {status, result}
```

The API run is always forced offline (deterministic, no paid LLM calls), since
the endpoint is unauthenticated. The evaluation loop uses isolated in-memory
document/vector storage even when the app is running in Docker/Postgres mode, so
sample evaluation documents do not pollute the main document store. Run metadata
and final results are persisted to Postgres when durable state is enabled, so
`GET /evaluation/{evaluation_id}` can retrieve completed runs after the worker
thread finishes.

## Generating Candidates

`scripts/generate_eval_dataset.py` can use the configured LLM provider to
bootstrap candidate evaluation rows from the synthetic sample documents:

```bash
ENABLE_LLM=true OPENROUTER_API_KEY=sk-or-... uv run python scripts/generate_eval_dataset.py
```

The script writes to `data/evaluation/generated_candidates/`, which is ignored by
Git. Generated rows are candidates only; manually review them before copying any
question or extraction row into the committed golden evaluation files.

## Current Snapshot

Measured on 2026-06-07 with Python 3.13, no API key, hash embeddings and the
deterministic extractive answerer:

```json
{
  "embedding_backend": "hash",
  "llm_enabled": false,
  "documents_loaded": 13,
  "questions_evaluated": 7,
  "negative_questions_evaluated": 5,
  "expected_extractions_evaluated": 8,
  "retrieval_questions_scored": 7,
  "extraction_rows_scored": 8,
  "missing_expected_filenames": [],
  "document_hit_at_5": 1.0,
  "citation_coverage": 1.0,
  "unsupported_answer_rejection_rate": 0.8,
  "support_check_pass_rate": 1.0,
  "extraction_field_accuracy": 1.0
}
```

Latency is intentionally omitted from the stable snapshot because it varies by
host, container cache and CPU load. The current measured value is shown in the
script output when `make eval` runs.

## Current Limitation

The offline lexical answerer still has a known false-positive mode on
keyword-dense but unsupported questions. That is why the rejection rate is below
1.0 and is documented instead of hidden.
