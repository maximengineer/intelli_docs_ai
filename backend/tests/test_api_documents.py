import pytest
from app.api import routes_documents
from app.documents.service import DocumentProcessingActiveError
from fastapi import HTTPException


class FakeDeleteService:
    def __init__(self, result: bool = True, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.deleted_id: str | None = None

    def delete(self, document_id: str) -> bool:
        self.deleted_id = document_id
        if self.error is not None:
            raise self.error
        return self.result


def test_delete_document_returns_no_content(monkeypatch) -> None:
    service = FakeDeleteService()
    monkeypatch.setattr(routes_documents, "get_document_service", lambda: service)

    response = routes_documents.delete_document("doc_123")

    assert response.status_code == 204
    assert service.deleted_id == "doc_123"


def test_delete_document_returns_not_found(monkeypatch) -> None:
    monkeypatch.setattr(
        routes_documents,
        "get_document_service",
        lambda: FakeDeleteService(result=False),
    )

    with pytest.raises(HTTPException) as exc_info:
        routes_documents.delete_document("doc_missing")

    assert exc_info.value.status_code == 404


def test_delete_document_rejects_active_processing(monkeypatch) -> None:
    error = DocumentProcessingActiveError("Document is still processing.")
    monkeypatch.setattr(
        routes_documents,
        "get_document_service",
        lambda: FakeDeleteService(error=error),
    )

    with pytest.raises(HTTPException) as exc_info:
        routes_documents.delete_document("doc_active")

    assert exc_info.value.status_code == 409
