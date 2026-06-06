from app.rag.citations import FALLBACK_ANSWER, map_citations
from app.rag.schemas import RetrievedChunk


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        document_id="doc_1",
        filename="invoice.txt",
        page_number=1,
        section_title="Invoice",
        chunk_id="chunk_1",
        text="Total Amount: EUR 12,450.00",
        score=0.9,
    )


def test_maps_placeholder_to_backend_metadata() -> None:
    answer, sources, supported = map_citations('Total is EUR 12,450. <cite index="0">', [_chunk()])

    assert supported is True
    assert answer == "Total is EUR 12,450."
    assert sources[0].document_id == "doc_1"
    assert sources[0].chunk_id == "chunk_1"


def test_invalid_placeholder_falls_back_without_sources() -> None:
    answer, sources, supported = map_citations('Bad cite <cite index="3">', [_chunk()])

    assert supported is False
    assert answer == FALLBACK_ANSWER
    assert sources == []
