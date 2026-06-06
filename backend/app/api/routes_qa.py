from fastapi import APIRouter

from app.rag.schemas import QARequest, QAResponse
from app.rag.service import get_qa_service

router = APIRouter(tags=["qa"])


@router.post("/qa", response_model=QAResponse)
def ask_question(request: QARequest) -> QAResponse:
    service = get_qa_service()
    return service.answer(request)
