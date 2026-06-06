from __future__ import annotations

from app.core.text import WORD_RE
from app.rag.schemas import RetrievedChunk


class LexicalReranker:
    """Small deterministic Phase 2 reranker.

    This is intentionally explainable and offline. A cross-encoder reranker can
    replace this class later without changing the retriever interface.
    """

    name = "lexical-overlap-v1"

    def rerank(
        self,
        question: str,
        candidates: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        question_terms = {token.lower() for token in WORD_RE.findall(question) if len(token) > 2}
        if not question_terms:
            return candidates[:top_k]

        reranked = []
        for candidate in candidates:
            chunk_terms = {token.lower() for token in WORD_RE.findall(candidate.text)}
            overlap = len(question_terms & chunk_terms) / len(question_terms)
            combined = (0.75 * candidate.score) + (0.25 * overlap)
            reranked.append(candidate.model_copy(update={"rerank_score": round(combined, 6)}))
        reranked.sort(
            key=lambda chunk: chunk.rerank_score if chunk.rerank_score is not None else chunk.score,
            reverse=True,
        )
        return reranked[:top_k]
