import time
from threading import Event

from app.documents.schemas import DocumentChunk
from app.documents.service import DocumentService
from app.rag.schemas import RetrievedChunk


class BlockingVectorStore:
    def __init__(self) -> None:
        self.embedding_model = None
        self.started = Event()
        self.release = Event()
        self.index_calls = 0

    def index(self, chunks: list[DocumentChunk]) -> None:
        self.index_calls += 1
        self.started.set()
        assert self.release.wait(timeout=5)

    def remove(self, document_id: str) -> None:
        return None

    def search(
        self,
        query: str,
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        return []


class FailingVectorStore:
    def __init__(self) -> None:
        self.embedding_model = None

    def index(self, chunks: list[DocumentChunk]) -> None:
        raise RuntimeError("vector index failed")

    def remove(self, document_id: str) -> None:
        return None

    def search(
        self,
        query: str,
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        return []


def test_submit_upload_tracks_processing_status() -> None:
    service = DocumentService()

    upload = service.submit_upload(
        filename="invoice.txt",
        content=b"Invoice\nVendor: Phase Two Ltd\nTotal Amount: EUR 2,400.00",
    )

    assert upload.status in {"queued", "completed"}
    _wait_for_status(service, upload.document_id, "completed")
    document = service.get(upload.document_id)

    status = service.get_status(upload.document_id)
    assert status is not None
    assert status.document_id == upload.document_id
    assert {step.name for step in status.steps} >= {"parsing", "embedding", "extracting"}
    assert "classifying" not in {step.name for step in status.steps}
    assert document is not None
    assert document.status == "completed"


def test_duplicate_upload_joins_existing_processing_task() -> None:
    store = BlockingVectorStore()
    service = DocumentService(vector_store=store)
    content = b"Invoice\nVendor: Phase Two Ltd\nTotal Amount: EUR 2,400.00"

    first = service.submit_upload(filename="invoice.txt", content=content)
    assert store.started.wait(timeout=5)
    pending = service.get(first.document_id)
    second = service.submit_upload(filename="invoice.txt", content=content)

    assert pending is not None
    assert pending.status != "completed"
    assert second.document_id == first.document_id
    assert second.task_id == first.task_id
    assert store.index_calls == 1

    store.release.set()
    _wait_for_status(service, first.document_id, "completed")


def test_background_failure_is_visible_on_status_and_task_error() -> None:
    service = DocumentService(vector_store=FailingVectorStore())

    upload = service.submit_upload(
        filename="invoice.txt",
        content=b"Invoice\nVendor: Broken Ltd\nTotal Amount: EUR 10.00",
    )
    status = _wait_for_status(service, upload.document_id, "failed")

    assert status.error is not None
    assert "vector index failed" in status.error
    assert _wait_for_task_error(service, upload.document_id) is not None


def _wait_for_status(
    service: DocumentService,
    document_id: str,
    expected_status: str,
    timeout: float = 5.0,
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = service.get_status(document_id)
        if status is not None and status.status == expected_status:
            return status
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for {document_id} to reach {expected_status}.")


def _wait_for_task_error(
    service: DocumentService,
    document_id: str,
    timeout: float = 5.0,
) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        error = service.get_task_error(document_id)
        if error is not None:
            return error
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for task error for {document_id}.")
