import time
from concurrent.futures import Future
from threading import Event
from typing import get_args

import pytest
from app.documents.schemas import (
    BranchStatusName,
    DocumentChunk,
    DocumentStatus,
    ProcessingStepName,
)
from app.documents.service import DocumentProcessingActiveError, DocumentService
from app.rag.schemas import RetrievedChunk
from app.storage.repositories import DEFAULT_BRANCHES, DEFAULT_STEPS


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


class ImmediateExecutor:
    def submit(self, fn, *args, **kwargs):
        future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:  # pragma: no cover - defensive helper
            future.set_exception(exc)
        return future


def test_status_model_vocabulary_matches_public_contract() -> None:
    assert set(get_args(DocumentStatus)) == {
        "uploaded",
        "queued",
        "parsing",
        "privacy_processing",
        "chunking",
        "processing",
        "completed",
        "failed",
    }
    assert set(get_args(ProcessingStepName)) == {
        "parsing",
        "privacy_processing",
        "chunking",
    }
    assert set(get_args(BranchStatusName)) == {
        "embedding",
        "extracting",
        "summarising",
    }
    assert "classifying" not in set(get_args(BranchStatusName))
    assert DEFAULT_STEPS == ("parsing", "privacy_processing", "chunking")
    assert DEFAULT_BRANCHES == ("embedding", "extracting", "summarising")


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
    # Sequential lifecycle steps and the fan-out branches are disjoint.
    assert {step.name for step in status.steps} >= {"parsing", "privacy_processing", "chunking"}
    assert {branch.name for branch in status.branches} >= {"embedding", "extracting"}
    step_and_branch_names = {step.name for step in status.steps} | {
        branch.name for branch in status.branches
    }
    assert "classifying" not in step_and_branch_names
    assert document is not None
    assert document.status == "completed"


def test_completed_thread_task_is_removed_from_tracking(monkeypatch) -> None:
    service = DocumentService()
    monkeypatch.setattr(service, "_executor_handle", lambda: ImmediateExecutor())

    upload = service.submit_upload(
        filename="invoice.txt",
        content=b"Invoice\nVendor: Immediate Ltd\nTotal Amount: EUR 2,400.00",
    )

    assert upload.status == "queued"
    status = service.get_status(upload.document_id)
    assert status is not None
    assert status.status == "completed"
    assert upload.document_id not in service._task_futures


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


def test_completed_document_can_be_deleted_from_storage_and_retrieval() -> None:
    service = DocumentService()
    document = service.upload(
        filename="delete-me.txt",
        content=b"Invoice\nVendor: Remove Me Ltd\nTotal Amount: EUR 10.00",
    )

    assert service.search("Remove Me", top_k=5, document_ids=[document.document_id])
    assert service.delete(document.document_id) is True

    assert service.get(document.document_id) is None
    assert service.get_status(document.document_id) is None
    assert service.search("Remove Me", top_k=5, document_ids=[document.document_id]) == []
    assert service.delete(document.document_id) is False


def test_document_cannot_be_deleted_while_processing() -> None:
    store = BlockingVectorStore()
    service = DocumentService(vector_store=store)
    upload = service.submit_upload(
        filename="processing.txt",
        content=b"Invoice\nVendor: Still Processing Ltd\nTotal Amount: EUR 10.00",
    )
    assert store.started.wait(timeout=5)

    try:
        with pytest.raises(DocumentProcessingActiveError):
            service.delete(upload.document_id)
        assert service.get_status(upload.document_id) is not None
    finally:
        store.release.set()
        _wait_for_status(service, upload.document_id, "completed")


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
