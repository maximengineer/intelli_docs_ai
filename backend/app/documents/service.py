from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from threading import Lock

from app.core.settings import get_settings
from app.documents.chunker import chunk_document
from app.documents.extractor import extract_fields
from app.documents.parser import parse_document_with_timeout
from app.documents.schemas import DocumentChunk, DocumentResponse
from app.documents.summarizer import summarize_document
from app.llm.client import LLMClient, get_llm_client
from app.rag.schemas import RetrievedChunk
from app.rag.vector_store import InMemoryVectorStore

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(
        self,
        llm_client: LLMClient | None = None,
        vector_store: InMemoryVectorStore | None = None,
    ) -> None:
        self._documents: dict[str, DocumentResponse] = {}
        self._chunks: dict[str, list[DocumentChunk]] = {}
        self._lock = Lock()
        self._llm_client = llm_client if llm_client is not None else get_llm_client()
        self._vector_store = vector_store or InMemoryVectorStore()

    def upload(self, filename: str, content: bytes) -> DocumentResponse:
        safe_name = Path(filename).name
        suffix = Path(safe_name).suffix.lower()
        settings = get_settings()
        if suffix not in settings.allowed_extensions:
            raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")
        if not content:
            raise ValueError("Uploaded file is empty.")

        document_id = "doc_" + hashlib.sha256(content).hexdigest()[:16]

        # Content-hash deduplication: identical bytes are processed once.
        existing = self._documents.get(document_id)
        if existing is not None and existing.status == "completed":
            logger.info("document_upload_deduplicated document_id=%s", document_id)
            return existing

        logger.info("document_upload_started document_id=%s filename=%s", document_id, safe_name)
        try:
            parsed = parse_document_with_timeout(
                document_id=document_id,
                filename=safe_name,
                content=content,
                timeout_seconds=settings.parser_timeout_seconds,
            )
            fields = extract_fields(parsed.text, self._llm_client)
            chunks = chunk_document(parsed)
            document = DocumentResponse(
                document_id=document_id,
                filename=safe_name,
                status="completed",
                summary=summarize_document(parsed.text, self._llm_client),
                document_type=fields.document_type,
                extracted_fields=fields,
                chunk_count=len(chunks),
            )
        except Exception as exc:
            logger.exception("document_upload_failed document_id=%s", document_id)
            document = DocumentResponse(
                document_id=document_id,
                filename=safe_name,
                status="failed",
                summary="",
                document_type="unknown",
                extracted_fields=extract_fields(""),
                chunk_count=0,
                error=str(exc),
            )
            with self._lock:
                self._documents[document_id] = document
                self._chunks[document_id] = []
            self._vector_store.remove(document_id)
            raise ValueError(str(exc)) from exc

        self._vector_store.remove(document_id)
        self._vector_store.index(chunks)
        with self._lock:
            self._documents[document_id] = document
            self._chunks[document_id] = chunks
        logger.info("document_upload_completed document_id=%s chunks=%s", document_id, len(chunks))
        return document

    def get(self, document_id: str) -> DocumentResponse | None:
        with self._lock:
            return self._documents.get(document_id)

    def list_chunks(self, document_ids: list[str] | None = None) -> list[DocumentChunk]:
        with self._lock:
            if document_ids:
                return [chunk for doc_id in document_ids for chunk in self._chunks.get(doc_id, [])]
            return [chunk for chunks in self._chunks.values() for chunk in chunks]

    def search(
        self,
        query: str,
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        return self._vector_store.search(query, top_k, document_ids)


_document_service = DocumentService()


def get_document_service() -> DocumentService:
    return _document_service
