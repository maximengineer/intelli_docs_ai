from app.documents.schemas import DocumentResponse, ExtractedFields
from app.storage.repositories import InMemoryDocumentRepository


def test_in_memory_repository_persists_document_status_and_chunks() -> None:
    repository = InMemoryDocumentRepository()
    repository.init_document(
        document_id="doc_phase4",
        filename="phase4.txt",
        content_hash="phase4",
        status="queued",
        storage_key="phase4.txt",
        task_id="task_phase4",
        processing_backend="thread",
    )
    repository.set_step("doc_phase4", "parsing", "completed")
    repository.set_branch(
        "doc_phase4",
        "extracting",
        "completed",
        result={"extracted_fields": {"document_type": "invoice"}},
    )
    document = DocumentResponse(
        document_id="doc_phase4",
        filename="phase4.txt",
        status="completed",
        summary="A completed document.",
        document_type="invoice",
        extracted_fields=ExtractedFields(document_type="invoice"),
        chunk_count=0,
    )
    repository.save_document(document)

    stored = repository.get_document("doc_phase4")
    status = repository.get_status("doc_phase4")
    results = repository.get_branch_results("doc_phase4")

    assert stored == document
    assert status is not None
    assert status.status == "completed"
    assert status.processing_backend == "thread"
    assert status.task_id == "task_phase4"
    assert {step.name: step.status for step in status.steps}["parsing"] == "completed"
    assert results["extracting"]["extracted_fields"]["document_type"] == "invoice"


def test_repository_clears_branch_results_when_reinitialized() -> None:
    repository = InMemoryDocumentRepository()
    repository.init_document(
        document_id="doc_retry",
        filename="retry.txt",
        content_hash="retry",
        status="queued",
    )
    repository.set_branch("doc_retry", "summarising", "completed", result={"summary": "stale"})
    assert repository.get_branch_results("doc_retry") == {"summarising": {"summary": "stale"}}

    repository.init_document(
        document_id="doc_retry",
        filename="retry.txt",
        content_hash="retry",
        status="queued",
    )

    assert repository.get_branch_results("doc_retry") == {}


def _service_with_repository(tmp_path, repository: InMemoryDocumentRepository):
    from app.documents.service import DocumentService
    from app.rag.embeddings import HashEmbeddingModel
    from app.rag.vector_store import InMemoryVectorStore
    from app.storage.upload_store import LocalUploadStore

    return DocumentService(
        llm_client=None,
        vector_store=InMemoryVectorStore(HashEmbeddingModel()),
        repository=repository,
        upload_store=LocalUploadStore(tmp_path),
    )


def test_startup_recovery_fails_interrupted_thread_documents(tmp_path) -> None:
    from app.documents.service import INTERRUPTED_PROCESSING_ERROR

    repository = InMemoryDocumentRepository()
    for document_id, status, backend in [
        ("doc_thread", "processing", "thread"),
        ("doc_legacy", "parsing", None),
        ("doc_celery", "processing", "celery"),
        ("doc_done", "completed", "thread"),
    ]:
        repository.init_document(
            document_id=document_id,
            filename=f"{document_id}.txt",
            content_hash=document_id,
            status=status,
            processing_backend=backend,
        )
    repository.set_branch("doc_thread", "extracting", "running")
    service = _service_with_repository(tmp_path, repository)

    recovered = service.recover_interrupted_thread_documents()

    assert sorted(recovered) == ["doc_legacy", "doc_thread"]
    thread_status = service.get_status("doc_thread")
    assert thread_status.status == "failed"
    assert thread_status.error == INTERRUPTED_PROCESSING_ERROR
    assert {b.name: b.status for b in thread_status.branches}["extracting"] == "failed"
    # Celery tasks are redelivered by the broker; completed documents are untouched.
    assert service.get_status("doc_celery").status == "processing"
    assert service.get_status("doc_done").status == "completed"
    # The recovered document can now be removed instead of returning 409.
    assert service.delete("doc_thread") is True


def test_recovered_document_is_reprocessed_on_reupload(tmp_path) -> None:
    content = b"Invoice\nVendor: Restart Ltd\nTotal Amount: EUR 100.00"
    repository = InMemoryDocumentRepository()
    service = _service_with_repository(tmp_path, repository)
    document_id = service._validate_upload("restart.txt", content)[1]
    repository.init_document(
        document_id=document_id,
        filename="restart.txt",
        content_hash="restart",
        status="processing",
        processing_backend="thread",
    )
    service.recover_interrupted_thread_documents()

    upload = service.submit_upload("restart.txt", content)
    future = service._task_futures.get(document_id)
    if future is not None:  # already popped if the worker thread finished first
        future.result(timeout=10)
    service.shutdown()

    assert upload.status == "queued"
    assert upload.task_id.startswith("task_")
    assert service.get_status(document_id).status == "completed"


def test_api_starts_when_startup_recovery_cannot_reach_the_database(monkeypatch, caplog) -> None:
    import asyncio

    import app.main as main_module

    class _UnreachableService:
        def recover_interrupted_thread_documents(self) -> list[str]:
            raise ConnectionError("database unavailable")

    monkeypatch.setattr(main_module, "get_document_service", lambda: _UnreachableService())

    async def _start_and_stop() -> bool:
        async with main_module.lifespan(main_module.app):
            return True

    # /ready reports the database outage; startup itself must not crash.
    assert asyncio.run(_start_and_stop()) is True
    assert "interrupted_document_recovery_failed" in caplog.text
