from __future__ import annotations

import atexit
import hashlib
import logging
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from app.core.settings import get_settings
from app.documents.chunker import chunk_document
from app.documents.confidence import extraction_confidence
from app.documents.extractor import extract_fields
from app.documents.parser import parse_document_with_timeout
from app.documents.privacy import apply_basic_privacy
from app.documents.processing_backend import resolve_processing_backend
from app.documents.schemas import (
    BranchStatusName,
    DocumentChunk,
    DocumentResponse,
    DocumentStatus,
    DocumentStatusResponse,
    DocumentUploadResponse,
    ExtractedFields,
    ParsedDocument,
    ParsedPage,
    ProcessingStepName,
    ProcessingStepStatus,
)
from app.documents.summarizer import summarize_document
from app.llm.client import LLMClient, get_llm_client
from app.rag.schemas import RetrievedChunk
from app.rag.vector_store import InMemoryVectorStore, PgVectorStore, VectorStore
from app.storage.repositories import DocumentRepository, build_document_repository
from app.storage.upload_store import LocalUploadStore, get_upload_store

logger = logging.getLogger(__name__)
_DEFAULT_LLM_CLIENT = object()


class DocumentSubmissionError(RuntimeError):
    def __init__(self, document_id: str, filename: str, message: str) -> None:
        super().__init__(message)
        self.document_id = document_id
        self.filename = filename
        self.message = message


@dataclass(frozen=True)
class PreparedDocument:
    ai_text: str
    privacy_policy_version: str
    chunks: list[DocumentChunk]


