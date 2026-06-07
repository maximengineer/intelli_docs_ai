# Privacy

Phase 3 keeps privacy purpose-scoped without overclaiming compliance.

## Text Variants

`apply_basic_privacy` produces three variants per document:

- `raw_text`: parsed source text, used for local processing only. The parsed raw
  text is not persisted, logged, or displayed. The original upload blob is stored
  only long enough for async processing/retry and is removed after successful
  processing.
- `ai_text`: high-risk identifiers redacted; used for extraction, summarisation
  and embeddings.
- `display_text`: the redacted text used for citation snippets and UI rendering.

In the current policy (`phase3-purpose-v1`) `ai_text` and `display_text` are
identical (both redacted); they are kept as separate fields so a future policy
can diverge them (e.g. preserve more in `ai_text` than in `display_text`) without
a schema change. The pipeline does not expose a runtime "purpose" switch.

In Postgres mode, `ai_text` is persisted on the document row for Celery branches
and retries. Display-safe chunk text is persisted in `document_chunks.text` for
retrieval and citations. The system does not maintain an enterprise-style
immutable audit trail of every privacy variant.

## Redacted Patterns

The basic policy redacts:

- email addresses
- phone-like numbers
- credit-card-like numbers
- account-like identifiers
- tax ID/VAT/TIN-like identifiers

Organisation, vendor, party, and company names are intentionally preserved by
default so extraction and name-based retrieval still work.

## Limits

This is not a GDPR, SOC2, or enterprise compliance system. There is no
authentication, legal retention workflow, encryption-at-rest implementation, or
data-subject request handling. Those are out of scope for this portfolio phase.
