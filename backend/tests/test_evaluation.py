from app.documents.schemas import ExtractedFields
from app.evaluation.extraction_eval import extraction_field_accuracy
from app.evaluation.retrieval_eval import citation_coverage, fact_recall, first_citation_hit
from app.evaluation.service import run_offline_evaluation
from app.rag.schemas import SourceCitation


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
    for metric in ("citation_coverage", "answer_fact_recall", "first_citation_document_accuracy"):
        assert 0.0 <= payload[metric] <= 1.0


def test_citation_coverage_uses_all_answerable_questions() -> None:
    # 6 of 7 answerable questions got a cited answer; refusals count against it.
    assert citation_coverage(answerable_count=7, cited_answer_count=6) == 6 / 7
    assert citation_coverage(answerable_count=0, cited_answer_count=0) == 0.0


def test_fact_recall_is_case_and_whitespace_insensitive() -> None:
    answer = "Total Amount:  eur 12,450.00 for Acme."

    assert fact_recall(answer, ["EUR 12,450.00"]) == 1.0
    assert fact_recall(answer, ["EUR 12,450.00", "Globex"]) == 0.5
    assert fact_recall(answer, []) == 0.0


def test_first_citation_hit_checks_only_the_leading_source() -> None:
    def source(document_id: str) -> SourceCitation:
        return SourceCitation(
            document_id=document_id, filename=f"{document_id}.txt", chunk_id="c", snippet="s"
        )

    assert first_citation_hit([source("doc_a"), source("doc_b")], ["doc_a"]) == 1.0
    assert first_citation_hit([source("doc_b"), source("doc_a")], ["doc_a"]) == 0.0
    assert first_citation_hit([], ["doc_a"]) == 0.0


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
