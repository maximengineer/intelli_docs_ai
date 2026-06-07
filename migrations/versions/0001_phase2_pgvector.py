from __future__ import annotations

from alembic import op

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
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS document_chunks (
            chunk_id text primary key,
            document_id text not null,
            filename text not null,
            text text not null,
            page_number integer,
            section_title text,
            chunk_index integer not null,
            embedding vector({EMBEDDING_DIMENSION})
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_document_id ON document_chunks(document_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_table("document_chunks")
