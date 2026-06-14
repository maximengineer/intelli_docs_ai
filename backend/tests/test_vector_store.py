from contextlib import contextmanager

import pytest
from app.core.settings import get_settings
from app.documents.schemas import DocumentChunk
from app.rag.embeddings import HashEmbeddingModel
from app.rag.vector_store import InMemoryVectorStore, PgVectorStore
from app.storage import database as database_module


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


class WrongDimensionEmbeddingModel:
    name = "wrong-dimension"

    def embed(self, text: str) -> list[float]:
        del text
        return [1.0, 0.0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class FakePgvectorCursor:
    def __init__(self, *, index_type: str, operator_class: str) -> None:
        self._rows = [
            (True, True, True, True, True),
            ("vector(1536)",),
            (index_type, operator_class),
        ]
        self._index = 0

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: object | None = None) -> None:
        del query, params

    def fetchone(self):
        row = self._rows[self._index]
        self._index += 1
        return row


class FakePgvectorConnection:
    def __init__(self, *, index_type: str, operator_class: str) -> None:
        self._index_type = index_type
        self._operator_class = operator_class

    def cursor(self) -> FakePgvectorCursor:
        return FakePgvectorCursor(
            index_type=self._index_type,
            operator_class=self._operator_class,
        )


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


def test_hash_embedding_matches_pgvector_dimension_in_postgres_mode(monkeypatch) -> None:
    monkeypatch.setenv("VECTOR_STORE_BACKEND", "postgres")
    monkeypatch.setenv("POSTGRES_VECTOR_DIMENSION", "1536")
    get_settings.cache_clear()

    try:
        vector = HashEmbeddingModel().embed("invoice total amount")
    finally:
        get_settings.cache_clear()

    assert len(vector) == 1536


def test_pgvector_index_rejects_mismatched_embedding_dimension(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_VECTOR_DIMENSION", "3")
    get_settings.cache_clear()
    store = PgVectorStore(
        "postgresql://example",
        embedding_model=WrongDimensionEmbeddingModel(),
    )
    monkeypatch.setattr(store, "_ensure_schema", lambda: None)

    try:
        with pytest.raises(ValueError) as exc_info:
            store.index([_chunk("c0", "doc_a", "Findable invoice content.")])
    finally:
        get_settings.cache_clear()
    assert "Embedding dimension 2" in str(exc_info.value)
    assert "POSTGRES_VECTOR_DIMENSION=3" in str(exc_info.value)


def test_pgvector_ready_validates_index_method_and_operator_class(monkeypatch) -> None:
    @contextmanager
    def fake_connection(database_url: str, *, connect_timeout: int = 2):
        del database_url, connect_timeout
        yield FakePgvectorConnection(index_type="hnsw", operator_class="vector_cosine_ops")

    monkeypatch.setattr(database_module, "database_connection", fake_connection)

    assert database_module.check_pgvector_ready(
        "postgresql://example",
        expected_dimension=1536,
        expected_operator_class="vector_cosine_ops",
        expected_index_type="hnsw",
    )


def test_pgvector_ready_rejects_stale_index_operator_class(monkeypatch) -> None:
    @contextmanager
    def fake_connection(database_url: str, *, connect_timeout: int = 2):
        del database_url, connect_timeout
        yield FakePgvectorConnection(index_type="hnsw", operator_class="vector_l2_ops")

    monkeypatch.setattr(database_module, "database_connection", fake_connection)

    assert not database_module.check_pgvector_ready(
        "postgresql://example",
        expected_dimension=1536,
        expected_operator_class="vector_cosine_ops",
        expected_index_type="hnsw",
    )


def test_pgvector_search_rejects_mismatched_embedding_dimension(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_VECTOR_DIMENSION", "3")
    get_settings.cache_clear()
    store = PgVectorStore(
        "postgresql://example",
        embedding_model=WrongDimensionEmbeddingModel(),
    )
    monkeypatch.setattr(store, "_ensure_schema", lambda: None)

    try:
        with pytest.raises(ValueError) as exc_info:
            store.search("invoice content", top_k=5)
    finally:
        get_settings.cache_clear()
    assert "Embedding dimension 2" in str(exc_info.value)
    assert "POSTGRES_VECTOR_DIMENSION=3" in str(exc_info.value)
