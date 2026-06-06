from __future__ import annotations

import logging
import time
import uuid

from app.core.settings import get_settings
from app.documents.service import get_document_service
from app.llm.client import LLMClient, get_llm_client
from app.rag.citations import map_citations
from app.rag.generator import FALLBACK_ANSWER, generate_answer_with_placeholders
from app.rag.retriever import Retriever
from app.rag.schemas import QARequest, QAResponse

logger = logging.getLogger(__name__)


class QAService:
    def __init__(self, retriever: Retriever, llm_client: LLMClient | None = None) -> None:
        self.retriever = retriever
        self.llm_client = llm_client if llm_client is not None else get_llm_client()

    def answer(self, request: QARequest) -> QAResponse:
        started = time.perf_counter()
        run_id = "run_" + uuid.uuid4().hex[:16]
        try:
            context = self.retriever.retrieve(request)
            settings = get_settings()
            if not context or context[0].score < settings.min_relevance_score:
                return self._insufficient(run_id)

            draft = generate_answer_with_placeholders(request.question, context, self.llm_client)
            answer, sources, supported = map_citations(draft, context)
            if not supported or not sources:
                return self._insufficient(run_id)
            return QAResponse(run_id=run_id, answer=answer, status="success", sources=sources)
        except Exception as exc:
            logger.exception("qa_failed run_id=%s", run_id)
            return QAResponse(run_id=run_id, answer="", status="failed", sources=[], error=str(exc))
        finally:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info("qa_completed run_id=%s latency_ms=%s", run_id, elapsed_ms)

    @staticmethod
    def _insufficient(run_id: str) -> QAResponse:
        return QAResponse(
            run_id=run_id,
            answer=FALLBACK_ANSWER,
            status="insufficient_information",
            sources=[],
        )


_qa_service = QAService(Retriever(get_document_service()))


def get_qa_service() -> QAService:
    return _qa_service
