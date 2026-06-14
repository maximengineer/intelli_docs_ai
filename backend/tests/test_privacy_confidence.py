from app.documents.chunker import chunk_document
from app.documents.confidence import extraction_confidence
from app.documents.privacy import apply_basic_privacy
from app.documents.schemas import ExtractedFields, ParsedDocument, ParsedPage
from app.documents.service import _replace_parsed_text


def test_basic_privacy_redacts_high_risk_identifiers() -> None:
    texts = apply_basic_privacy(
        "Vendor: Example Ltd\nContact: person@example.com\nCard: 4111 1111 1111 1111"
    )

    assert "person@example.com" in texts.raw_text
    assert "[REDACTED_EMAIL]" in texts.ai_text
    assert "[REDACTED_CARD]" in texts.display_text
    assert "Example Ltd" in texts.ai_text


def test_basic_privacy_preserves_business_dates() -> None:
    texts = apply_basic_privacy("Effective Date: 2026-02-01\nPhone: +353 1 555 0199")

    assert "2026-02-01" in texts.ai_text
    assert "[REDACTED_PHONE]" in texts.ai_text


def test_basic_privacy_redacts_account_and_tax_identifiers() -> None:
    texts = apply_basic_privacy(
        "IBAN: IE29 AIBK 9311 5212 3456 78\nAccount No: ACME-12345678\nVAT ID: IE1234567A"
    )

    assert "IE29" not in texts.ai_text
    assert "ACME-12345678" not in texts.ai_text
    assert "IE1234567A" not in texts.ai_text
    assert texts.ai_text.count("[REDACTED_ACCOUNT]") == 2
    assert "[REDACTED_TAX_ID]" in texts.ai_text


def test_basic_privacy_does_not_over_redact_business_prose() -> None:
    texts = apply_basic_privacy(
        "Account manager is Jane Smith.\n"
        "VAT rate is 23 percent.\n"
        "The renewal account review is due on 2026-02-01."
    )

    assert "Account manager is Jane Smith." in texts.ai_text
    assert "VAT rate is 23 percent." in texts.ai_text
    assert "2026-02-01" in texts.ai_text
    assert "[REDACTED_ACCOUNT]" not in texts.ai_text
    assert "[REDACTED_TAX_ID]" not in texts.ai_text


def test_basic_privacy_records_policy_and_keeps_display_variant_redacted() -> None:
    texts = apply_basic_privacy("Contact: person@example.com")

    assert texts.privacy_policy_version == "phase3-purpose-v1"
    assert texts.display_text == texts.ai_text
    assert texts.raw_text == "Contact: person@example.com"


def test_multi_page_privacy_text_is_used_for_chunks() -> None:
    parsed = ParsedDocument(
        document_id="doc_privacy",
        filename="privacy.pdf",
        text="Contact: first@example.com\n\nPhone: +353 1 555 0199",
        pages=[
            ParsedPage(page_number=1, text="Contact: first@example.com"),
            ParsedPage(page_number=2, text="Phone: +353 1 555 0199"),
        ],
    )

    redacted = _replace_parsed_text(parsed, apply_basic_privacy(parsed.text).ai_text)
    chunks = chunk_document(redacted)
    chunk_text = "\n".join(chunk.text for chunk in chunks)

    assert "first@example.com" not in chunk_text
    assert "+353 1 555 0199" not in chunk_text
    assert "[REDACTED_EMAIL]" in chunk_text
    assert "[REDACTED_PHONE]" in chunk_text


def test_extraction_confidence_hard_gate_for_missing_invoice_fields() -> None:
    score, needs_review = extraction_confidence(
        ExtractedFields(document_type="invoice", vendor="Example Ltd")
    )

    assert score < 1.0
    assert needs_review is True


def test_extraction_confidence_hard_gate_for_implausible_values() -> None:
    score, needs_review = extraction_confidence(
        ExtractedFields(
            document_type="invoice",
            vendor="Example Ltd",
            amount=-10.0,
            currency="EURO",
        )
    )

    assert score < 1.0
    assert needs_review is True
