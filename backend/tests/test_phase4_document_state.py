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
