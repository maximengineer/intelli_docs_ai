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

## Running

```bash
ENABLE_LLM=false EMBEDDING_BACKEND=hash VECTOR_STORE_BACKEND=memory uv run python scripts/run_evaluation.py
```

The API also exposes the evaluator asynchronously:

```http
POST /evaluation/run            -> 202 {evaluation_id, status: "running"}
GET  /evaluation/{evaluation_id} -> {status, result}
```

The API run is always forced offline (deterministic, no paid LLM calls), since
the endpoint is unauthenticated. Results are held in memory for the process
lifetime; a durable evaluation store is intentionally out of scope here.

## Current Limitation

The offline lexical answerer still has a known false-positive mode on
keyword-dense but unsupported questions. That is why the rejection rate is below
1.0 and is documented instead of hidden.
