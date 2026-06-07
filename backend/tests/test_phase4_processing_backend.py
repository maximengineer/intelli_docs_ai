import hashlib

import pytest
from app.core.settings import get_settings
from app.documents.schemas import DocumentChunk
from app.documents.service import DocumentService
from app.rag.schemas import RetrievedChunk
from app.storage.repositories import InMemoryDocumentRepository
from app.storage.upload_store import LocalUploadStore


class NoopVectorStore:
    def __init__(self) -> None:
        self.embedding_model = None
        self.index_calls = 0

    def index(self, chunks: list[DocumentChunk]) -> None:
        self.index_calls += 1

    def remove(self, document_id: str) -> None:
        return None

    def search(
        self,
        query: str,
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        return []


class RecordingRepository(InMemoryDocumentRepository):
    def __init__(self) -> None:
        super().__init__()
        self.init_count = 0
        self.task_ids: list[str] = []

    def init_document(self, **kwargs) -> None:
        self.init_count += 1
        super().init_document(**kwargs)

    def set_processing_task_id(self, document_id: str, task_id: str) -> None:
        del document_id
        self.task_ids.append(task_id)


def test_celery_processing_requires_durable_postgres_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DOCUMENT_PROCESSING_BACKEND", "celery")
    monkeypatch.setenv("VECTOR_STORE_BACKEND", "memory")
    get_settings.cache_clear()
    try:
        service = DocumentService(upload_store=LocalUploadStore(root=tmp_path))

        with pytest.raises(ValueError) as exc:
            service.submit_upload(
                filename="invoice.txt",
                content=b"Invoice\nVendor: Celery Guard Ltd\nTotal Amount: EUR 42.00",
            )
    finally:
        get_settings.cache_clear()

    assert "requires VECTOR_STORE_BACKEND=postgres" in str(exc.value)


def test_celery_submit_records_task_id_without_second_destructive_init(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("DOCUMENT_PROCESSING_BACKEND", "celery")
    monkeypatch.setenv("VECTOR_STORE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    get_settings.cache_clear()
    repository = RecordingRepository()
    service = DocumentService(
        repository=repository,
        upload_store=LocalUploadStore(root=tmp_path),
        vector_store=NoopVectorStore(),
    )

    def fake_dispatch(
        document_id: str,
        safe_name: str,
        storage_key: str,
    ) -> str:
        del safe_name, storage_key
        repository.save_ai_text(document_id, "worker progress", "test-policy")
        return "celery-task-id"

    monkeypatch.setattr(service, "_dispatch_celery", fake_dispatch)
    try:
        upload = service.submit_upload(
            filename="invoice.txt",
            content=b"Invoice\nVendor: Race Ltd\nTotal Amount: EUR 42.00",
        )
    finally:
        get_settings.cache_clear()

    assert upload.task_id == "celery-task-id"
    assert repository.init_count == 1
    assert repository.task_ids == ["celery-task-id"]
    assert repository.get_ai_text(upload.document_id) == "worker progress"


def test_celery_dispatch_failure_marks_document_failed_and_cleans_blob(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("DOCUMENT_PROCESSING_BACKEND", "celery")
    monkeypatch.setenv("VECTOR_STORE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    get_settings.cache_clear()
    repository = RecordingRepository()
    service = DocumentService(
        repository=repository,
        upload_store=LocalUploadStore(root=tmp_path),
        vector_store=NoopVectorStore(),
    )

    def fake_dispatch(document_id: str, safe_name: str, storage_key: str) -> str:
        del document_id, safe_name, storage_key
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(service, "_dispatch_celery", fake_dispatch)
    content = b"Invoice\nVendor: Dispatch Failure Ltd\nTotal Amount: EUR 42.00"
    document_id = "doc_" + hashlib.sha256(content).hexdigest()[:16]
    try:
        with pytest.raises(RuntimeError, match="broker unavailable"):
            service.submit_upload(
                filename="invoice.txt",
                content=content,
            )
    finally:
        get_settings.cache_clear()

    status = repository.get_status(document_id)
    assert status is not None
    assert status.status == "failed"
    assert status.error == "broker unavailable"
    assert list(tmp_path.iterdir()) == []


def test_sync_upload_deduplicates_before_reinitializing(tmp_path) -> None:
    store = NoopVectorStore()
    service = DocumentService(vector_store=store, upload_store=LocalUploadStore(root=tmp_path))
    content = b"Invoice\nVendor: Sync Dedup Ltd\nTotal Amount: EUR 42.00"

    first = service.upload(filename="invoice.txt", content=content)
    second = service.upload(filename="invoice.txt", content=content)

    assert first.document_id == second.document_id
    assert second.status == "completed"
    assert store.index_calls == 1
