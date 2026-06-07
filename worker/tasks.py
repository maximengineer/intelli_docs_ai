from __future__ import annotations

from app.core.settings import get_settings
from app.documents.service import get_document_service
from celery.exceptions import SoftTimeLimitExceeded

from worker.worker import celery_app

_SETTINGS = get_settings()
_TASK_LIMITS = {
    "soft_time_limit": _SETTINGS.celery_task_soft_time_limit_seconds,
    "time_limit": _SETTINGS.celery_task_time_limit_seconds,
}


@celery_app.task(name="intellidocs.seed_document_from_storage", **_TASK_LIMITS)
def seed_document_from_storage(
    document_id: str,
    filename: str,
    storage_key: str,
) -> dict[str, object]:
    return get_document_service().seed_document_from_storage(document_id, filename, storage_key)


@celery_app.task(name="intellidocs.embed_branch", **_TASK_LIMITS)
def embed_branch(payload: dict[str, object]) -> dict[str, object]:
    document_id = str(payload["document_id"])
    return get_document_service().run_embedding_branch(document_id)


@celery_app.task(name="intellidocs.extract_branch", **_TASK_LIMITS)
def extract_branch(payload: dict[str, object]) -> dict[str, object]:
    document_id = str(payload["document_id"])
    return get_document_service().run_extraction_branch(document_id)


@celery_app.task(name="intellidocs.summarize_branch", **_TASK_LIMITS)
def summarize_branch(payload: dict[str, object]) -> dict[str, object]:
    document_id = str(payload["document_id"])
    return get_document_service().run_summary_branch(document_id)


@celery_app.task(name="intellidocs.aggregate_document", **_TASK_LIMITS)
def aggregate_document(results: list[dict[str, object]]) -> dict[str, object]:
    document_id = str(results[0].get("document_id", "")) if results else ""
    try:
        return get_document_service().aggregate_document(document_id)
    except SoftTimeLimitExceeded as exc:
        get_document_service().mark_document_failed(document_id, str(exc))
        raise


@celery_app.task(name="intellidocs.document_chord_error")
def document_chord_error(*args: object, **kwargs: object) -> dict[str, str]:
    document_id = _extract_document_id(args, kwargs)
    request = args[1] if len(args) > 1 else kwargs.get("request", "")
    exc = _extract_exception(args, kwargs)
    get_document_service().mark_document_failed(document_id, str(exc))
    return {
        "document_id": document_id,
        "status": "failed",
        "request": str(request),
        "error": str(exc),
    }


def _extract_document_id(args: tuple[object, ...], kwargs: dict[str, object]) -> str:
    explicit = kwargs.get("document_id")
    if isinstance(explicit, str) and explicit:
        return explicit
    for arg in args:
        if isinstance(arg, str) and arg.startswith("doc_"):
            return arg
    return "unknown_document"


def _extract_exception(args: tuple[object, ...], kwargs: dict[str, object]) -> object:
    explicit = kwargs.get("exc")
    if explicit is not None:
        return explicit
    for arg in args:
        if isinstance(arg, BaseException):
            return arg
    return "Celery chord failed"


def build_document_canvas(document_id: str, filename: str, storage_key: str):
    """Assemble the durable Celery canvas: seed -> group(branches) -> aggregate."""

    from celery import chain, chord

    branches = [embed_branch.s(), extract_branch.s(), summarize_branch.s()]
    return chain(
        seed_document_from_storage.s(document_id, filename, storage_key),
        chord(branches, aggregate_document.s()).on_error(document_chord_error.s(document_id)),
    )
