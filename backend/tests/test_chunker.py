from app.core.settings import get_settings
from app.documents.chunker import chunk_document
from app.documents.schemas import ParsedDocument, ParsedPage


def test_chunker_preserves_document_metadata() -> None:
    parsed = ParsedDocument(
        document_id="doc_test",
        filename="sample.txt",
        text="Invoice\nVendor: Acme Analytics Ltd",
        pages=[ParsedPage(page_number=1, text="Invoice\nVendor: Acme Analytics Ltd")],
    )

    chunks = chunk_document(parsed)

    assert len(chunks) == 1
    assert chunks[0].document_id == "doc_test"
    assert chunks[0].filename == "sample.txt"
    assert chunks[0].page_number == 1
    assert chunks[0].chunk_id.startswith("doc_test_chunk_")


def test_chunker_uses_configured_size_and_overlap(monkeypatch) -> None:
    monkeypatch.setenv("CHUNK_SIZE_TOKENS", "4")
    monkeypatch.setenv("CHUNK_OVERLAP_TOKENS", "2")
    get_settings.cache_clear()
    try:
        parsed = ParsedDocument(
            document_id="doc_overlap",
            filename="overlap.txt",
            text="one two three four five six seven",
            pages=[
                ParsedPage(
                    page_number=1,
                    text="one two three four five six seven",
                )
            ],
        )

        chunks = chunk_document(parsed)
    finally:
        get_settings.cache_clear()

    assert [chunk.text for chunk in chunks] == [
        "one two three four",
        "three four five six",
        "five six seven",
    ]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]


def test_chunker_preserves_heading_as_section_title() -> None:
    parsed = ParsedDocument(
        document_id="doc_sections",
        filename="sections.txt",
        text="SUMMARY:\nAlpha text\nDETAILS:\nBeta text",
        pages=[
            ParsedPage(
                page_number=3,
                text="SUMMARY:\nAlpha text\nDETAILS:\nBeta text",
            )
        ],
    )

    chunks = chunk_document(parsed)

    assert [chunk.section_title for chunk in chunks] == ["SUMMARY", "DETAILS"]
    assert [chunk.page_number for chunk in chunks] == [3, 3]


def test_chunker_keeps_line_breaks_inside_chunks() -> None:
    text = "INVOICE\nVendor: Acme\nTotal amount: EUR 1,000.00\nDue date: 2026-01-01"
    parsed = ParsedDocument(
        document_id="doc_lines",
        filename="lines.txt",
        text=text,
        pages=[ParsedPage(page_number=1, text=text)],
    )

    chunks = chunk_document(parsed)

    assert [chunk.text for chunk in chunks] == [text]


def test_settings_reject_overlap_not_smaller_than_chunk_size() -> None:
    import pytest
    from app.core.settings import Settings
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="CHUNK_OVERLAP_TOKENS"):
        Settings(chunk_size_tokens=100, chunk_overlap_tokens=100)
