from __future__ import annotations

from alembic import op

revision = "0002_phase4_document_state"
down_revision = "0001_phase2_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
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
    op.execute("create index if not exists ix_documents_content_hash on documents(content_hash)")
    op.execute("create index if not exists ix_documents_status on documents(status)")

    op.execute(
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
            document_id,
            min(filename),
            document_id,
            'completed',
            '',
            'unknown',
            '{}'::jsonb,
            count(*)
        from document_chunks
        group by document_id
        on conflict (document_id) do nothing
        """
    )

    op.execute(
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

    op.execute(
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
    op.execute(
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
    op.execute(
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
    op.execute("create index if not exists ix_evaluation_runs_status on evaluation_runs(status)")


def downgrade() -> None:
    op.drop_index("ix_evaluation_runs_status", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_table("document_branches")
    op.drop_table("processing_steps")
    op.drop_constraint("fk_document_chunks_document_id", "document_chunks", type_="foreignkey")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_content_hash", table_name="documents")
    op.drop_table("documents")
