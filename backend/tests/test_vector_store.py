from app.documents.schemas import DocumentChunk
from app.rag.embeddings import HashEmbeddingModel
from app.rag.vector_store import InMemoryVectorStore


class CountingEmbeddingModel:
    """Wraps the hash embedder and counts how often each method is called."""

    name = "counting"

    def __init__(self) -> None:
        self.batch_calls = 0
        self.single_calls = 0
        self._inner = HashEmbeddingModel()

    def embed(self, text: str) -> list[float]:
        self.single_calls += 1
        return self._inner.embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.batch_calls += 1
        return self._inner.embed_batch(texts)


def _chunk(chunk_id: str, document_id: str, text: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        filename=f"{document_id}.txt",
        text=text,
        page_number=1,
        section_title=None,
        chunk_index=0,
    )


def test_search_returns_most_relevant_chunk() -> None:
    store = InMemoryVectorStore(HashEmbeddingModel())
    store.index(
        [
            _chunk("c0", "doc_a", "The invoice total amount is EUR 12,450."),
            _chunk("c1", "doc_b", "The remote work policy allows three days per week."),
        ]
    )

    results = store.search("What is the invoice total amount?", top_k=5)

    assert results
    assert results[0].chunk_id == "c0"


def test_search_can_filter_by_document_id() -> None:
    store = InMemoryVectorStore(HashEmbeddingModel())
    store.index(
        [
            _chunk("c0", "doc_a", "Apples and oranges."),
            _chunk("c1", "doc_b", "Apples and oranges."),
        ]
    )

    results = store.search("apples", top_k=5, document_ids=["doc_b"])

    assert [r.document_id for r in results] == ["doc_b"]


def test_remove_drops_document_vectors() -> None:
    store = InMemoryVectorStore(HashEmbeddingModel())
    store.index([_chunk("c0", "doc_a", "Findable content about invoices.")])

    store.remove("doc_a")

    assert store.search("invoices", top_k=5) == []


def test_embeddings_are_precomputed_once_at_index_time() -> None:
    counter = CountingEmbeddingModel()
    store = InMemoryVectorStore(counter)
    store.index(
        [
            _chunk("c0", "doc_a", "First chunk text."),
            _chunk("c1", "doc_a", "Second chunk text."),
        ]
    )

    assert counter.batch_calls == 1  # chunks embedded once, in a single batch

    store.search("first chunk", top_k=5)
    store.search("second chunk", top_k=5)

    # Only the two queries are embedded; stored chunk vectors are reused.
    assert counter.batch_calls == 1
    assert counter.single_calls == 2
