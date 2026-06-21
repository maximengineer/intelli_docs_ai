from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from app.core.settings import get_settings
from app.documents.schemas import DocumentResponse, DocumentStatusResponse, DocumentUploadResponse
from app.documents.service import (
    DocumentProcessingActiveError,
    DocumentSubmissionError,
    get_document_service,
)

router = APIRouter(prefix="/documents", tags=["documents"])

# Content types that carry no useful signal; fall back to the extension check.
_AMBIGUOUS_MIME_TYPES = {"application/octet-stream", ""}


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_document(file: UploadFile = File(...)) -> DocumentUploadResponse:
    settings = get_settings()
    service = get_document_service()

    content_type = _base_content_type(file.content_type)
    if (
        content_type not in _AMBIGUOUS_MIME_TYPES
        and content_type not in settings.allowed_mime_types
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported MIME type: {content_type}",
        )

    # Read at most one byte past the limit so an oversized upload is rejected
    # without buffering the whole file into memory.
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_mb} MB upload limit.",
        )

    try:
        return service.submit_upload(filename=file.filename or "document.txt", content=content)
    except DocumentSubmissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "document_id": exc.document_id,
                "filename": exc.filename,
                "status": "failed",
                "error": exc.message,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _base_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str) -> DocumentResponse:
    service = get_document_service()
    document = service.get(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
def get_document_status(document_id: str) -> DocumentStatusResponse:
    service = get_document_service()
    document_status = service.get_status(document_id)
    if document_status is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document_status


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_document(document_id: str) -> Response:
    service = get_document_service()
    try:
        deleted = service.delete(document_id)
    except DocumentProcessingActiveError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
