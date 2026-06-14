from app.documents.schemas import ExtractedFields
from app.evaluation.extraction_eval import extraction_field_accuracy
from app.evaluation.service import run_offline_evaluation


def test_offline_evaluation_reports_dataset_coverage() -> None:
    payload = run_offline_evaluation()

    assert payload["status"] == "completed"
    assert payload["documents_loaded"] == 13
    assert payload["questions_evaluated"] == 7
    assert payload["negative_questions_evaluated"] == 5
    assert payload["expected_extractions_evaluated"] == 8
    assert payload["retrieval_questions_scored"] == 7
    assert payload["extraction_rows_scored"] == 8
    assert payload["missing_expected_filenames"] == []


def test_extraction_field_accuracy_is_case_and_numeric_tolerant() -> None:
    actual = ExtractedFields(
        document_type="invoice",
        vendor="Acme Analytics Ltd",
        amount=12450.0,
        currency="eur",
    )
    expected = {
        "document_type": "invoice",
        "vendor": "acme analytics ltd",
        "amount": 12450.0,
        "currency": "EUR",
    }

    assert extraction_field_accuracy(actual, expected) == 1.0


def test_extraction_field_accuracy_returns_zero_for_empty_expected_fields() -> None:
    assert extraction_field_accuracy(ExtractedFields(vendor="Acme"), {}) == 0.0
