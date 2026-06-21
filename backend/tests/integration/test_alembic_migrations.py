import os

import psycopg
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_ALEMBIC_INTEGRATION") != "1",
    reason="Run through `make alembic-integration-test` against isolated Postgres.",
)


def test_alembic_upgrade_creates_expected_schema() -> None:
    database_url = os.environ["ALEMBIC_TEST_DATABASE_URL"]

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("select version_num from alembic_version")
        assert cursor.fetchone() == ("0002_phase4_document_state",)

        cursor.execute("select exists(select 1 from pg_extension where extname = 'vector')")
        assert cursor.fetchone() == (True,)

        cursor.execute(
            """
            select table_name
            from information_schema.tables
            where table_schema = 'public'
            """
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert {
            "documents",
            "document_chunks",
            "processing_steps",
            "document_branches",
            "evaluation_runs",
        } <= tables

        cursor.execute(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'public' and table_name = 'documents'
            """
        )
        document_columns = {row[0] for row in cursor.fetchall()}
        assert {
            "document_id",
            "content_hash",
            "status",
            "storage_key",
            "processing_task_id",
            "processing_backend",
            "ai_text",
        } <= document_columns

        cursor.execute(
            """
            select format_type(attribute.atttypid, attribute.atttypmod)
            from pg_attribute attribute
            join pg_class table_info on table_info.oid = attribute.attrelid
            join pg_namespace namespace on namespace.oid = table_info.relnamespace
            where namespace.nspname = 'public'
              and table_info.relname = 'document_chunks'
              and attribute.attname = 'embedding'
              and not attribute.attisdropped
            """
        )
        assert cursor.fetchone() == ("vector(1536)",)

        cursor.execute(
            """
            select access_method.amname, operator_class.opcname
            from pg_index index_info
            join pg_class index_class on index_class.oid = index_info.indexrelid
            join pg_namespace namespace on namespace.oid = index_class.relnamespace
            join pg_am access_method on access_method.oid = index_class.relam
            join pg_opclass operator_class on operator_class.oid = index_info.indclass[0]
            where namespace.nspname = 'public'
              and index_class.relname = 'ix_document_chunks_embedding'
            """
        )
        assert cursor.fetchone() == ("hnsw", "vector_cosine_ops")

        cursor.execute(
            """
            select
                constraint_info.conrelid::regclass::text,
                constraint_info.confrelid::regclass::text,
                constraint_info.confdeltype
            from pg_constraint constraint_info
            where constraint_info.conname = 'fk_document_chunks_document_id'
              and constraint_info.conrelid = 'public.document_chunks'::regclass
            """
        )
        assert cursor.fetchone() == ("document_chunks", "documents", "c")
