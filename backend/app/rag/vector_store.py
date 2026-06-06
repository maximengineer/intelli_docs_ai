from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from app.core.settings import get_settings
from app.documents.schemas import DocumentChunk
from app.rag.embeddings import EmbeddingModel, cosine_similarity, get_embedding_model
from app.rag.schemas import RetrievedChunk
from app.storage.database import ensure_pgvector_schema

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredVector:
    chunk: DocumentChunk
    vector: list[float]


class VectorStore(Protocol):
    embedding_model: EmbeddingModel

    def index(self, chunks: list[DocumentChunk]) -> None: ...

    def remove(self, document_id: str) -> None: ...

    def search(
        self,
        query: str,
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]: ...


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


class PgVectorStore:
    """PostgreSQL/pgvector store for chunks + embeddings (the durable Phase 2 slice).

    Only chunk/embedding data is persisted here; document-level metadata and
    processing status remain in the in-memory DocumentService (Phase 3 adds
    durable document state). The schema mirrors the Alembic migration, which is
    the source of truth for managed deployments; this self-init exists so a local
    ``docker compose up`` works without a manual migration step. Schema creation
    is lazy (first use), so importing the app never opens a database connection.
    """

    def __init__(self, database_url: str, embedding_model: EmbeddingModel | None = None) -> None:
        self.database_url = database_url
        self.embedding_model = embedding_model or get_embedding_model()
        settings = get_settings()
        self._dimension = settings.postgres_vector_dimension
        self._operator_class = settings.postgres_vector_operator_class
        self._index_type = settings.postgres_vector_index_type
        self._schema_ready = False
        self._schema_lock = Lock()

    def index(self, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            return
        self._ensure_schema()
        vectors = self.embedding_model.embed_batch([chunk.text for chunk in chunks])
        rows = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            if len(vector) != self._dimension:
                raise ValueError(
                    f"Embedding dimension {len(vector)} does not match the configured "
                    f"POSTGRES_VECTOR_DIMENSION={self._dimension}. Set it to match the "
                    f"embedding model ('{self.embedding_model.name}') and re-run the migration."
                )
            rows.append((chunk, _vector_literal(vector)))

        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for chunk, vector in rows:
                    cursor.execute(
                        """
                        insert into document_chunks (
                            chunk_id,
                            document_id,
                            filename,
                            text,
                            page_number,
                            section_title,
                            chunk_index,
                            embedding
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                        on conflict (chunk_id) do update set
                            filename = excluded.filename,
                            text = excluded.text,
                            page_number = excluded.page_number,
                            section_title = excluded.section_title,
                            chunk_index = excluded.chunk_index,
                            embedding = excluded.embedding
                        """,
                        (
                            chunk.chunk_id,
                            chunk.document_id,
                            chunk.filename,
                            chunk.text,
                            chunk.page_number,
                            chunk.section_title,
                            chunk.chunk_index,
                            vector,
                        ),
                    )
            connection.commit()

    def remove(self, document_id: str) -> None:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("delete from document_chunks where document_id = %s", (document_id,))
            connection.commit()

    def search(
        self,
        query: str,
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        self._ensure_schema()
        query_vector = _vector_literal(self.embedding_model.embed(query))
        where = "where embedding is not null"
        params: list[object] = [query_vector]
        if document_ids:
            where += " and document_id = any(%s)"
            params.append(document_ids)
        params.extend([query_vector, top_k])

        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select
                        document_id,
                        filename,
                        page_number,
                        section_title,
                        chunk_id,
                        text,
                        1 - (embedding <=> %s::vector) as score
                    from document_chunks
                    {where}
                    order by embedding <=> %s::vector
                    limit %s
                    """,
                    params,
                )
                rows = cursor.fetchall()

        return [
            RetrievedChunk(
                document_id=row[0],
                filename=row[1],
                page_number=row[2],
                section_title=row[3],
                chunk_id=row[4],
                text=row[5],
                score=float(row[6]),
            )
            for row in rows
            if row[6] is not None and float(row[6]) > 0
        ]

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            schema_ready = ensure_pgvector_schema(
                self.database_url,
                dimension=self._dimension,
                operator_class=self._operator_class,
                index_type=self._index_type,
            )
            if not schema_ready:
                raise ValueError(
                    "pgvector schema is present but does not match "
                    f"POSTGRES_VECTOR_DIMENSION={self._dimension}."
                )
            self._schema_ready = True
            logger.info(
                "pgvector_store_ready backend=postgres model=%s dim=%s",
                self.embedding_model.name,
                self._dimension,
            )


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
