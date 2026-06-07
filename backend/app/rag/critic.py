from __future__ import annotations

from pydantic import BaseModel

from app.core.settings import get_settings
from app.core.text import WORD_RE
from app.rag.generator import FALLBACK_ANSWER
from app.rag.schemas import RetrievedChunk, SourceCitation


class SupportCheckResult(BaseModel):
    supported: bool
    reason: str


def check_answer_support(
    answer: str,
    sources: list[SourceCitation],
    context: list[RetrievedChunk],
) -> SupportCheckResult:
    """Deterministic, backend-side support gate for Phase 3.

    Two layers, both explainable and free of fake confidence scores:

    1. Citation integrity — cited answers must have mapped sources whose chunk
       IDs belong to the retrieved context, and fallback answers are never
       treated as supported.
    2. Grounding — the answer must share at least ``support_check_min_overlap``
       content tokens with the text of the chunks it cites. This is what lets the
       gate actually reject an answer that cites context it did not use (e.g. an
       LLM that hallucinates a sentence and attaches an unrelated citation). It is
       a lexical-grounding heuristic, not semantic entailment.
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

    overlap = _grounding_overlap(answer, sources, context_by_id)
    if overlap < settings.support_check_min_overlap:
        return SupportCheckResult(
            supported=False,
            reason=f"answer_not_grounded_in_citations:overlap={overlap}",
        )
    return SupportCheckResult(supported=True, reason="citations_supported_by_context")


def _content_tokens(text: str) -> set[str]:
    return {token.lower() for token in WORD_RE.findall(text) if len(token) > 2}


def _grounding_overlap(
    answer: str,
    sources: list[SourceCitation],
    context_by_id: dict[str, RetrievedChunk],
) -> int:
    cited_text = " ".join(
        context_by_id[source.chunk_id].text
        for source in sources
        if source.chunk_id in context_by_id
    )
    return len(_content_tokens(answer) & _content_tokens(cited_text))
