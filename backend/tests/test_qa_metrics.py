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
    assert response.metrics.cost_estimate_available is True


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
    assert response.metrics.cost_estimate_available is True


def test_provider_cost_is_unavailable_without_configured_prices(monkeypatch) -> None:
    monkeypatch.setenv("LLM_INPUT_PRICE_PER_1M_TOKENS", "0")
    monkeypatch.setenv("LLM_OUTPUT_PRICE_PER_1M_TOKENS", "0")
    get_settings.cache_clear()
    service = QAService(
        _FakeRetriever([_chunk()]),
        llm_client=_FakeLLM(
            'Total is EUR 12,450. <cite index="0">',
            TokenUsage(input_tokens=321, output_tokens=42),
        ),
    )

    try:
        response = service.answer(QARequest(question="What is the total amount?"))
    finally:
        get_settings.cache_clear()

    assert response.metrics is not None
    assert response.metrics.token_usage_source == "provider"
    assert response.metrics.estimated_cost_usd is None
    assert response.metrics.cost_estimate_available is False


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


class _FailingLLM:
    def complete(self, prompt: str, **_: object) -> str:
        del prompt
        raise TimeoutError("provider timed out")

    def pop_usage(self) -> TokenUsage | None:
        return None


def test_heuristic_fallback_after_llm_failure_is_not_attributed_to_the_llm(monkeypatch) -> None:
    monkeypatch.setenv("LLM_INPUT_PRICE_PER_1M_TOKENS", "2.0")
    monkeypatch.setenv("LLM_OUTPUT_PRICE_PER_1M_TOKENS", "8.0")
    get_settings.cache_clear()
    service = QAService(_FakeRetriever([_chunk()]), llm_client=_FailingLLM())

    try:
        response = service.answer(QARequest(question="What is the total amount?"))
    finally:
        get_settings.cache_clear()

    assert response.status == "success"  # the offline answerer took over
    assert response.metrics is not None
    assert response.metrics.model_name == "offline-heuristic"
    assert response.metrics.token_usage_source == "estimate"
    assert response.metrics.estimated_cost_usd == 0.0
    assert response.metrics.cost_estimate_available is True


def test_relevance_gate_refusal_names_no_model_and_reports_no_usage(monkeypatch) -> None:
    monkeypatch.setenv("LLM_INPUT_PRICE_PER_1M_TOKENS", "2.0")
    monkeypatch.setenv("LLM_OUTPUT_PRICE_PER_1M_TOKENS", "8.0")
    get_settings.cache_clear()
    weak = _chunk().model_copy(update={"score": 0.01})
    service = QAService(
        _FakeRetriever([weak]),
        llm_client=_FakeLLM("unused", TokenUsage(input_tokens=1, output_tokens=1)),
    )

    try:
        response = service.answer(QARequest(question="What is the total amount?"))
    finally:
        get_settings.cache_clear()

    assert response.status == "insufficient_information"
    assert response.metrics is not None
    # No answerer ran: no model to name and no tokens consumed.
    assert response.metrics.model_name is None
    assert response.metrics.input_tokens == response.metrics.output_tokens == 0
    assert response.metrics.token_usage_source == "none"
    assert response.metrics.estimated_cost_usd == 0.0
    assert response.metrics.cost_estimate_available is True
    assert response.metrics.support_check_reason == "relevance_below_threshold"


def test_local_ollama_answers_report_zero_api_cost(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "phi4-mini")
    monkeypatch.setenv("LLM_INPUT_PRICE_PER_1M_TOKENS", "0")
    monkeypatch.setenv("LLM_OUTPUT_PRICE_PER_1M_TOKENS", "0")
    get_settings.cache_clear()
    service = QAService(
        _FakeRetriever([_chunk()]),
        llm_client=_FakeLLM(
            'Total is EUR 12,450.00. <cite index="0">',
            TokenUsage(input_tokens=321, output_tokens=42),
        ),
    )

    try:
        response = service.answer(QARequest(question="What is the total amount?"))
    finally:
        get_settings.cache_clear()

    assert response.status == "success"
    assert response.metrics is not None
    assert response.metrics.model_name == "phi4-mini"
    assert response.metrics.token_usage_source == "provider"
    assert response.metrics.estimated_cost_usd == 0.0
    assert response.metrics.cost_estimate_available is True


def test_declined_answer_and_broken_citation_contract_are_distinguished(caplog) -> None:
    from app.rag.generator import FALLBACK_ANSWER

    declined = QAService(
        _FakeRetriever([_chunk()]), llm_client=_FakeLLM(FALLBACK_ANSWER, TokenUsage())
    ).answer(QARequest(question="What is the total amount?"))

    caplog.set_level(logging.WARNING, logger="app.rag.service")
    broken = QAService(
        _FakeRetriever([_chunk()]),
        llm_client=_FakeLLM("The total is EUR 12,450.00 [1].", TokenUsage()),
    ).answer(QARequest(question="What is the total amount?"))

    assert declined.status == broken.status == "insufficient_information"
    assert declined.metrics.support_check_reason == "answer_declined"
    assert broken.metrics.support_check_reason == "citation_mapping_failed"
    assert "llm_citation_contract_failed" in caplog.text


def test_cited_refusal_is_returned_as_insufficient_information() -> None:
    from app.rag.generator import FALLBACK_ANSWER

    draft = 'The late fee percentage is not specified. <cite index="0">\n' + FALLBACK_ANSWER
    response = QAService(
        _FakeRetriever([_chunk()]), llm_client=_FakeLLM(draft, TokenUsage())
    ).answer(QARequest(question="What is the late fee percentage?"))

    assert response.status == "insufficient_information"
    assert response.sources == []
    assert response.answer == FALLBACK_ANSWER
    assert response.metrics.support_check_reason == "answer_declined"


def test_metrics_label_the_model_the_client_actually_calls() -> None:
    llm = _FakeLLM('Total is EUR 12,450.00. <cite index="0">', TokenUsage(input_tokens=5))
    llm.model_name = "custom/injected-model"

    response = QAService(_FakeRetriever([_chunk()]), llm_client=llm).answer(
        QARequest(question="What is the total amount?")
    )

    assert response.metrics.model_name == "custom/injected-model"


def test_provider_clients_get_their_model_and_only_openrouter_gets_attribution(
    monkeypatch,
) -> None:
    from app.llm.client import get_llm_client

    monkeypatch.setenv("ENABLE_LLM", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-used")
    clients = {}
    for provider in ("ollama", "openrouter"):
        monkeypatch.setenv("LLM_PROVIDER", provider)
        get_settings.cache_clear()
        get_llm_client.cache_clear()
        clients[provider] = get_llm_client()
    get_settings.cache_clear()
    get_llm_client.cache_clear()

    assert clients["ollama"].model_name == get_settings().ollama_model
    assert clients["ollama"]._extra_headers == {}
    assert clients["openrouter"].model_name == get_settings().llm_model
    assert set(clients["openrouter"]._extra_headers) == {"HTTP-Referer", "X-Title"}
