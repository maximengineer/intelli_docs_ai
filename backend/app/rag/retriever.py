from app.core.settings import get_settings
from app.documents.service import DocumentService
from app.rag.schemas import QARequest, RetrievedChunk


class Retriever:
    def __init__(self, document_service: DocumentService) -> None:
        self.document_service = document_service

    def retrieve(self, request: QARequest) -> list[RetrievedChunk]:
        settings = get_settings()
        return self.document_service.search(
            query=request.question,
            top_k=settings.retrieval_top_k,
            document_ids=request.document_ids,
        )
