import json

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.settings import get_settings
from app.rag.schemas import QARequest, QAResponse, QAStreamEvent
from app.rag.service import get_qa_service, new_run_id

router = APIRouter(tags=["qa"])


@router.post("/qa", response_model=QAResponse)
def ask_question(request: QARequest) -> QAResponse:
    service = get_qa_service()
    return service.answer(request)


@router.post("/qa/stream")
def stream_question(request: QARequest) -> StreamingResponse:
    if not get_settings().streaming_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Streaming Q&A is disabled (STREAMING_ENABLED=false).",
        )
    return StreamingResponse(stream_question_events(request), media_type="application/x-ndjson")


def stream_question_events(request: QARequest):
    service = get_qa_service()

    # Generate the run_id up front so status events correlate with the final one.
    run_id = new_run_id()
    yield _json_event(
        QAStreamEvent(event="status", run_id=run_id, message="accepted_for_verification")
    )
    yield _json_event(
        QAStreamEvent(event="status", run_id=run_id, message="building_verified_answer")
    )
    response = service.answer(request, run_id=run_id)
    yield _json_event(
        QAStreamEvent(
            event="final",
            run_id=response.run_id,
            message=response.status,
            response=response,
        )
    )


def _json_event(event: QAStreamEvent) -> str:
    return json.dumps(event.model_dump(mode="json"), separators=(",", ":")) + "\n"
