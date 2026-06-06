# Privacy

Phase 2 adds purpose-scoped text handling without overclaiming compliance.

## Text Variants

- `raw_text`: parsed source text used for local parsing only.
- `ai_text`: high-risk identifiers redacted before AI and embedding use.
- `display_text`: redacted text suitable for source snippets.

The current policy version is `phase2-basic-v1`.

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
