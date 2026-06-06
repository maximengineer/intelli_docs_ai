from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.storage.pgvector import Vector


class Base(DeclarativeBase):
    pass


class ChunkRecord(Base):
    """The only durable Phase 2 table: chunks + embeddings for retrieval.

    Document-level metadata (summary, extracted fields, status, processing
    steps) is intentionally NOT persisted in Phase 2 — it lives in the
    in-memory DocumentService. Durable document state is a Phase 3 concern.
    """

    __tablename__ = "document_chunks"

    chunk_id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(String, index=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(String)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector())
