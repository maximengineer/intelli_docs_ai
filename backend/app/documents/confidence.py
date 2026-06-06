from __future__ import annotations

from app.documents.schemas import ExtractedFields

REQUIRED_FIELDS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "invoice": ("vendor", "amount", "currency"),
    "contract": ("party_name", "effective_date"),
    "policy": ("effective_date",),
    "report": (),
}


def extraction_confidence(fields: ExtractedFields) -> tuple[float, bool]:
    """Derived extraction quality score with simple hard gates.

    This is not an LLM-provided confidence number. It is a deterministic score
    derived from field completeness and basic plausibility.
    """

    required = REQUIRED_FIELDS_BY_TYPE.get(fields.document_type, ())
    completeness = _required_completeness(fields, required)
    plausibility = _plausibility_score(fields)
    optional_quality = _optional_quality(fields)
    score = round(0.55 * completeness + 0.30 * plausibility + 0.15 * optional_quality, 3)
    needs_review = bool(required and completeness < 1.0) or plausibility < 1.0
    return score, needs_review


def _required_completeness(fields: ExtractedFields, required: tuple[str, ...]) -> float:
    if not required:
        return 1.0
    present = sum(1 for name in required if getattr(fields, name) not in (None, "", "unknown"))
    return present / len(required)


def _plausibility_score(fields: ExtractedFields) -> float:
    if fields.amount is not None and fields.amount < 0:
        return 0.0
    if fields.currency is not None and len(fields.currency) != 3:
        return 0.5
    return 1.0


def _optional_quality(fields: ExtractedFields) -> float:
    values = fields.model_dump()
    populated = sum(1 for value in values.values() if value not in (None, "", "unknown"))
    return min(1.0, populated / 4)
