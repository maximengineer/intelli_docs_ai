from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.settings import get_settings
from app.documents.schemas import DocumentResponse
from app.documents.service import get_document_service

router = APIRouter(prefix="/documents", tags=["documents"])

# Content types that carry no useful signal; fall back to the extension check.
_AMBIGUOUS_MIME_TYPES = {"application/octet-stream", ""}


@router.post("/upload", response_model=DocumentResponse)
def upload_document(file: UploadFile = File(...)) -> DocumentResponse:
    settings = get_settings()
    service = get_document_service()

    content_type = file.content_type or ""
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
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_mb} MB upload limit.",
        )

    try:
        return service.upload(filename=file.filename or "document.txt", content=content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str) -> DocumentResponse:
    service = get_document_service()
    document = service.get(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document
