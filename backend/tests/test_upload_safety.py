import hashlib
from io import BytesIO

import pytest
from app.api import routes_documents
from app.api.routes_documents import upload_document
from app.core.settings import get_settings
from app.documents.service import DocumentService, DocumentSubmissionError, get_document_service
from app.rag.schemas import RetrievedChunk
from app.storage.upload_store import LocalUploadStore
from fastapi import HTTPException, UploadFile, status
from starlette.datastructures import Headers


class NoopVectorStore:
    def __init__(self) -> None:
        self.embedding_model = None

    def index(self, chunks) -> None:
        return None

    def remove(self, document_id: str) -> None:
        return None

    def search(
        self,
        query: str,
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        return []


def test_upload_rejects_unsupported_mime_type() -> None:
    file = UploadFile(
        BytesIO(b"not really an executable"),
        filename="invoice.txt",
        headers=Headers({"content-type": "application/x-msdownload"}),
    )

    with pytest.raises(HTTPException) as exc:
        upload_document(file)

    assert exc.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE


def test_upload_accepts_allowed_mime_type_with_parameters() -> None:
    file = UploadFile(
        BytesIO(b"Invoice\nVendor: Charset Ltd\nTotal Amount: EUR 1,200.00"),
        filename="invoice.txt",
        headers=Headers({"content-type": "text/plain; charset=utf-8"}),
    )

    document = upload_document(file)

    assert document.status in {"queued", "completed"}
    assert document.filename == "invoice.txt"


def test_upload_accepts_allowed_text_mime_type() -> None:
    file = UploadFile(
        BytesIO(b"Invoice\nVendor: Safe Upload Ltd\nTotal Amount: EUR 1,200.00"),
        filename="invoice.txt",
        headers=Headers({"content-type": "text/plain"}),
    )

    document = upload_document(file)

    assert document.status in {"queued", "completed"}
    assert document.filename == "invoice.txt"
    status_response = get_document_service().get_status(document.document_id)
    assert status_response is not None


def test_upload_rejects_file_over_configured_size(monkeypatch) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    file = UploadFile(
        BytesIO(b"x" * (1024 * 1024 + 1)),
        filename="large.txt",
        headers=Headers({"content-type": "text/plain"}),
    )

    try:
        with pytest.raises(HTTPException) as exc:
            upload_document(file)
    finally:
        get_settings.cache_clear()

    assert exc.value.status_code == status.HTTP_413_CONTENT_TOO_LARGE


def test_upload_rejects_unsupported_extension() -> None:
    file = UploadFile(
        BytesIO(b"Invoice"),
        filename="invoice.exe",
        headers=Headers({"content-type": "application/octet-stream"}),
    )

    with pytest.raises(HTTPException) as exc:
        upload_document(file)

    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Unsupported file type" in str(exc.value.detail)


def test_upload_rejects_empty_file() -> None:
    file = UploadFile(
        BytesIO(b""),
        filename="empty.txt",
        headers=Headers({"content-type": "text/plain"}),
    )

    with pytest.raises(HTTPException) as exc:
        upload_document(file)

    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "empty" in str(exc.value.detail)


def test_upload_sanitizes_path_traversal_filename(tmp_path) -> None:
    service = DocumentService(
        vector_store=NoopVectorStore(),
        upload_store=LocalUploadStore(root=tmp_path),
    )

    document = service.upload(
        filename="../../invoice.txt",
        content=b"Invoice\nVendor: Safe Name Ltd\nTotal Amount: EUR 99.00",
    )

    assert document.filename == "invoice.txt"
    assert ".." not in document.filename


def test_corrupt_supported_file_marks_document_failed(tmp_path) -> None:
    service = DocumentService(
        vector_store=NoopVectorStore(),
        upload_store=LocalUploadStore(root=tmp_path),
    )

    with pytest.raises(ValueError):
        service.upload(filename="corrupt.pdf", content=b"not a pdf")

    document_id = "doc_" + hashlib.sha256(b"not a pdf").hexdigest()[:16]
    status_response = service.get_status(document_id)
    assert status_response is not None
    assert status_response.status == "failed"
    assert status_response.error


def test_upload_returns_structured_service_unavailable_on_submission_failure(
    monkeypatch,
) -> None:
    class FailingService:
        def submit_upload(self, filename: str, content: bytes):
            del content
            raise DocumentSubmissionError("doc_failed", filename, "broker unavailable")

    monkeypatch.setattr(routes_documents, "get_document_service", lambda: FailingService())
    file = UploadFile(
        BytesIO(b"Invoice\nVendor: Failure Ltd"),
        filename="invoice.txt",
        headers=Headers({"content-type": "text/plain"}),
    )

    with pytest.raises(HTTPException) as exc:
        upload_document(file)

    assert exc.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert exc.value.detail == {
        "document_id": "doc_failed",
        "filename": "invoice.txt",
        "status": "failed",
        "error": "broker unavailable",
    }
