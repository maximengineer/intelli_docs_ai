import pytest
from app.core.settings import get_settings
from app.documents.summarizer import summarize_document


class FakeSummaryClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "json_mode": json_mode,
            }
        )
        return self.response


class FailingSummaryClient:
    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        del prompt, system, temperature, max_tokens, json_mode
        raise RuntimeError("provider unavailable")


def test_summarizer_handles_empty_text() -> None:
    assert summarize_document("   ") == "No readable text was extracted from this document."


def test_heuristic_summary_uses_business_bullets() -> None:
    summary = summarize_document(
        "Invoice from Example Ltd. Total amount is EUR 1,200. Payment is due in 30 days."
    )

    assert summary.startswith("- What this document is:")
    assert "\n- Key facts:" in summary
    assert "\n- Risks or actions:" in summary


def test_llm_summary_uses_prompt_and_limits_tokens() -> None:
    client = FakeSummaryClient("- What this document is: an invoice")

    summary = summarize_document("Invoice from Example Ltd.", client)

    assert summary == "- What this document is: an invoice"
    assert client.calls[0]["system"] is not None
    assert client.calls[0]["temperature"] == 0.0
    assert client.calls[0]["max_tokens"] == 400
    assert client.calls[0]["json_mode"] is False


def test_blank_llm_summary_falls_back_to_heuristic() -> None:
    summary = summarize_document("Invoice from Example Ltd.", FakeSummaryClient("  "))

    assert summary.startswith("- What this document is:")
    assert "Invoice from Example Ltd." in summary


def test_provider_failure_falls_back_to_heuristic() -> None:
    summary = summarize_document("Invoice from Example Ltd.", FailingSummaryClient())

    assert summary.startswith("- What this document is:")
    assert "Invoice from Example Ltd." in summary


def test_strict_provider_mode_rejects_provider_failure(monkeypatch) -> None:
    monkeypatch.setenv("STRICT_PROVIDER_MODE", "true")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="provider unavailable"):
            summarize_document("Invoice from Example Ltd.", FailingSummaryClient())
    finally:
        get_settings.cache_clear()


def test_strict_provider_mode_rejects_blank_summary(monkeypatch) -> None:
    monkeypatch.setenv("STRICT_PROVIDER_MODE", "true")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="empty document summary"):
            summarize_document("Invoice from Example Ltd.", FakeSummaryClient("  "))
    finally:
        get_settings.cache_clear()
