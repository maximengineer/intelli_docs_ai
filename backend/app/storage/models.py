from __future__ import annotations

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.storage.pgvector import Vector


class Base(DeclarativeBase):
    pass


class DocumentRecord(Base):
    """Durable document metadata and processing state for Phase 4."""

    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    document_type: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    extracted_fields: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extraction_confidence: Mapped[float | None] = mapped_column(Float)
    privacy_policy_version: Mapped[str | None] = mapped_column(String)
    processing_error: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(String)
    processing_task_id: Mapped[str | None] = mapped_column(String)
    processing_backend: Mapped[str | None] = mapped_column(String)
    ai_text: Mapped[str | None] = mapped_column(Text)


class ChunkRecord(Base):
    """Durable chunks + embeddings used for retrieval."""

    __tablename__ = "document_chunks"

    chunk_id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("documents.document_id", ondelete="CASCADE"),
        index=True,
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(String)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector())


class ProcessingStepRecord(Base):
    __tablename__ = "processing_steps"

    document_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("documents.document_id", ondelete="CASCADE"),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class DocumentBranchRecord(Base):
    __tablename__ = "document_branches"

    document_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("documents.document_id", ondelete="CASCADE"),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EvaluationRunRecord(Base):
    __tablename__ = "evaluation_runs"

    evaluation_id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    started_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    result_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
