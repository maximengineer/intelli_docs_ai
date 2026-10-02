# Evaluation

IntelliDocs AI keeps evaluation small, synthetic and repeatable. The committed
offline evaluator is not a benchmark; it is a smoke test for the demo contract.

## Metrics

- `document_hit_at_5`: expected document appears in retrieved context.
- `citation_coverage`: share of answerable questions that received a cited
  `success` answer. Refusals count against it. (Before 2026-10-02 it was computed
  over successful answers only, which is 1.0 by construction because `/qa` never
  returns `success` without sources.)
- `answer_fact_recall`: share of each question's `expected_facts` found verbatim
  (case- and whitespace-insensitive) in the answer, averaged over answerable
  questions; refusals score 0. This is the closest thing to an answer-correctness
  check, and it is strict: a correct paraphrase that does not contain the fact
  string scores 0.
- `first_citation_document_accuracy`: share of answerable questions whose first
  citation comes from an expected document. It catches answers that lead with a
  keyword-similar distractor document.
- `unsupported_answer_rejection_rate`: negative questions receive the standard
  insufficient-information fallback.
- `support_check_pass_rate`: cited answers pass the backend support gate, which
  checks citation integrity (citations belong to retrieved context) **and**
  lexical grounding (the answer shares content tokens, function words excluded,
  with its cited chunk text, so it can reject an answer that cites context it
  did not use) **and** numeric grounding (numbers in the answer must appear in
  the cited chunks or the question). It is computed over answerable questions,
  so a refusal counts as not passing. It is a grounding heuristic, not a
  semantic correctness score. The extractive answerer copies sentences from the
  cited chunks, so offline misses here are refusals, not ungrounded answers.
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

Measured on 2026-10-02 with Python 3.13.14, no API key, hash embeddings and the
deterministic extractive answerer. `make eval` and `uv run python
scripts/run_evaluation.py` produced identical values (rounded here):

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
  "citation_coverage": 0.857,
  "answer_fact_recall": 0.714,
  "first_citation_document_accuracy": 0.714,
  "unsupported_answer_rejection_rate": 0.8,
  "support_check_pass_rate": 0.857,
  "extraction_field_accuracy": 1.0
}
```

Latency is intentionally omitted from the stable snapshot because it varies by
host, container cache and CPU load. The current measured value is shown in the
script output when `make eval` runs.

## Current Limitations

These are failure modes of the offline extractive answerer, reported rather
than tuned away:

- It cannot compare values, so *"Which invoice is above 10,000 EUR?"* is refused
  (lowers `citation_coverage`, `answer_fact_recall` and
  `support_check_pass_rate`).
- It answers with single lines, so a fact on a neighbouring line (the vendor of
  the ergonomic-equipment invoice) is missed (lowers `answer_fact_recall`).
- Lexical retrieval can rank a keyword-similar distractor first (another
  invoice's total for the Globex question), which lowers
  `first_citation_document_accuracy`.
- It has a false-positive mode on keyword-dense but unsupported questions (the
  Acme late-fee percentage), which is why `unsupported_answer_rejection_rate` is
  below 1.0.

The previous snapshot (2026-06-07) reported 1.0 for `citation_coverage` and
`support_check_pass_rate`. The first was a tautology. The second fell once
chunks kept their line breaks and the answerer stopped returning whole chunks.
See `docs/dev_log.md`.
