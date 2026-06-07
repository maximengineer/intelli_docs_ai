from __future__ import annotations

from typing import Literal

from app.core.settings import Settings

ProcessingBackend = Literal["thread", "celery"]


def resolve_processing_backend(settings: Settings) -> ProcessingBackend:
    backend = settings.document_processing_backend
    if backend == "celery" and not settings.durable_document_state_enabled:
        raise ValueError(
            "DOCUMENT_PROCESSING_BACKEND=celery requires VECTOR_STORE_BACKEND=postgres."
        )
    return backend
