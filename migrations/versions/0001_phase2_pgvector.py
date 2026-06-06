from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from app.storage.pgvector import Vector

revision = "0001_phase2_pgvector"
down_revision = None
branch_labels = None
depends_on = None

# Canonical (managed-deploy) schema. The runtime PgVectorStore self-creates the
# same single table for a turnkey local demo; this migration is the source of
# truth for managed deployments. Dimension/index match the default OpenRouter
# embedding (1536, cosine); changing the embedding model requires a new
# migration with the matching dimension.
EMBEDDING_DIMENSION = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "document_chunks",
        sa.Column("chunk_id", sa.String(), primary_key=True),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_title", sa.String(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=True),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_table("document_chunks")