class DocumentService:
    def __init__(
        self,
        llm_client: LLMClient | None | object = _DEFAULT_LLM_CLIENT,
        vector_store: VectorStore | None = None,
        repository: DocumentRepository | None = None,
        upload_store: LocalUploadStore | None = None,
    ) -> None:
        self._tasks: dict[str, str] = {}
        self._task_errors: dict[str, str] = {}
        self._task_futures: dict[str, Future[DocumentResponse]] = {}
        self._lock = Lock()
        self._llm_client = get_llm_client() if llm_client is _DEFAULT_LLM_CLIENT else llm_client
        if get_settings().strict_provider_mode and self._llm_client is None:
            raise RuntimeError("Strict provider mode requires an active LLM client.")
        self._vector_store = vector_store or _build_vector_store()
        self._repository = repository or build_document_repository()
        self._upload_store = upload_store or get_upload_store()
        # Created lazily on first async submit, so the synchronous/eval path
        # never spins up idle worker threads.
        self._executor: ThreadPoolExecutor | None = None

    def _executor_handle(self) -> ThreadPoolExecutor:
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=2, thread_name_prefix="document-worker"
                )
            return self._executor

    def shutdown(self) -> None:
        with self._lock:
            executor = self._executor
            self._executor = None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)

    def upload(self, filename: str, content: bytes) -> DocumentResponse:
        safe_name, document_id, content_hash = self._validate_upload(filename, content)
        existing = self._repository.get_document(document_id)
        if existing is not None and existing.status == "completed":
            logger.info("document_upload_deduplicated document_id=%s", document_id)
            return existing
        stored = self._upload_store.put(filename=safe_name, content=content)
        self._repository.init_document(
            document_id=document_id,
            filename=safe_name,
            content_hash=content_hash,
            status="processing",
            storage_key=stored.storage_key,
            task_id="task_sync",
            processing_backend="thread",
        )
        return self._process_document(document_id, safe_name, content)

    def submit_upload(self, filename: str, content: bytes) -> DocumentUploadResponse:
        safe_name, document_id, content_hash = self._validate_upload(filename, content)
        settings = get_settings()
        processing_backend = resolve_processing_backend(settings)
        with self._lock:
            existing = self._repository.get_document(document_id)
            current_status = self._repository.get_status(document_id)
            existing_task_id = self._tasks.get(document_id)

            if existing is not None and existing.status == "completed":
                logger.info("document_upload_deduplicated document_id=%s", document_id)
                return DocumentUploadResponse(
                    document_id=document_id,
                    task_id=existing_task_id or "task_deduplicated",
                    filename=safe_name,
                    status="completed",
                )

            if current_status is not None and current_status.status not in {"completed", "failed"}:
                logger.info(
                    "document_upload_joined_existing_task document_id=%s task_id=%s",
                    document_id,
                    existing_task_id,
                )
                return DocumentUploadResponse(
                    document_id=document_id,
                    task_id=existing_task_id or "task_existing",
                    filename=safe_name,
                    status=current_status.status,
                )

            # Register the queued status + task inside the same locked section as
            # the check above, so a concurrent duplicate upload joins this task
            # instead of starting a second one (no check-then-act race).
            stored = self._upload_store.put(filename=safe_name, content=content)
            task_id = "task_" + uuid.uuid4().hex[:16]
            self._tasks[document_id] = task_id
            self._task_errors.pop(document_id, None)
            self._repository.init_document(
                document_id=document_id,
                filename=safe_name,
                content_hash=content_hash,
                status="queued",
                storage_key=stored.storage_key,
                task_id=task_id,
                processing_backend=processing_backend,
            )

        if processing_backend == "celery":
            try:
                task_id = self._dispatch_celery(document_id, safe_name, stored.storage_key)
            except Exception as exc:
                with self._lock:
                    self._tasks.pop(document_id, None)
                    self._task_errors[document_id] = str(exc)
                self.mark_document_failed(document_id, str(exc))
                self._cleanup_upload_blob(document_id)
                logger.exception("document_celery_dispatch_failed document_id=%s", document_id)
                raise DocumentSubmissionError(document_id, safe_name, str(exc)) from exc
            with self._lock:
                self._tasks[document_id] = task_id
            self._repository.set_processing_task_id(document_id, task_id)
            return DocumentUploadResponse(
                document_id=document_id,
                task_id=task_id,
                filename=safe_name,
                status="queued",
            )

        future = self._executor_handle().submit(
            self._process_document, document_id, safe_name, content
        )
        with self._lock:
            self._task_futures[document_id] = future
        future.add_done_callback(
            lambda completed: self._record_task_completion(document_id, completed)
        )
        return DocumentUploadResponse(
            document_id=document_id,
            task_id=task_id,
            filename=safe_name,
            status="queued",
        )

    def _validate_upload(self, filename: str, content: bytes) -> tuple[str, str, str]:
        safe_name = Path(filename).name
        suffix = Path(safe_name).suffix.lower()
        settings = get_settings()
        if suffix not in settings.allowed_extensions:
            raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")
        if not content:
            raise ValueError("Uploaded file is empty.")
        content_hash = hashlib.sha256(content).hexdigest()
        document_id = "doc_" + content_hash[:16]
        return safe_name, document_id, content_hash

    def _dispatch_celery(
        self,
        document_id: str,
        safe_name: str,
        storage_key: str,
    ) -> str:
        from worker.tasks import build_document_canvas

        result = build_document_canvas(document_id, safe_name, storage_key).apply_async()
        return str(result.id)

    def _process_document(
        self,
        document_id: str,
        safe_name: str,
        content: bytes,
    ) -> DocumentResponse:
        existing = self._repository.get_document(document_id)
        if existing is not None and existing.status == "completed":
            logger.info("document_upload_deduplicated document_id=%s", document_id)
            self._set_document_status(document_id, "completed")
            return existing

        logger.info("document_upload_started document_id=%s filename=%s", document_id, safe_name)
        try:
            prepared = self._prepare_document_for_branches(document_id, safe_name, content)

            # Fan-out stages are tracked as branches (document status stays
            # "processing"); they run sequentially here but model the points a
            # real Celery group/chord would parallelise.
            self._set_document_status(document_id, "processing")
            self._set_branch(document_id, "extracting", "running")
            fields = extract_fields(prepared.ai_text, self._llm_client)
            confidence, needs_review = extraction_confidence(fields)
            self._set_branch(
                document_id,
                "extracting",
                "completed",
                result={
                    "extracted_fields": fields.model_dump(),
                    "extraction_confidence": confidence,
                    "needs_review": needs_review,
                },
            )

            self._set_branch(document_id, "summarising", "running")
            summary = summarize_document(prepared.ai_text, self._llm_client)
            self._set_branch(document_id, "summarising", "completed", result={"summary": summary})

            self._set_branch(document_id, "embedding", "running")
            self._vector_store.remove(document_id)
            self._vector_store.index(prepared.chunks)
            self._set_branch(
                document_id,
                "embedding",
                "completed",
                result={"chunk_count": len(prepared.chunks)},
            )

            document = DocumentResponse(
                document_id=document_id,
                filename=safe_name,
                status="completed",
                summary=summary,
                document_type=fields.document_type,
                extracted_fields=fields,
                chunk_count=len(prepared.chunks),
                needs_review=needs_review,
                extraction_confidence=confidence,
                privacy_policy_version=prepared.privacy_policy_version,
            )
        except Exception as exc:
            logger.exception("document_upload_failed document_id=%s", document_id)
            document = DocumentResponse(
                document_id=document_id,
                filename=safe_name,
                status="failed",
                summary="",
                document_type="unknown",
                extracted_fields=ExtractedFields(),
                chunk_count=0,
                error=str(exc),
            )
            self._repository.save_document(document)
            self._repository.save_chunks(document_id, [])
            self._remove_vectors_safely(document_id)
            self._fail_running_step(document_id, str(exc))
            self._set_document_status(document_id, "failed", error=str(exc))
            raise ValueError(str(exc)) from exc

        self._repository.save_document(document)
        self._set_document_status(document_id, "completed", needs_review=needs_review)
        self._cleanup_upload_blob(document_id)
        logger.info(
            "document_upload_completed document_id=%s chunks=%s",
            document_id,
            len(prepared.chunks),
        )
        return document

    def seed_document_from_storage(
        self,
        document_id: str,
        safe_name: str,
        storage_key: str,
    ) -> dict[str, str]:
        logger.info("document_seed_started document_id=%s filename=%s", document_id, safe_name)
        try:
            content = self._upload_store.get(storage_key)
            self._prepare_document_for_branches(document_id, safe_name, content)
            self._set_document_status(document_id, "processing")
            return {"document_id": document_id}
        except Exception as exc:
            self.mark_document_failed(document_id, str(exc))
            raise

    def _prepare_document_for_branches(
        self,
        document_id: str,
        safe_name: str,
        content: bytes,
    ) -> PreparedDocument:
        settings = get_settings()
        self._set_step(document_id, "parsing", "running")
        self._set_document_status(document_id, "parsing")
        parsed = parse_document_with_timeout(
            document_id=document_id,
            filename=safe_name,
            content=content,
            timeout_seconds=settings.parser_timeout_seconds,
        )
        self._set_step(document_id, "parsing", "completed")

        self._set_step(document_id, "privacy_processing", "running")
        self._set_document_status(document_id, "privacy_processing")
        privacy_texts = apply_basic_privacy(parsed.text)
        ai_parsed = _replace_parsed_text(parsed, privacy_texts.ai_text)
        self._repository.save_ai_text(
            document_id, privacy_texts.ai_text, privacy_texts.privacy_policy_version
        )
        self._set_step(document_id, "privacy_processing", "completed")

        self._set_step(document_id, "chunking", "running")
        self._set_document_status(document_id, "chunking")
        chunks = chunk_document(ai_parsed)
        self._repository.save_chunks(document_id, chunks)
        self._set_step(document_id, "chunking", "completed")
        return PreparedDocument(
            ai_text=privacy_texts.ai_text,
            privacy_policy_version=privacy_texts.privacy_policy_version,
            chunks=chunks,
        )

    def run_embedding_branch(self, document_id: str) -> dict[str, object]:
        try:
            self._set_branch(document_id, "embedding", "running")
            chunks = self._repository.list_chunks([document_id])
            self._vector_store.remove(document_id)
            self._vector_store.index(chunks)
            result = {"chunk_count": len(chunks)}
            self._set_branch(document_id, "embedding", "completed", result=result)
            return {"document_id": document_id, "branch": "embedding", "status": "completed"}
        except Exception as exc:
            self._set_branch(document_id, "embedding", "failed", error=str(exc))
            self.mark_document_failed(document_id, str(exc))
            raise

    def run_extraction_branch(self, document_id: str) -> dict[str, object]:
        try:
            self._set_branch(document_id, "extracting", "running")
            ai_text = self._require_ai_text(document_id)
            fields = extract_fields(ai_text, self._llm_client)
            confidence, needs_review = extraction_confidence(fields)
            self._set_branch(
                document_id,
                "extracting",
                "completed",
                result={
                    "extracted_fields": fields.model_dump(),
                    "extraction_confidence": confidence,
                    "needs_review": needs_review,
                },
            )
            return {"document_id": document_id, "branch": "extracting", "status": "completed"}
        except Exception as exc:
            self._set_branch(document_id, "extracting", "failed", error=str(exc))
            self.mark_document_failed(document_id, str(exc))
            raise

    def run_summary_branch(self, document_id: str) -> dict[str, object]:
        try:
            self._set_branch(document_id, "summarising", "running")
            summary = summarize_document(self._require_ai_text(document_id), self._llm_client)
            self._set_branch(document_id, "summarising", "completed", result={"summary": summary})
            return {"document_id": document_id, "branch": "summarising", "status": "completed"}
        except Exception as exc:
            self._set_branch(document_id, "summarising", "failed", error=str(exc))
            self.mark_document_failed(document_id, str(exc))
            raise

    def aggregate_document(self, document_id: str) -> dict[str, object]:
        document = self._repository.get_document(document_id)
        if document is None:
            raise ValueError(f"Document not found: {document_id}")
        results = self._repository.get_branch_results(document_id)
        missing = {"embedding", "extracting", "summarising"} - set(results)
        if missing:
            error = f"Missing branch results: {', '.join(sorted(missing))}"
            self.mark_document_failed(document_id, error)
            raise ValueError(error)

        extraction = results["extracting"]
        fields = ExtractedFields.model_validate(extraction.get("extracted_fields") or {})
        summary = str(results["summarising"].get("summary") or "")
        chunk_count = int(results["embedding"].get("chunk_count") or 0)
        needs_review = bool(extraction.get("needs_review"))
        confidence_raw = extraction.get("extraction_confidence")
        confidence = float(confidence_raw) if confidence_raw is not None else None
        completed = DocumentResponse(
            document_id=document.document_id,
            filename=document.filename,
            status="completed",
            summary=summary,
            document_type=fields.document_type,
            extracted_fields=fields,
            chunk_count=chunk_count,
            needs_review=needs_review,
            extraction_confidence=confidence,
            privacy_policy_version=document.privacy_policy_version,
        )
        self._repository.save_document(completed)
        self._set_document_status(document_id, "completed", needs_review=needs_review)
        self._cleanup_upload_blob(document_id)
        logger.info("document_celery_completed document_id=%s chunks=%s", document_id, chunk_count)
        return {"document_id": document_id, "status": "completed"}

    def mark_document_failed(self, document_id: str, error: str) -> None:
        document = self._repository.get_document(document_id)
        if document is not None:
            failed = DocumentResponse(
                document_id=document.document_id,
                filename=document.filename,
                status="failed",
                summary=document.summary,
                document_type=document.document_type,
                extracted_fields=document.extracted_fields,
                chunk_count=document.chunk_count,
                needs_review=document.needs_review,
                extraction_confidence=document.extraction_confidence,
                privacy_policy_version=document.privacy_policy_version,
                error=error,
            )
            self._repository.save_document(failed)
        self._fail_running_step(document_id, error)
        self._set_document_status(document_id, "failed", error=error)

    def _require_ai_text(self, document_id: str) -> str:
        ai_text = self._repository.get_ai_text(document_id)
        if not ai_text:
            raise ValueError(f"Document AI text is not available: {document_id}")
        return ai_text

    def get(self, document_id: str) -> DocumentResponse | None:
        return self._repository.get_document(document_id)

    def delete(self, document_id: str) -> None:
        self._remove_vectors_safely(document_id)
        self._cleanup_upload_blob(document_id)
        self._repository.delete_document(document_id)

    def list_chunks(self, document_ids: list[str] | None = None) -> list[DocumentChunk]:
        return self._repository.list_chunks(document_ids)

    def search(
        self,
        query: str,
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        return self._vector_store.search(query, top_k, document_ids)

    def get_status(self, document_id: str) -> DocumentStatusResponse | None:
        return self._repository.get_status(document_id)

    def get_task_error(self, document_id: str) -> str | None:
        with self._lock:
            return self._task_errors.get(document_id)

    def _set_document_status(
        self,
        document_id: str,
        status: DocumentStatus,
        *,
        needs_review: bool | None = None,
        error: str | None = None,
    ) -> None:
        self._repository.set_document_status(
            document_id, status, needs_review=needs_review, error=error
        )

    def _set_step(
        self,
        document_id: str,
        name: ProcessingStepName,
        status: ProcessingStepStatus,
        error: str | None = None,
    ) -> None:
        self._repository.set_step(document_id, name, status, error)

    def _set_branch(
        self,
        document_id: str,
        name: BranchStatusName,
        status: ProcessingStepStatus,
        error: str | None = None,
        result: dict[str, object] | None = None,
    ) -> None:
        self._repository.set_branch(document_id, name, status, error, result)

    def _fail_running_step(self, document_id: str, error: str) -> None:
        self._repository.fail_running_work(document_id, error)

    def _record_task_completion(
        self,
        document_id: str,
        future: Future[DocumentResponse],
    ) -> None:
        try:
            future.result()
        except Exception as exc:
            with self._lock:
                self._task_errors[document_id] = str(exc)
            logger.exception("document_worker_task_failed document_id=%s", document_id)
        finally:
            with self._lock:
                self._task_futures.pop(document_id, None)

    def _remove_vectors_safely(self, document_id: str) -> None:
        try:
            self._vector_store.remove(document_id)
        except Exception:
            logger.exception("document_vector_cleanup_failed document_id=%s", document_id)

    def _cleanup_upload_blob(self, document_id: str) -> None:
        storage_key = self._repository.get_storage_key(document_id)
        if storage_key is None:
            return
        try:
            self._upload_store.delete(storage_key)
        except Exception:
            logger.exception("document_upload_blob_cleanup_failed document_id=%s", document_id)


def _replace_parsed_text(parsed: ParsedDocument, text: str) -> ParsedDocument:
    # Phase 2 keeps page metadata while using privacy-processed text for AI and embeddings.
    pages = [
        ParsedPage(
            page_number=page.page_number,
            text=apply_basic_privacy(page.text).ai_text,
            section_title=page.section_title,
        )
        for page in parsed.pages
    ]
    return parsed.model_copy(update={"text": text, "pages": pages})


def _pending_document_from_status(status: DocumentStatusResponse) -> DocumentResponse:
    return DocumentResponse(
        document_id=status.document_id,
        filename=status.filename,
        status=status.status,
        summary="",
        document_type="unknown",
        extracted_fields=ExtractedFields(),
        chunk_count=0,
        needs_review=status.needs_review,
        error=status.error,
    )


def _build_vector_store() -> VectorStore:
    settings = get_settings()
    if settings.vector_store_backend == "postgres":
        if not settings.database_url:
            raise ValueError("VECTOR_STORE_BACKEND=postgres requires DATABASE_URL.")
        return PgVectorStore(settings.database_url)
    return InMemoryVectorStore()


_document_service = DocumentService()
atexit.register(_document_service.shutdown)


def get_document_service() -> DocumentService:
    return _document_service
