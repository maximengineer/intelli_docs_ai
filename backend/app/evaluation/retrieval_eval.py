import re

from app.rag.schemas import RetrievedChunk, SourceCitation


def document_hit_at_k(
    retrieved: list[RetrievedChunk], expected_document_ids: list[str], k: int
) -> float:
    top_ids = {chunk.document_id for chunk in retrieved[:k]}
    return 1.0 if top_ids & set(expected_document_ids) else 0.0


def citation_coverage(answerable_count: int, cited_answer_count: int) -> float:
    """Share of answerable questions that received a cited ``success`` answer.

    The denominator is every answerable question, not only successful answers:
    ``QAService`` never returns ``success`` without sources, so a ratio over
    successful answers would be 1.0 by construction.
    """
    if answerable_count == 0:
        return 0.0
    return cited_answer_count / answerable_count


def fact_recall(answer: str, expected_facts: list[str]) -> float:
    """Share of expected facts found verbatim (case/whitespace-insensitive) in the answer."""
    if not expected_facts:
        return 0.0
    normalized_answer = _normalize(answer)
    found = sum(1 for fact in expected_facts if _normalize(fact) in normalized_answer)
    return found / len(expected_facts)


def first_citation_hit(sources: list[SourceCitation], expected_document_ids: list[str]) -> float:
    """1.0 when the answer's first citation comes from an expected document."""
    if not sources:
        return 0.0
    return 1.0 if sources[0].document_id in set(expected_document_ids) else 0.0


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()
