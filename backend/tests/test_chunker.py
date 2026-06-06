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
