from __future__ import annotations

from worker.worker import celery_app


@celery_app.task(name="intellidocs.parse_privacy_chunk")
def parse_privacy_chunk(document_id: str, filename: str, content_hex: str) -> dict[str, object]:
    """Chord header seed (contract scaffold).

    Returns the seed payload that the branch tasks fan out from. It deliberately
    does NOT run the document pipeline here: doing so would write document
    metadata into a process-local, API-invisible store. Durable cross-process
    document state is the prerequisite before this becomes the real upload path,
    so for now it only validates and forwards the identifiers.
    """

    bytes.fromhex(content_hex)  # validate payload shape without processing
    return {"document_id": document_id, "filename": filename}


@celery_app.task(name="intellidocs.embed_branch")
def embed_branch(payload: dict[str, object]) -> dict[str, object]:
    return {**payload, "branch": "embedding", "status": "completed"}


@celery_app.task(name="intellidocs.extract_branch")
def extract_branch(payload: dict[str, object]) -> dict[str, object]:
    return {**payload, "branch": "extracting", "status": "completed"}


@celery_app.task(name="intellidocs.summarize_branch")
def summarize_branch(payload: dict[str, object]) -> dict[str, object]:
    return {**payload, "branch": "summarising", "status": "completed"}


@celery_app.task(name="intellidocs.aggregate_document")
def aggregate_document(results: list[dict[str, object]]) -> dict[str, object]:
    document_id = str(results[0].get("document_id", "")) if results else ""
    return {
        "document_id": document_id,
        "status": "completed" if results else "failed",
        "branches": results,
    }


@celery_app.task(name="intellidocs.document_chord_error")
def document_chord_error(request: object, exc: object, traceback: object) -> dict[str, str]:
    del traceback
    return {
        "status": "failed",
        "request": str(request),
        "error": str(exc),
    }


def build_document_canvas(document_id: str, filename: str, content_hex: str):
    """Assemble the intended Celery canvas: seed -> group(branches) -> aggregate.

    Returns a real ``chain``/``chord`` so the fan-out shape is reviewable. It is
    intentionally not dispatched anywhere yet (durable document state is the
    prerequisite). Requires Celery to be installed.
    """

    from celery import chain, chord

    branches = [embed_branch.s(), extract_branch.s(), summarize_branch.s()]
    return chain(
        parse_privacy_chunk.s(document_id, filename, content_hex),
        chord(branches, aggregate_document.s()).on_error(document_chord_error.s()),
    )
