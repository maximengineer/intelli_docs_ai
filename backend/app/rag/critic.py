from __future__ import annotations

from pydantic import BaseModel

from app.core.settings import get_settings
from app.core.text import content_tokens, numeric_values
from app.rag.generator import FALLBACK_ANSWER
from app.rag.schemas import RetrievedChunk, SourceCitation


class SupportCheckResult(BaseModel):
    supported: bool
    reason: str


def check_answer_support(
    answer: str,
    sources: list[SourceCitation],
    context: list[RetrievedChunk],
    question: str = "",
) -> SupportCheckResult:
    """Deterministic, backend-side support gate.

    Three layers, all explainable and free of fake confidence scores:

    1. Citation integrity — cited answers must have mapped sources whose chunk
       IDs belong to the retrieved context, and fallback answers are never
       treated as supported.
    2. Grounding — the answer must share at least ``support_check_min_overlap``
       content tokens (function words such as "the" or "and" excluded) with the
       text of the chunks it cites. This rejects an answer that cites context it
       did not use.
    3. Numeric grounding — every number in the answer must appear in the cited
       chunk text or in the question. Invented amounts, dates and counts are the
       most damaging failure for business documents.

    It is a lexical heuristic, not semantic entailment.
    """

    settings = get_settings()
    if not settings.support_check_enabled:
        return SupportCheckResult(supported=True, reason="support_check_disabled")
    if not answer.strip() or answer == FALLBACK_ANSWER:
        return SupportCheckResult(supported=False, reason="fallback_or_empty_answer")
    if len(sources) < settings.support_check_min_citation_count:
        return SupportCheckResult(supported=False, reason="missing_required_citations")

    context_by_id = {chunk.chunk_id: chunk for chunk in context}
    invalid_sources = [
        source.chunk_id for source in sources if source.chunk_id not in context_by_id
    ]
    if invalid_sources:
        return SupportCheckResult(
            supported=False,
            reason=f"citations_not_in_context:{','.join(invalid_sources)}",
        )

    cited_text = " ".join(context_by_id[source.chunk_id].text for source in sources)
    overlap = len(content_tokens(answer) & content_tokens(cited_text))
    if overlap < settings.support_check_min_overlap:
        return SupportCheckResult(
            supported=False,
            reason=f"answer_not_grounded_in_citations:overlap={overlap}",
        )

    if settings.support_check_numeric_grounding:
        unsupported_numbers = numeric_values(answer) - numeric_values(cited_text + " " + question)
        if unsupported_numbers:
            listed = ",".join(sorted(format(value, "f") for value in unsupported_numbers))
            return SupportCheckResult(
                supported=False,
                reason=f"numbers_not_in_citations:{listed}",
            )
    return SupportCheckResult(supported=True, reason="citations_supported_by_context")
