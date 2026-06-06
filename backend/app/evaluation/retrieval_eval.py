from app.rag.schemas import RetrievedChunk


def document_hit_at_k(
    retrieved: list[RetrievedChunk], expected_document_ids: list[str], k: int
) -> float:
    top_ids = {chunk.document_id for chunk in retrieved[:k]}
    return 1.0 if top_ids & set(expected_document_ids) else 0.0


def citation_coverage(answer_count: int, cited_answer_count: int) -> float:
    if answer_count == 0:
        return 0.0
    return cited_answer_count / answer_count
