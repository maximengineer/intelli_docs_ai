from dataclasses import dataclass

from app.core.settings import get_settings
from app.documents.service import DocumentService
from app.rag.reranker import LexicalReranker
from app.rag.schemas import QARequest, RetrievedChunk


@dataclass(frozen=True)
class RetrievalResult:
    candidates: list[RetrievedChunk]
    context: list[RetrievedChunk]


class Retriever:
    def __init__(
        self,
        document_service: DocumentService,
        reranker: LexicalReranker | None = None,
    ) -> None:
        self.document_service = document_service
        self.reranker = reranker or LexicalReranker()

    def retrieve(self, request: QARequest) -> RetrievalResult:
        settings = get_settings()
        candidates = self.document_service.search(
            query=request.question,
            top_k=settings.retrieval_candidate_k,
            document_ids=request.document_ids,
        )
        if not settings.reranker_enabled:
            return RetrievalResult(
                candidates=candidates,
                context=candidates[: settings.retrieval_top_k],
            )
        return RetrievalResult(
            candidates=candidates,
            context=self.reranker.rerank(request.question, candidates, settings.retrieval_top_k),
        )
