import json
import logging

from app.core.settings import get_settings
from app.documents.service import DocumentService
from app.observability.costs import TokenUsage
from app.rag.retriever import RetrievalResult
from app.rag.schemas import QARequest, RetrievedChunk
from app.rag.service import QAService


class _FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self._chunks = chunks

    def retrieve(self, request: QARequest) -> RetrievalResult:
        return RetrievalResult(candidates=self._chunks, context=self._chunks)


class _FailingRetriever:
    def retrieve(self, request: QARequest) -> RetrievalResult:
        del request
        raise RuntimeError("retrieval unavailable")


class _FakeLLM:
    """Mimics the real client: usage is recorded on complete(), popped after."""

    def __init__(self, draft: str, usage: TokenUsage) -> None:
        self._draft = draft
        self._usage = usage
        self._pending: TokenUsage | None = None

    def complete(self, prompt: str, **_: object) -> str:
        self._pending = self._usage
        return self._draft

    def pop_usage(self) -> TokenUsage | None:
        usage = self._pending
        self._pending = None
        return usage


class _NoUsageLLM:
    def complete(self, prompt: str, **_: object) -> str:
        del prompt
        return 'Total is EUR 12,450. <cite index="0">'

    def pop_usage(self) -> TokenUsage | None:
        return None


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        document_id="doc_1",
        filename="invoice.txt",
        chunk_id="chunk_1",
        text="Total Amount: EUR 12,450.00",
        score=0.9,
    )


def test_qa_metrics_report_real_provider_token_usage() -> None:
    fake_llm = _FakeLLM(
        'Total is EUR 12,450. <cite index="0">',
        TokenUsage(input_tokens=321, output_tokens=42),
    )
    service = QAService(_FakeRetriever([_chunk()]), llm_client=fake_llm)

    response = service.answer(QARequest(question="What is the total amount?"))

    assert response.status == "success"
    assert response.metrics is not None
    # Real provider counts, not the word-count approximation.
    assert response.metrics.input_tokens == 321
    assert response.metrics.output_tokens == 42
    assert response.metrics.token_usage_source == "provider"


def test_qa_metrics_fall_back_to_estimate_without_provider_usage() -> None:
    service = QAService(_FakeRetriever([_chunk()]), llm_client=None)

    response = service.answer(QARequest(question="What is the total amount?"))

    assert response.metrics is not None
    # Word-count approximation is positive; model is flagged as offline.
    assert response.metrics.input_tokens > 0
    assert response.metrics.model_name == "offline-heuristic"
    assert response.metrics.token_usage_source == "estimate"


def test_offline_heuristic_reports_zero_api_cost_when_prices_are_configured(monkeypatch) -> None:
    monkeypatch.setenv("LLM_INPUT_PRICE_PER_1M_TOKENS", "2.0")
    monkeypatch.setenv("LLM_OUTPUT_PRICE_PER_1M_TOKENS", "8.0")
    get_settings.cache_clear()
    service = QAService(_FakeRetriever([_chunk()]), llm_client=None)

    try:
        response = service.answer(QARequest(question="What is the total amount?"))
    finally:
        get_settings.cache_clear()

    assert response.metrics is not None
    assert response.metrics.model_name == "offline-heuristic"
    assert response.metrics.token_usage_source == "estimate"
    assert response.metrics.estimated_cost_usd == 0.0


def test_provider_without_usage_metadata_is_marked_estimated(monkeypatch) -> None:
    monkeypatch.setenv("LLM_INPUT_PRICE_PER_1M_TOKENS", "2.0")
    monkeypatch.setenv("LLM_OUTPUT_PRICE_PER_1M_TOKENS", "8.0")
    get_settings.cache_clear()
    service = QAService(_FakeRetriever([_chunk()]), llm_client=_NoUsageLLM())

    try:
        response = service.answer(QARequest(question="What is the total amount?"))
    finally:
        get_settings.cache_clear()

    assert response.metrics is not None
    assert response.metrics.model_name != "offline-heuristic"
    assert response.metrics.token_usage_source == "estimate"
    assert response.metrics.estimated_cost_usd > 0.0


def test_explicit_none_disables_default_llm_clients(monkeypatch) -> None:
    def fail_if_called() -> None:
        raise AssertionError("provider client should not be initialized")

    monkeypatch.setattr("app.rag.service.get_llm_client", fail_if_called)
    monkeypatch.setattr("app.documents.service.get_llm_client", fail_if_called)

    qa_service = QAService(_FakeRetriever([_chunk()]), llm_client=None)
    document_service = DocumentService(llm_client=None)

    assert qa_service.llm_client is None
    assert document_service._llm_client is None


def test_qa_metrics_label_heuristic_when_provider_is_not_active(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_LLM", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "configured-but-unused")
    get_settings.cache_clear()
    service = QAService(_FakeRetriever([_chunk()]), llm_client=_FakeLLM("", TokenUsage()))
    service.llm_client = None

    try:
        response = service.answer(QARequest(question="What is the total amount?"))
    finally:
        get_settings.cache_clear()

    assert response.metrics is not None
    assert response.metrics.model_name == "offline-heuristic"


def test_qa_metrics_log_structured_status(caplog) -> None:
    caplog.set_level(logging.INFO, logger="intellidocs.run")
    service = QAService(_FakeRetriever([_chunk()]), llm_client=None)

    response = service.answer(QARequest(question="What is the total amount?"))

    assert response.status == "success"
    run_logs = [record for record in caplog.records if record.name == "intellidocs.run"]
    payload = json.loads(run_logs[-1].message)
    assert payload["event"] == "qa_metrics"
    assert payload["run_id"] == response.run_id
    assert payload["status"] == "success"
    assert payload["citation_count"] == 1
    assert payload["token_usage_source"] == "estimate"


def test_qa_failure_logs_structured_error(caplog) -> None:
    caplog.set_level(logging.INFO, logger="intellidocs.run")
    service = QAService(_FailingRetriever(), llm_client=None)

    response = service.answer(QARequest(question="What is the total amount?"))

    assert response.status == "failed"
    run_logs = [record for record in caplog.records if record.name == "intellidocs.run"]
    payload = json.loads(run_logs[-1].message)
    assert payload == {
        "error": "retrieval unavailable",
        "event": "qa_failed",
        "run_id": response.run_id,
        "status": "failed",
    }
