from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def check_database_ready(database_url: str | None) -> bool:
    if not database_url:
        return False
    try:
        import psycopg

        with psycopg.connect(database_url, connect_timeout=2) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select 1")
                cursor.fetchone()
        return True
    except Exception:
        logger.warning("database_readiness_check_failed", exc_info=True)
        return False


def check_pgvector_ready(database_url: str | None, expected_dimension: int | None = None) -> bool:
    if not database_url:
        return False
    try:
        import psycopg

        with psycopg.connect(database_url, connect_timeout=2) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                        exists(select 1 from pg_extension where extname = 'vector'),
                        to_regclass('public.document_chunks') is not null,
                        to_regclass('public.ix_document_chunks_embedding') is not null
                    """
                )
                extension_ready, chunks_ready, embedding_index_ready = cursor.fetchone()
                cursor.execute(
                    """
                    select format_type(attribute.atttypid, attribute.atttypmod)
                    from pg_attribute attribute
                    join pg_class class on class.oid = attribute.attrelid
                    join pg_namespace namespace on namespace.oid = class.relnamespace
                    where namespace.nspname = 'public'
                      and class.relname = 'document_chunks'
                      and attribute.attname = 'embedding'
                      and not attribute.attisdropped
                    """
                )
                row = cursor.fetchone()
        column_type = row[0] if row else None
        expected_type = f"vector({expected_dimension})" if expected_dimension else None
        column_ready = column_type == expected_type if expected_type else bool(column_type)
        return bool(extension_ready and chunks_ready and embedding_index_ready and column_ready)
    except Exception:
        logger.warning("pgvector_readiness_check_failed", exc_info=True)
        return False


def ensure_pgvector_schema(
    database_url: str,
    *,
    dimension: int,
    operator_class: str,
    index_type: str,
) -> bool:
    """Create the Phase 2 pgvector retrieval schema if it is missing."""

    if dimension <= 0:
        raise ValueError("POSTGRES_VECTOR_DIMENSION must be positive.")
    _validate_sql_identifier(operator_class, "POSTGRES_VECTOR_OPERATOR_CLASS")
    _validate_sql_identifier(index_type, "POSTGRES_VECTOR_INDEX_TYPE")

    import psycopg

    with psycopg.connect(database_url, connect_timeout=2) as connection:
        with connection.cursor() as cursor:
            cursor.execute("create extension if not exists vector")
            cursor.execute(
                f"""
                create table if not exists document_chunks (
                    chunk_id text primary key,
                    document_id text not null,
                    filename text not null,
                    text text not null,
                    page_number integer,
                    section_title text,
                    chunk_index integer not null,
                    embedding vector({dimension})
                )
                """
            )
            cursor.execute(
                "create index if not exists ix_document_chunks_document_id "
                "on document_chunks(document_id)"
            )
            cursor.execute(
                f"create index if not exists ix_document_chunks_embedding "
                f"on document_chunks using {index_type} (embedding {operator_class})"
            )
        connection.commit()
    return check_pgvector_ready(database_url, expected_dimension=dimension)


def _validate_sql_identifier(value: str, setting_name: str) -> None:
    if not _SQL_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{setting_name} must be a simple SQL identifier.")
