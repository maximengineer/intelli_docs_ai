from app.rag.citations import FALLBACK_ANSWER, map_citations
from app.rag.schemas import RetrievedChunk


def _chunk(
    *,
    chunk_id: str = "chunk_1",
    text: str = "Total Amount: EUR 12,450.00",
) -> RetrievedChunk:
    return RetrievedChunk(
        document_id="doc_1",
        filename="invoice.txt",
        page_number=1,
        section_title="Invoice",
        chunk_id=chunk_id,
        text=text,
        score=0.9,
    )


def test_maps_placeholder_to_backend_metadata() -> None:
    answer, sources, supported = map_citations('Total is EUR 12,450. <cite index="0">', [_chunk()])

    assert supported is True
    assert answer == "Total is EUR 12,450."
    assert sources[0].document_id == "doc_1"
    assert sources[0].chunk_id == "chunk_1"
    assert sources[0].filename == "invoice.txt"
    assert sources[0].page_number == 1
    assert sources[0].section_title == "Invoice"
    assert sources[0].snippet == "Total Amount: EUR 12,450.00"


def test_maps_tolerant_placeholder_format() -> None:
    answer, sources, supported = map_citations("Total is cited. <cite index = '0'>", [_chunk()])

    assert supported is True
    assert answer == "Total is cited."
    assert sources[0].chunk_id == "chunk_1"


def test_deduplicates_sources_but_removes_all_placeholders() -> None:
    answer, sources, supported = map_citations(
        'First cite. <cite index="0"> Second cite. <cite index="0">',
        [_chunk()],
    )

    assert supported is True
    assert answer == "First cite.  Second cite."
    assert len(sources) == 1


def test_snippet_is_normalized_and_truncated() -> None:
    long_text = "Heading\n" + ("alpha " * 80)
    answer, sources, supported = map_citations(
        'See source. <cite index="0">',
        [_chunk(text=long_text)],
    )

    assert supported is True
    assert answer == "See source."
    assert "\n" not in sources[0].snippet
    assert len(sources[0].snippet) == 240


def test_invalid_placeholder_falls_back_without_sources() -> None:
    answer, sources, supported = map_citations('Bad cite <cite index="3">', [_chunk()])

    assert supported is False
    assert answer == FALLBACK_ANSWER
    assert sources == []


def test_malformed_placeholder_is_unsupported_without_rewriting_answer() -> None:
    answer, sources, supported = map_citations("Bad cite <cite index='abc'>", [_chunk()])

    assert supported is False
    assert answer == "Bad cite <cite index='abc'>"
    assert sources == []


def test_any_out_of_range_placeholder_falls_back_even_with_valid_citation() -> None:
    answer, sources, supported = map_citations(
        'Good <cite index="0"> bad <cite index="7">',
        [_chunk(), _chunk(chunk_id="chunk_2")],
    )

    assert supported is False
    assert answer == FALLBACK_ANSWER
    assert sources == []
