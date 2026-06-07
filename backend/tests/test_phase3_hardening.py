import json
import time

from app.api.routes_evaluation import get_evaluation, run_evaluation
from app.api.routes_qa import stream_question_events
from app.documents.service import DocumentService
from app.evaluation.service import run_offline_evaluation
from app.rag.critic import check_answer_support
from app.rag.schemas import QARequest, RetrievedChunk, SourceCitation

from worker.tasks import document_chord_error, seed_document_from_storage


def test_streaming_qa_emits_status_before_final_answer() -> None:
    service_document = DocumentService()
    service_document.upload(
        filename="invoice.txt",
        content=b"Invoice\nVendor: Stream Ltd\nTotal Amount: EUR 999.00",
    )

    events = [
        json.loads(line) for line in stream_question_events(QARequest(question="No such fact?"))
    ]

    assert [event["event"] for event in events[:2]] == ["status", "status"]
    assert events[-1]["event"] == "final"
    assert events[-1]["response"]["status"] in {
        "success",
        "insufficient_information",
        "failed",
    }


def test_celery_document_tasks_have_time_limits() -> None:
    assert seed_document_from_storage.soft_time_limit == 50
    assert seed_document_from_storage.time_limit == 60


def test_support_check_rejects_citation_outside_context() -> None:
    result = check_answer_support(
        "The answer is cited.",
        [
            SourceCitation(
                document_id="doc_1",
                filename="a.txt",
                chunk_id="missing_chunk",
                snippet="snippet",
            )
        ],
        [
            RetrievedChunk(
                document_id="doc_1",
                filename="a.txt",
                chunk_id="chunk_1",
                text="snippet",
                score=0.9,
            )
        ],
    )

    assert result.supported is False
    assert result.reason.startswith("citations_not_in_context")


def test_support_check_rejects_answer_not_grounded_in_cited_chunk() -> None:
    # The citation is valid (in context), but the answer shares no content with
    # the cited chunk text — the grounding signal must reject it.
    result = check_answer_support(
        "Quarterly revenue increased twelve percent in Singapore.",
        [
            SourceCitation(
                document_id="doc_1",
                filename="invoice.txt",
                chunk_id="chunk_1",
                snippet="Total Amount: EUR 12,450.00",
            )
        ],
        [
            RetrievedChunk(
                document_id="doc_1",
                filename="invoice.txt",
                chunk_id="chunk_1",
                text="Total Amount: EUR 12,450.00",
                score=0.9,
            )
        ],
    )

    assert result.supported is False
    assert result.reason.startswith("answer_not_grounded_in_citations")


def test_document_status_includes_phase3_branch_statuses() -> None:
    service = DocumentService()

    document = service.upload(
        filename="invoice.txt",
        content=b"Invoice\nVendor: Branch Ltd\nTotal Amount: EUR 123.00",
    )
    status = service.get_status(document.document_id)

    assert status is not None
    assert {branch.name for branch in status.branches} == {
        "embedding",
        "extracting",
        "summarising",
    }
    assert {branch.status for branch in status.branches} == {"completed"}


def test_offline_evaluation_returns_richer_phase3_metrics() -> None:
    payload = run_offline_evaluation()

    assert payload["status"] == "completed"
    assert payload["document_hit_at_5"] == 1.0
    assert "support_check_pass_rate" in payload


def test_forced_offline_evaluation_does_not_use_configured_repository(monkeypatch) -> None:
    def fail_if_called():
        raise AssertionError("forced offline evaluation should use an isolated repository")

    monkeypatch.setattr("app.documents.service.build_document_repository", fail_if_called)

    payload = run_offline_evaluation(force_offline=True)

    assert payload["status"] == "completed"
    assert payload["embedding_backend"] == "hash"


def test_evaluation_api_runs_async_and_exposes_result() -> None:
    started = run_evaluation()
    assert started["status"] == "running"
    evaluation_id = started["evaluation_id"]

    deadline = time.monotonic() + 10.0
    payload = get_evaluation(evaluation_id)
    while payload["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.02)
        payload = get_evaluation(evaluation_id)

    assert payload["status"] == "completed"
    assert payload["result"]["document_hit_at_5"] == 1.0


def test_celery_chord_errback_contract(monkeypatch) -> None:
    failures: list[tuple[str, str]] = []

    class FakeDocumentService:
        def mark_document_failed(self, document_id: str, error: str) -> None:
            failures.append((document_id, error))

    monkeypatch.setattr(
        "worker.tasks.get_document_service",
        lambda: FakeDocumentService(),
    )

    payload = document_chord_error("doc_err", "request-id", RuntimeError("boom"), "traceback")

    assert payload["document_id"] == "doc_err"
    assert payload["status"] == "failed"
    assert "boom" in payload["error"]
    assert failures == [("doc_err", "boom")]


def test_celery_chord_errback_finds_document_id_when_celery_reorders_args(
    monkeypatch,
) -> None:
    failures: list[tuple[str, str]] = []

    class FakeDocumentService:
        def mark_document_failed(self, document_id: str, error: str) -> None:
            failures.append((document_id, error))

    monkeypatch.setattr(
        "worker.tasks.get_document_service",
        lambda: FakeDocumentService(),
    )

    payload = document_chord_error("request-id", RuntimeError("boom"), "traceback", "doc_err")

    assert payload["document_id"] == "doc_err"
    assert failures == [("doc_err", "boom")]
