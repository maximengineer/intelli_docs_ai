from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from app.documents.schemas import DocumentChunk
from app.rag.embeddings import EmbeddingModel, cosine_similarity, get_embedding_model
from app.rag.schemas import RetrievedChunk


@dataclass(frozen=True)
class StoredVector:
    chunk: DocumentChunk
    vector: list[float]


class InMemoryVectorStore:
    """In-memory vector index.

    Embeddings are computed once when chunks are indexed (at upload time) rather
    than on every query, so a question only embeds the query string itself.
    """

    def __init__(self, embedding_model: EmbeddingModel | None = None) -> None:
        self.embedding_model = embedding_model or get_embedding_model()
        self._vectors: dict[str, list[StoredVector]] = {}
        self._lock = Lock()

    def index(self, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            return
        vectors = self.embedding_model.embed_batch([chunk.text for chunk in chunks])
        stored: dict[str, list[StoredVector]] = {}
        for chunk, vector in zip(chunks, vectors, strict=True):
            stored.setdefault(chunk.document_id, []).append(
                StoredVector(chunk=chunk, vector=vector)
            )
        with self._lock:
            self._vectors.update(stored)

    def remove(self, document_id: str) -> None:
        with self._lock:
            self._vectors.pop(document_id, None)

    def search(
        self,
        query: str,
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        with self._lock:
            if document_ids:
                candidates = [sv for doc_id in document_ids for sv in self._vectors.get(doc_id, [])]
            else:
                candidates = [sv for vectors in self._vectors.values() for sv in vectors]
        if not candidates:
            return []

        query_vector = self.embedding_model.embed(query)
        scored = (
            (cosine_similarity(query_vector, stored.vector), stored.chunk) for stored in candidates
        )
        ranked = sorted(scored, key=lambda item: item[0], reverse=True)
        return [
            RetrievedChunk(
                document_id=chunk.document_id,
                filename=chunk.filename,
                page_number=chunk.page_number,
                section_title=chunk.section_title,
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                score=score,
            )
            for score, chunk in ranked[:top_k]
            if score > 0
        ]
