from app.api.routes_health import health
from app.api.routes_qa import ask_question
from app.documents.service import get_document_service
from app.rag.schemas import QARequest


def test_health_endpoint() -> None:
    assert health() == {"status": "alive"}


def test_upload_then_qa_returns_cited_answer() -> None:
    upload = get_document_service().upload(
        filename="invoice.txt",
        content=b"Invoice\nVendor: Acme Analytics Ltd\nTotal Amount: EUR 12,450.00",
    )
    assert upload.status == "completed"

    response = ask_question(QARequest(question="Which invoice has EUR 12,450?"))

    assert response.status == "success"
    assert response.run_id.startswith("run_")
    assert response.sources
    assert response.sources[0].filename == "invoice.txt"


def test_unsupported_question_returns_fallback_without_sources() -> None:
    response = ask_question(QARequest(question="Which document mentions a Singapore office?"))

    assert response.status == "insufficient_information"
    assert response.sources == []
