from __future__ import annotations

import atexit
import hashlib
import logging
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from app.core.settings import get_settings
from app.documents.chunker import chunk_document
from app.documents.confidence import extraction_confidence
from app.documents.extractor import extract_fields
from app.documents.parser import parse_document_with_timeout
from app.documents.privacy import apply_basic_privacy
from app.documents.schemas import (
    BranchStatus,
    BranchStatusName,
    DocumentChunk,
    DocumentResponse,
    DocumentStatus,
    DocumentStatusResponse,
    DocumentUploadResponse,
    ExtractedFields,
    ParsedDocument,
    ParsedPage,
    ProcessingStep,
    ProcessingStepName,
    ProcessingStepStatus,
)
from app.documents.summarizer import summarize_document
from app.llm.client import LLMClient, get_llm_client
from app.rag.schemas import RetrievedChunk
from app.rag.vector_store import InMemoryVectorStore, PgVectorStore, VectorStore

logger = logging.getLogger(__name__)

STEP_NAMES: tuple[ProcessingStepName, ...] = (
    "parsing",
    "privacy_processing",
    "chunking",
)
BRANCH_NAMES: tuple[BranchStatusName, ...] = ("embedding", "extracting", "summarising")


class DocumentService:
    def __init__(
        self,
        llm_client: LLMClient | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self._documents: dict[str, DocumentResponse] = {}
        self._chunks: dict[str, list[DocumentChunk]] = {}
        self._statuses: dict[str, DocumentStatusResponse] = {}
        self._tasks: dict[str, str] = {}
        self._task_errors: dict[str, str] = {}
        self._task_futures: dict[str, Future[DocumentResponse]] = {}
        self._lock = Lock()
        self._llm_client = llm_client if llm_client is not None else get_llm_client()
        self._vector_store = vector_store or _build_vector_store()
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
        safe_name, document_id = self._validate_upload(filename, content)
        self._init_status(document_id, safe_name, "processing")
        return self._process_document(document_id, safe_name, content)

    def submit_upload(self, filename: str, content: bytes) -> DocumentUploadResponse:
        safe_name, document_id = self._validate_upload(filename, content)
        with self._lock:
            existing = self._documents.get(document_id)
            current_status = self._statuses.get(document_id)
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
            task_id = "task_" + uuid.uuid4().hex[:16]
            self._tasks[document_id] = task_id
            self._task_errors.pop(document_id, None)
            self._statuses[document_id] = DocumentStatusResponse(
                document_id=document_id,
                filename=safe_name,
                status="queued",
                steps=[ProcessingStep(name=name) for name in STEP_NAMES],
                branches=[BranchStatus(name=name) for name in BRANCH_NAMES],
            )

        future = self._executor_handle().submit(
            self._process_document, document_id, safe_name, content
        )
        future.add_done_callback(
            lambda completed: self._record_task_completion(document_id, completed)
        )
        with self._lock:
            self._task_futures[document_id] = future
        return DocumentUploadResponse(
            document_id=document_id,
            task_id=task_id,
            filename=safe_name,
            status="queued",
        )

    def _validate_upload(self, filename: str, content: bytes) -> tuple[str, str]:
        safe_name = Path(filename).name
        suffix = Path(safe_name).suffix.lower()
        settings = get_settings()
        if suffix not in settings.allowed_extensions:
            raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")
        if not content:
            raise ValueError("Uploaded file is empty.")
        document_id = "doc_" + hashlib.sha256(content).hexdigest()[:16]
        return safe_name, document_id

    def _process_document(
        self,
        document_id: str,
        safe_name: str,
        content: bytes,
    ) -> DocumentResponse:
        settings = get_settings()
        with self._lock:
            existing = self._documents.get(document_id)
        if existing is not None and existing.status == "completed":
            logger.info("document_upload_deduplicated document_id=%s", document_id)
            self._set_document_status(document_id, "completed")
            return existing

        logger.info("document_upload_started document_id=%s filename=%s", document_id, safe_name)
        try:
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
            self._set_step(document_id, "privacy_processing", "completed")

            self._set_step(document_id, "chunking", "running")
            self._set_document_status(document_id, "chunking")
            chunks = chunk_document(ai_parsed)
            self._set_step(document_id, "chunking", "completed")

            # Fan-out stages are tracked as branches (document status stays
            # "processing"); they run sequentially here but model the points a
            # real Celery group/chord would parallelise.
            self._set_document_status(document_id, "processing")
            self._set_branch(document_id, "extracting", "running")
            fields = extract_fields(privacy_texts.ai_text, self._llm_client)
            confidence, needs_review = extraction_confidence(fields)
            self._set_branch(document_id, "extracting", "completed")

            self._set_branch(document_id, "summarising", "running")
            summary = summarize_document(privacy_texts.ai_text, self._llm_client)
            self._set_branch(document_id, "summarising", "completed")

            self._set_branch(document_id, "embedding", "running")
            self._vector_store.remove(document_id)
            self._vector_store.index(chunks)
            self._set_branch(document_id, "embedding", "completed")

            document = DocumentResponse(
                document_id=document_id,
                filename=safe_name,
                status="completed",
                summary=summary,
                document_type=fields.document_type,
                extracted_fields=fields,
                chunk_count=len(chunks),
                needs_review=needs_review,
                extraction_confidence=confidence,
                privacy_policy_version=privacy_texts.privacy_policy_version,
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
            with self._lock:
                self._documents[document_id] = document
                self._chunks[document_id] = []
            self._remove_vectors_safely(document_id)
            self._fail_running_step(document_id, str(exc))
            self._set_document_status(document_id, "failed", error=str(exc))
            raise ValueError(str(exc)) from exc

        with self._lock:
            self._documents[document_id] = document
            self._chunks[document_id] = chunks
        self._set_document_status(document_id, "completed", needs_review=needs_review)
        logger.info("document_upload_completed document_id=%s chunks=%s", document_id, len(chunks))
        return document

    def get(self, document_id: str) -> DocumentResponse | None:
        with self._lock:
            document = self._documents.get(document_id)
            if document is not None:
                return document
            status = self._statuses.get(document_id)
            if status is None:
                return None
            return _pending_document_from_status(status)

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

    def get_status(self, document_id: str) -> DocumentStatusResponse | None:
        with self._lock:
            return self._statuses.get(document_id)

    def get_task_error(self, document_id: str) -> str | None:
        with self._lock:
            return self._task_errors.get(document_id)

    def _init_status(self, document_id: str, filename: str, status: DocumentStatus) -> None:
        with self._lock:
            self._statuses[document_id] = DocumentStatusResponse(
                document_id=document_id,
                filename=filename,
                status=status,
                steps=[ProcessingStep(name=name) for name in STEP_NAMES],
                branches=[BranchStatus(name=name) for name in BRANCH_NAMES],
            )

    def _set_document_status(
        self,
        document_id: str,
        status: DocumentStatus,
        *,
        needs_review: bool | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            current = self._statuses.get(document_id)
            if current is None:
                return
            self._statuses[document_id] = current.model_copy(
                update={
                    "status": status,
                    "needs_review": current.needs_review if needs_review is None else needs_review,
                    "error": error,
                }
            )

    def _set_step(
        self,
        document_id: str,
        name: ProcessingStepName,
        status: ProcessingStepStatus,
        error: str | None = None,
    ) -> None:
        with self._lock:
            current = self._statuses.get(document_id)
            if current is None:
                return
            steps = [
                step.model_copy(update={"status": status, "error": error})
                if step.name == name
                else step
                for step in current.steps
            ]
            self._statuses[document_id] = current.model_copy(update={"steps": steps})

    def _set_branch(
        self,
        document_id: str,
        name: BranchStatusName,
        status: ProcessingStepStatus,
        error: str | None = None,
    ) -> None:
        with self._lock:
            current = self._statuses.get(document_id)
            if current is None:
                return
            branches = [
                branch.model_copy(update={"status": status, "error": error})
                if branch.name == name
                else branch
                for branch in current.branches
            ]
            self._statuses[document_id] = current.model_copy(update={"branches": branches})

    def _fail_running_step(self, document_id: str, error: str) -> None:
        with self._lock:
            current = self._statuses.get(document_id)
            if current is None:
                return
            steps = [
                step.model_copy(update={"status": "failed", "error": error})
                if step.status == "running"
                else step
                for step in current.steps
            ]
            branches = [
                branch.model_copy(update={"status": "failed", "error": error})
                if branch.status == "running"
                else branch
                for branch in current.branches
            ]
            self._statuses[document_id] = current.model_copy(
                update={"steps": steps, "branches": branches}
            )

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
