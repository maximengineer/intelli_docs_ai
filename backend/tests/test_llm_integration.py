"""Tests for the LLM-backed paths using a fake client (no real network calls)."""

from app.documents.extractor import extract_fields
from app.documents.summarizer import summarize_document
from app.llm.client import get_llm_client
from app.rag.citations import FALLBACK_ANSWER, map_citations
from app.rag.generator import generate_answer_with_placeholders
from app.rag.schemas import RetrievedChunk


class FakeLLMClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict] = []

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        self.calls.append({"prompt": prompt, "system": system, "json_mode": json_mode})
        return self.response


def _chunk(index: int, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        document_id=f"doc_{index}",
        filename=f"file_{index}.txt",
        page_number=1,
        section_title=None,
        chunk_id=f"chunk_{index}",
        text=text,
        score=0.9,
    )


def test_llm_generator_citations_map_to_backend_metadata() -> None:
    context = [_chunk(0, "Acme Analytics Ltd issued the invoice."), _chunk(1, "Unrelated text.")]
    fake = FakeLLMClient('The vendor is Acme Analytics Ltd. <cite index="0">')

    draft = generate_answer_with_placeholders("Who is the vendor?", context, fake)
    answer, sources, supported = map_citations(draft, context)

    assert supported is True
    assert answer == "The vendor is Acme Analytics Ltd."
    assert len(sources) == 1
    assert sources[0].chunk_id == "chunk_0"
    assert fake.calls, "the LLM client should have been invoked"


def test_llm_generator_invalid_citation_index_falls_back() -> None:
    # The model can now genuinely emit a wrong index; the backend must catch it.
    context = [_chunk(0, "Only one passage exists.")]
    fake = FakeLLMClient('Made up answer. <cite index="7">')

    draft = generate_answer_with_placeholders("Anything?", context, fake)
    answer, sources, supported = map_citations(draft, context)

    assert supported is False
    assert answer == FALLBACK_ANSWER
    assert sources == []


def test_llm_extractor_returns_validated_fields() -> None:
    fake = FakeLLMClient(
        '{"document_type": "invoice", "vendor": "Globex Industrial Systems", '
        '"amount": 22000.0, "currency": "USD", "risk_level": "unknown"}'
    )

    fields = extract_fields("Invoice from Globex", fake)

    assert fields.document_type == "invoice"
    assert fields.vendor == "Globex Industrial Systems"
    assert fields.amount == 22000.0
    assert fields.currency == "USD"
    assert fake.calls[0]["json_mode"] is True


def test_llm_extractor_invalid_json_falls_back_to_heuristic() -> None:
    fake = FakeLLMClient("sorry, I cannot produce JSON")
    text = "Invoice\nVendor: Acme Analytics Ltd\nTotal Amount: EUR 12,450.00"

    fields = extract_fields(text, fake)

    assert fields.vendor == "Acme Analytics Ltd"
    assert fields.amount == 12450.0
    assert fields.currency == "EUR"


def test_llm_summarizer_uses_client_output() -> None:
    fake = FakeLLMClient("- What this document is: a test summary")

    summary = summarize_document("Some document body text.", fake)

    assert summary == "- What this document is: a test summary"


def test_get_llm_client_is_none_when_disabled() -> None:
    # No key / ENABLE_LLM unset in the test environment -> offline heuristics.
    assert get_llm_client() is None
