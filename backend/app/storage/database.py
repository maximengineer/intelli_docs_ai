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
                        to_regclass('public.documents') is not null,
                        to_regclass('public.document_chunks') is not null,
                        to_regclass('public.ix_document_chunks_embedding') is not null,
                        exists(
                            select 1
                            from pg_constraint
                            where conname = 'fk_document_chunks_document_id'
                        )
                    """
                )
                (
                    extension_ready,
                    documents_ready,
                    chunks_ready,
                    embedding_index_ready,
                    chunk_fk_ready,
                ) = cursor.fetchone()
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
        return bool(
            extension_ready
            and documents_ready
            and chunks_ready
            and embedding_index_ready
            and chunk_fk_ready
            and column_ready
        )
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
    """Create/evolve the durable document + pgvector schema if it is missing."""

    if dimension <= 0:
        raise ValueError("POSTGRES_VECTOR_DIMENSION must be positive.")
    _validate_sql_identifier(operator_class, "POSTGRES_VECTOR_OPERATOR_CLASS")
    _validate_sql_identifier(index_type, "POSTGRES_VECTOR_INDEX_TYPE")

    import psycopg

    with psycopg.connect(database_url, connect_timeout=2) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_lock(hashtext('intellidocs_schema'))")
            try:
                cursor.execute("create extension if not exists vector")
                _ensure_document_state_schema(cursor)
                cursor.execute(
                    f"""
                    create table if not exists document_chunks (
                        chunk_id text primary key,
                        document_id text not null
                            constraint fk_document_chunks_document_id
                            references documents(document_id) on delete cascade,
                        filename text not null,
                        text text not null,
                        page_number integer,
                        section_title text,
                        chunk_index integer not null,
                        embedding vector({dimension})
                    )
                    """
                )
                _ensure_chunk_fk(cursor)
                cursor.execute(
                    "create index if not exists ix_document_chunks_document_id "
                    "on document_chunks(document_id)"
                )
                cursor.execute(
                    f"create index if not exists ix_document_chunks_embedding "
                    f"on document_chunks using {index_type} (embedding {operator_class})"
                )
            finally:
                try:
                    cursor.execute("select pg_advisory_unlock(hashtext('intellidocs_schema'))")
                except Exception:
                    logger.warning("schema_advisory_unlock_failed", exc_info=True)
        connection.commit()
    return check_pgvector_ready(database_url, expected_dimension=dimension)


def _ensure_document_state_schema(cursor: object) -> None:
    cursor.execute(
        """
        create table if not exists documents (
            document_id text primary key,
            filename text not null,
            content_hash text not null unique,
            status text not null,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            summary text not null default '',
            document_type text not null default 'unknown',
            extracted_fields jsonb not null default '{}'::jsonb,
            chunk_count integer not null default 0,
            needs_review boolean not null default false,
            extraction_confidence double precision,
            privacy_policy_version text,
            processing_error text,
            storage_key text,
            processing_task_id text,
            processing_backend text,
            ai_text text
        )
        """
    )
    cursor.execute(
        "create index if not exists ix_documents_content_hash on documents(content_hash)"
    )
    cursor.execute("create index if not exists ix_documents_status on documents(status)")
    _ensure_column(cursor, "documents", "storage_key", "text")
    _ensure_column(cursor, "documents", "processing_task_id", "text")
    _ensure_column(cursor, "documents", "processing_backend", "text")
    _ensure_column(cursor, "documents", "ai_text", "text")
    cursor.execute(
        """
        create table if not exists processing_steps (
            document_id text not null references documents(document_id) on delete cascade,
            name text not null,
            status text not null,
            error text,
            updated_at timestamptz not null default now(),
            primary key (document_id, name)
        )
        """
    )
    cursor.execute(
        """
        create table if not exists document_branches (
            document_id text not null references documents(document_id) on delete cascade,
            name text not null,
            status text not null,
            error text,
            result_json jsonb,
            updated_at timestamptz not null default now(),
            primary key (document_id, name)
        )
        """
    )
    _ensure_column(cursor, "document_branches", "result_json", "jsonb")
    cursor.execute(
        """
        create table if not exists evaluation_runs (
            evaluation_id text primary key,
            status text not null,
            started_at timestamptz not null default now(),
            completed_at timestamptz,
            result_json jsonb,
            error text
        )
        """
    )
    cursor.execute(
        "create index if not exists ix_evaluation_runs_status on evaluation_runs(status)"
    )


def _ensure_chunk_fk(cursor: object) -> None:
    cursor.execute(
        """
        insert into documents (
            document_id,
            filename,
            content_hash,
            status,
            summary,
            document_type,
            extracted_fields,
            chunk_count
        )
        select
            chunks.document_id,
            min(chunks.filename),
            chunks.document_id,
            'completed',
            '',
            'unknown',
            '{}'::jsonb,
            count(*)
        from document_chunks chunks
        left join documents docs on docs.document_id = chunks.document_id
        where docs.document_id is null
        group by chunks.document_id
        on conflict (document_id) do nothing
        """
    )
    cursor.execute(
        """
        do $$
        begin
            if not exists (
                select 1
                from pg_constraint
                where conname = 'fk_document_chunks_document_id'
            ) then
                alter table document_chunks
                add constraint fk_document_chunks_document_id
                foreign key (document_id) references documents(document_id)
                on delete cascade;
            end if;
        end
        $$;
        """
    )


def _ensure_column(cursor: object, table: str, column: str, definition: str) -> None:
    _validate_sql_identifier(table, "table")
    _validate_sql_identifier(column, "column")
    cursor.execute(f"alter table {table} add column if not exists {column} {definition}")


def _validate_sql_identifier(value: str, setting_name: str) -> None:
    if not _SQL_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{setting_name} must be a simple SQL identifier.")
