from __future__ import annotations

import logging
from threading import Lock
from typing import Any, Protocol

from app.core.settings import get_settings
from app.documents.schemas import (
    BranchStatus,
    BranchStatusName,
    DocumentChunk,
    DocumentResponse,
    DocumentStatus,
    DocumentStatusResponse,
    ExtractedFields,
    ProcessingStep,
    ProcessingStepName,
    ProcessingStepStatus,
)
from app.storage.database import ensure_pgvector_schema

logger = logging.getLogger(__name__)

DEFAULT_STEPS: tuple[ProcessingStepName, ...] = (
    "parsing",
    "privacy_processing",
    "chunking",
)
DEFAULT_BRANCHES: tuple[BranchStatusName, ...] = ("embedding", "extracting", "summarising")


class DocumentRepository(Protocol):
    def get_document(self, document_id: str) -> DocumentResponse | None: ...

    def get_status(self, document_id: str) -> DocumentStatusResponse | None: ...

    def list_chunks(self, document_ids: list[str] | None = None) -> list[DocumentChunk]: ...

    def get_ai_text(self, document_id: str) -> str | None: ...

    def get_branch_results(self, document_id: str) -> dict[str, dict[str, Any]]: ...

    def init_document(
        self,
        *,
        document_id: str,
        filename: str,
        content_hash: str,
        status: DocumentStatus,
        storage_key: str | None = None,
        task_id: str | None = None,
        processing_backend: str | None = None,
    ) -> None: ...

    def set_processing_task_id(self, document_id: str, task_id: str) -> None: ...

    def get_storage_key(self, document_id: str) -> str | None: ...

    def save_ai_text(self, document_id: str, ai_text: str, privacy_policy_version: str) -> None: ...

    def save_chunks(self, document_id: str, chunks: list[DocumentChunk]) -> None: ...

    def save_document(self, document: DocumentResponse) -> None: ...

    def set_document_status(
        self,
        document_id: str,
        status: DocumentStatus,
        *,
        needs_review: bool | None = None,
        error: str | None = None,
    ) -> None: ...

    def set_step(
        self,
        document_id: str,
        name: ProcessingStepName,
        status: ProcessingStepStatus,
        error: str | None = None,
    ) -> None: ...

    def set_branch(
        self,
        document_id: str,
        name: BranchStatusName,
        status: ProcessingStepStatus,
        error: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None: ...

    def fail_running_work(self, document_id: str, error: str) -> None: ...

    def delete_document(self, document_id: str) -> None: ...


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[str, DocumentResponse] = {}
        self._chunks: dict[str, list[DocumentChunk]] = {}
        self._statuses: dict[str, DocumentStatusResponse] = {}
        self._ai_texts: dict[str, str] = {}
        self._branch_results: dict[str, dict[str, dict[str, Any]]] = {}
        self._storage_keys: dict[str, str] = {}
        self._lock = Lock()

    def get_document(self, document_id: str) -> DocumentResponse | None:
        with self._lock:
            document = self._documents.get(document_id)
            if document is not None:
                return document
            status = self._statuses.get(document_id)
            if status is None:
                return None
            return _pending_document_from_status(status)

    def get_status(self, document_id: str) -> DocumentStatusResponse | None:
        with self._lock:
            return self._statuses.get(document_id)

    def list_chunks(self, document_ids: list[str] | None = None) -> list[DocumentChunk]:
        with self._lock:
            if document_ids:
                return [chunk for doc_id in document_ids for chunk in self._chunks.get(doc_id, [])]
            return [chunk for chunks in self._chunks.values() for chunk in chunks]

    def get_ai_text(self, document_id: str) -> str | None:
        with self._lock:
            return self._ai_texts.get(document_id)

    def get_branch_results(self, document_id: str) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._branch_results.get(document_id, {}))

    def init_document(
        self,
        *,
        document_id: str,
        filename: str,
        content_hash: str,
        status: DocumentStatus,
        storage_key: str | None = None,
        task_id: str | None = None,
        processing_backend: str | None = None,
    ) -> None:
        del content_hash, task_id, processing_backend
        with self._lock:
            self._statuses[document_id] = _new_status(document_id, filename, status)
            self._documents.pop(document_id, None)
            self._chunks.pop(document_id, None)
            self._ai_texts.pop(document_id, None)
            self._branch_results.pop(document_id, None)
            if storage_key is not None:
                self._storage_keys[document_id] = storage_key

    def set_processing_task_id(self, document_id: str, task_id: str) -> None:
        # The in-memory repo has no durable task-id column; the service tracks
        # task ids separately, so this is intentionally a no-op.
        del document_id, task_id

    def get_storage_key(self, document_id: str) -> str | None:
        with self._lock:
            return self._storage_keys.get(document_id)

    def save_ai_text(self, document_id: str, ai_text: str, privacy_policy_version: str) -> None:
        del privacy_policy_version
        with self._lock:
            self._ai_texts[document_id] = ai_text

    def save_chunks(self, document_id: str, chunks: list[DocumentChunk]) -> None:
        with self._lock:
            self._chunks[document_id] = chunks

    def save_document(self, document: DocumentResponse) -> None:
        with self._lock:
            self._documents[document.document_id] = document
            current = self._statuses.get(document.document_id)
            if current is not None:
                self._statuses[document.document_id] = current.model_copy(
                    update={
                        "status": document.status,
                        "needs_review": document.needs_review,
                        "error": document.error,
                    }
                )

    def set_document_status(
        self,
        document_id: str,
        status: DocumentStatus,
        *,
        needs_review: bool | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            current = self._statuses.get(document_id)
            if current is None:
                return
            self._statuses[document_id] = current.model_copy(
                update={
                    "status": status,
                    "needs_review": current.needs_review if needs_review is None else needs_review,
                    "error": error,
                }
            )

    def set_step(
        self,
        document_id: str,
        name: ProcessingStepName,
        status: ProcessingStepStatus,
        error: str | None = None,
    ) -> None:
        with self._lock:
            current = self._statuses.get(document_id)
            if current is None:
                return
            steps = [
                step.model_copy(update={"status": status, "error": error})
                if step.name == name
                else step
                for step in current.steps
            ]
            self._statuses[document_id] = current.model_copy(update={"steps": steps})

    def set_branch(
        self,
        document_id: str,
        name: BranchStatusName,
        status: ProcessingStepStatus,
        error: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            current = self._statuses.get(document_id)
            if current is None:
                return
            branches = [
                branch.model_copy(update={"status": status, "error": error})
                if branch.name == name
                else branch
                for branch in current.branches
            ]
            self._statuses[document_id] = current.model_copy(update={"branches": branches})
            if result is not None:
                self._branch_results.setdefault(document_id, {})[name] = result
            else:
                self._branch_results.get(document_id, {}).pop(name, None)

    def fail_running_work(self, document_id: str, error: str) -> None:
        with self._lock:
            current = self._statuses.get(document_id)
            if current is None:
                return
            steps = [
                step.model_copy(update={"status": "failed", "error": error})
                if step.status == "running"
                else step
                for step in current.steps
            ]
            branches = [
                branch.model_copy(update={"status": "failed", "error": error})
                if branch.status == "running"
                else branch
                for branch in current.branches
            ]
            self._statuses[document_id] = current.model_copy(
                update={"steps": steps, "branches": branches}
            )

    def delete_document(self, document_id: str) -> None:
        with self._lock:
            self._documents.pop(document_id, None)
            self._statuses.pop(document_id, None)
            self._chunks.pop(document_id, None)
            self._ai_texts.pop(document_id, None)
            self._branch_results.pop(document_id, None)
            self._storage_keys.pop(document_id, None)


class PostgresDocumentRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        settings = get_settings()
        self._dimension = settings.postgres_vector_dimension
        self._operator_class = settings.postgres_vector_operator_class
        self._index_type = settings.postgres_vector_index_type
        self._schema_ready = False
        self._schema_lock = Lock()

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            if not ensure_pgvector_schema(
                self.database_url,
                dimension=self._dimension,
                operator_class=self._operator_class,
                index_type=self._index_type,
            ):
                raise ValueError("Durable document schema is not ready.")
            self._schema_ready = True

    def get_document(self, document_id: str) -> DocumentResponse | None:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                        document_id,
                        filename,
                        status,
                        summary,
                        document_type,
                        extracted_fields,
                        chunk_count,
                        needs_review,
                        extraction_confidence,
                        privacy_policy_version,
                        processing_error
                    from documents
                    where document_id = %s
                    """,
                    (document_id,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return DocumentResponse(
            document_id=row[0],
            filename=row[1],
            status=row[2],
            summary=row[3] or "",
            document_type=row[4] or "unknown",
            extracted_fields=ExtractedFields.model_validate(row[5] or {}),
            chunk_count=row[6] or 0,
            needs_review=bool(row[7]),
            extraction_confidence=row[8],
            privacy_policy_version=row[9],
            error=row[10],
        )

    def get_status(self, document_id: str) -> DocumentStatusResponse | None:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select document_id, filename, status, needs_review, processing_error
                    from documents
                    where document_id = %s
                    """,
                    (document_id,),
                )
                document = cursor.fetchone()
                if document is None:
                    return None
                cursor.execute(
                    """
                    select name, status, error
                    from processing_steps
                    where document_id = %s
                    order by case name
                        when 'parsing' then 1
                        when 'privacy_processing' then 2
                        when 'chunking' then 3
                        else 99
                    end
                    """,
                    (document_id,),
                )
                step_rows = cursor.fetchall()
                cursor.execute(
                    """
                    select name, status, error
                    from document_branches
                    where document_id = %s
                    order by case name
                        when 'embedding' then 1
                        when 'extracting' then 2
                        when 'summarising' then 3
                        else 99
                    end
                    """,
                    (document_id,),
                )
                branch_rows = cursor.fetchall()

        steps = (
            [ProcessingStep(name=row[0], status=row[1], error=row[2]) for row in step_rows]
            if step_rows
            else [ProcessingStep(name=name) for name in DEFAULT_STEPS]
        )
        branches = (
            [BranchStatus(name=row[0], status=row[1], error=row[2]) for row in branch_rows]
            if branch_rows
            else [BranchStatus(name=name) for name in DEFAULT_BRANCHES]
        )
        return DocumentStatusResponse(
            document_id=document[0],
            filename=document[1],
            status=document[2],
            needs_review=bool(document[3]),
            steps=steps,
            branches=branches,
            error=document[4],
        )

    def list_chunks(self, document_ids: list[str] | None = None) -> list[DocumentChunk]:
        self._ensure_schema()
        import psycopg

        where = ""
        params: tuple[object, ...] = ()
        if document_ids:
            where = "where document_id = any(%s)"
            params = (document_ids,)
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select
                        chunk_id,
                        document_id,
                        filename,
                        text,
                        page_number,
                        section_title,
                        chunk_index
                    from document_chunks
                    {where}
                    order by document_id, chunk_index
                    """,
                    params,
                )
                rows = cursor.fetchall()
        return [
            DocumentChunk(
                chunk_id=row[0],
                document_id=row[1],
                filename=row[2],
                text=row[3],
                page_number=row[4],
                section_title=row[5],
                chunk_index=row[6],
            )
            for row in rows
        ]

    def get_ai_text(self, document_id: str) -> str | None:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select ai_text from documents where document_id = %s",
                    (document_id,),
                )
                row = cursor.fetchone()
        return row[0] if row else None

    def get_branch_results(self, document_id: str) -> dict[str, dict[str, Any]]:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select name, result_json
                    from document_branches
                    where document_id = %s and result_json is not null
                    """,
                    (document_id,),
                )
                rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}

    def init_document(
        self,
        *,
        document_id: str,
        filename: str,
        content_hash: str,
        status: DocumentStatus,
        storage_key: str | None = None,
        task_id: str | None = None,
        processing_backend: str | None = None,
    ) -> None:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into documents (
                        document_id,
                        filename,
                        content_hash,
                        status,
                        storage_key,
                        processing_task_id,
                        processing_backend,
                        summary,
                        document_type,
                        extracted_fields,
                        chunk_count,
                        needs_review,
                        processing_error
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, '', 'unknown', '{}'::jsonb, 0, false, null)
                    on conflict (document_id) do update set
                        filename = excluded.filename,
                        status = excluded.status,
                        storage_key = excluded.storage_key,
                        processing_task_id = excluded.processing_task_id,
                        processing_backend = excluded.processing_backend,
                        summary = '',
                        document_type = 'unknown',
                        extracted_fields = '{}'::jsonb,
                        chunk_count = 0,
                        needs_review = false,
                        extraction_confidence = null,
                        privacy_policy_version = null,
                        processing_error = null,
                        ai_text = null,
                        updated_at = now()
                    """,
                    (
                        document_id,
                        filename,
                        content_hash,
                        status,
                        storage_key,
                        task_id,
                        processing_backend,
                    ),
                )
                for name in DEFAULT_STEPS:
                    self._upsert_step(cursor, document_id, name, "pending", None)
                for name in DEFAULT_BRANCHES:
                    self._upsert_branch(cursor, document_id, name, "pending", None, None)
            connection.commit()

    def set_processing_task_id(self, document_id: str, task_id: str) -> None:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update documents
                    set processing_task_id = %s,
                        updated_at = now()
                    where document_id = %s
                    """,
                    (task_id, document_id),
                )
            connection.commit()

    def get_storage_key(self, document_id: str) -> str | None:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select storage_key
                    from documents
                    where document_id = %s
                    """,
                    (document_id,),
                )
                row = cursor.fetchone()
        return row[0] if row else None

    def save_ai_text(self, document_id: str, ai_text: str, privacy_policy_version: str) -> None:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update documents
                    set ai_text = %s,
                        privacy_policy_version = %s,
                        updated_at = now()
                    where document_id = %s
                    """,
                    (ai_text, privacy_policy_version, document_id),
                )
            connection.commit()

    def save_chunks(self, document_id: str, chunks: list[DocumentChunk]) -> None:
        # This repository owns chunk text/metadata as part of durable document
        # state. PgVectorStore later updates the same rows with embeddings; keep
        # the call order as save_chunks -> vector_store.index to avoid wiping
        # freshly computed vectors.
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("delete from document_chunks where document_id = %s", (document_id,))
                for chunk in chunks:
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
                        values (%s, %s, %s, %s, %s, %s, %s, null)
                        on conflict (chunk_id) do update set
                            filename = excluded.filename,
                            text = excluded.text,
                            page_number = excluded.page_number,
                            section_title = excluded.section_title,
                            chunk_index = excluded.chunk_index
                        """,
                        (
                            chunk.chunk_id,
                            chunk.document_id,
                            chunk.filename,
                            chunk.text,
                            chunk.page_number,
                            chunk.section_title,
                            chunk.chunk_index,
                        ),
                    )
                cursor.execute(
                    """
                    update documents
                    set chunk_count = %s,
                        updated_at = now()
                    where document_id = %s
                    """,
                    (len(chunks), document_id),
                )
            connection.commit()

    def save_document(self, document: DocumentResponse) -> None:
        self._ensure_schema()
        import psycopg
        from psycopg.types.json import Jsonb

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update documents
                    set status = %s,
                        summary = %s,
                        document_type = %s,
                        extracted_fields = %s,
                        chunk_count = %s,
                        needs_review = %s,
                        extraction_confidence = %s,
                        privacy_policy_version = %s,
                        processing_error = %s,
                        updated_at = now()
                    where document_id = %s
                    """,
                    (
                        document.status,
                        document.summary,
                        document.document_type,
                        Jsonb(document.extracted_fields.model_dump()),
                        document.chunk_count,
                        document.needs_review,
                        document.extraction_confidence,
                        document.privacy_policy_version,
                        document.error,
                        document.document_id,
                    ),
                )
            connection.commit()

    def set_document_status(
        self,
        document_id: str,
        status: DocumentStatus,
        *,
        needs_review: bool | None = None,
        error: str | None = None,
    ) -> None:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update documents
                    set status = %s,
                        needs_review = coalesce(%s, needs_review),
                        processing_error = %s,
                        updated_at = now()
                    where document_id = %s
                    """,
                    (status, needs_review, error, document_id),
                )
            connection.commit()

    def set_step(
        self,
        document_id: str,
        name: ProcessingStepName,
        status: ProcessingStepStatus,
        error: str | None = None,
    ) -> None:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                self._upsert_step(cursor, document_id, name, status, error)
            connection.commit()

    def set_branch(
        self,
        document_id: str,
        name: BranchStatusName,
        status: ProcessingStepStatus,
        error: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                self._upsert_branch(cursor, document_id, name, status, error, result)
            connection.commit()

    def fail_running_work(self, document_id: str, error: str) -> None:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update processing_steps
                    set status = 'failed', error = %s, updated_at = now()
                    where document_id = %s and status = 'running'
                    """,
                    (error, document_id),
                )
                cursor.execute(
                    """
                    update document_branches
                    set status = 'failed', error = %s, updated_at = now()
                    where document_id = %s and status = 'running'
                    """,
                    (error, document_id),
                )
            connection.commit()

    def delete_document(self, document_id: str) -> None:
        self._ensure_schema()
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("delete from documents where document_id = %s", (document_id,))
            connection.commit()

    @staticmethod
    def _upsert_step(
        cursor: object,
        document_id: str,
        name: str,
        status: str,
        error: str | None,
    ) -> None:
        cursor.execute(
            """
            insert into processing_steps (document_id, name, status, error, updated_at)
            values (%s, %s, %s, %s, now())
            on conflict (document_id, name) do update set
                status = excluded.status,
                error = excluded.error,
                updated_at = now()
            """,
            (document_id, name, status, error),
        )

    @staticmethod
    def _upsert_branch(
        cursor: object,
        document_id: str,
        name: str,
        status: str,
        error: str | None,
        result: dict[str, Any] | None,
    ) -> None:
        from psycopg.types.json import Jsonb

        cursor.execute(
            """
            insert into document_branches (
                document_id,
                name,
                status,
                error,
                result_json,
                updated_at
            )
            values (%s, %s, %s, %s, %s, now())
            on conflict (document_id, name) do update set
                status = excluded.status,
                error = excluded.error,
                result_json = excluded.result_json,
                updated_at = now()
            """,
            (document_id, name, status, error, Jsonb(result) if result is not None else None),
        )


def build_document_repository() -> DocumentRepository:
    settings = get_settings()
    if settings.durable_document_state_enabled:
        if not settings.database_url:
            raise ValueError("VECTOR_STORE_BACKEND=postgres requires DATABASE_URL.")
        return PostgresDocumentRepository(settings.database_url)
    return InMemoryDocumentRepository()


def _new_status(
    document_id: str,
    filename: str,
    status: DocumentStatus,
) -> DocumentStatusResponse:
    return DocumentStatusResponse(
        document_id=document_id,
        filename=filename,
        status=status,
        steps=[ProcessingStep(name=name) for name in DEFAULT_STEPS],
        branches=[BranchStatus(name=name) for name in DEFAULT_BRANCHES],
    )


def _pending_document_from_status(status: DocumentStatusResponse) -> DocumentResponse:
    return DocumentResponse(
        document_id=status.document_id,
        filename=status.filename,
        status=status.status,
        summary="",
        document_type="unknown",
        extracted_fields=ExtractedFields(),
        chunk_count=0,
        needs_review=status.needs_review,
        error=status.error,
    )
