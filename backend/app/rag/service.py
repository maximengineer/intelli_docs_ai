from __future__ import annotations

import logging
import time
import uuid

from app.core.settings import get_settings
from app.documents.service import get_document_service
from app.llm.client import LLMClient, get_llm_client
from app.observability.costs import TokenUsage, estimate_cost_usd, estimate_tokens
from app.observability.run_logger import log_run_event
from app.rag.citations import map_citations
from app.rag.critic import SupportCheckResult, check_answer_support
from app.rag.generator import FALLBACK_ANSWER, generate_answer_with_placeholders
from app.rag.retriever import Retriever
from app.rag.schemas import QAMetrics, QARequest, QAResponse, RetrievedChunk

logger = logging.getLogger(__name__)
_DEFAULT_LLM_CLIENT = object()


def new_run_id() -> str:
    return "run_" + uuid.uuid4().hex[:16]


class QAService:
    def __init__(
        self,
        retriever: Retriever,
        llm_client: LLMClient | None | object = _DEFAULT_LLM_CLIENT,
    ) -> None:
        self.retriever = retriever
        self.llm_client = get_llm_client() if llm_client is _DEFAULT_LLM_CLIENT else llm_client

    def answer(self, request: QARequest, run_id: str | None = None) -> QAResponse:
        started = time.perf_counter()
        run_id = run_id or new_run_id()
        try:
            if self.llm_client is not None:
                self.llm_client.pop_usage()  # clear any stale per-thread usage
            retrieval = self.retriever.retrieve(request)
            context = retrieval.context
            settings = get_settings()
            # Gate on the best raw-retrieval cosine, not the post-rerank ordering.
            best_candidate_score = retrieval.candidates[0].score if retrieval.candidates else 0.0
            if not context or best_candidate_score < settings.min_relevance_score:
                metrics = self._metrics(
                    run_id=run_id,
                    started=started,
                    question=request.question,
                    context=context,
                    candidates_retrieved=len(retrieval.candidates),
                    answer=FALLBACK_ANSWER,
                    citation_count=0,
                    support_check=SupportCheckResult(
                        supported=False,
                        reason="relevance_below_threshold",
                    ),
                )
                return self._insufficient(run_id, metrics)

            draft = generate_answer_with_placeholders(request.question, context, self.llm_client)
            answer, sources, supported = map_citations(draft, context)
            if not supported or not sources:
                metrics = self._metrics(
                    run_id=run_id,
                    started=started,
                    question=request.question,
                    context=context,
                    candidates_retrieved=len(retrieval.candidates),
                    answer=FALLBACK_ANSWER,
                    citation_count=0,
                    support_check=SupportCheckResult(
                        supported=False,
                        reason="citation_mapping_failed",
                    ),
                )
                return self._insufficient(run_id, metrics)
            support_check = check_answer_support(answer, sources, context)
            if not support_check.supported:
                metrics = self._metrics(
                    run_id=run_id,
                    started=started,
                    question=request.question,
                    context=context,
                    candidates_retrieved=len(retrieval.candidates),
                    answer=FALLBACK_ANSWER,
                    citation_count=0,
                    support_check=support_check,
                )
                return self._insufficient(run_id, metrics)
            metrics = self._metrics(
                run_id=run_id,
                started=started,
                question=request.question,
                context=context,
                candidates_retrieved=len(retrieval.candidates),
                answer=answer,
                citation_count=len(sources),
                support_check=support_check,
            )
            return QAResponse(
                run_id=run_id,
                answer=answer,
                status="success",
                sources=sources,
                metrics=metrics,
            )
        except Exception as exc:
            logger.exception("qa_failed run_id=%s", run_id)
            return QAResponse(run_id=run_id, answer="", status="failed", sources=[], error=str(exc))
        finally:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info("qa_completed run_id=%s latency_ms=%s", run_id, elapsed_ms)

    def _metrics(
        self,
        *,
        run_id: str,
        started: float,
        question: str,
        context: list[RetrievedChunk],
        candidates_retrieved: int,
        answer: str,
        citation_count: int,
        support_check: SupportCheckResult | None = None,
    ) -> QAMetrics:
        settings = get_settings()
        usage = self.llm_client.pop_usage() if self.llm_client is not None else None
        if usage is None:
            # No real provider usage (offline heuristic, or no LLM call this turn):
            # fall back to a clearly-approximate word-count estimate.
            input_text = question + "\n" + "\n".join(chunk.text for chunk in context)
            usage = TokenUsage(
                input_tokens=estimate_tokens(input_text),
                output_tokens=estimate_tokens(answer),
            )
        model_name = settings.llm_model if self.llm_client is not None else "offline-heuristic"
        metrics = QAMetrics(
            latency_ms=int((time.perf_counter() - started) * 1000),
            candidates_retrieved=candidates_retrieved,
            context_chunks_used=len(context),
            citation_count=citation_count,
            model_name=model_name,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            estimated_cost_usd=estimate_cost_usd(usage),
            price_table_as_of=settings.price_table_as_of,
            reranker_enabled=settings.reranker_enabled,
            support_check_passed=support_check.supported if support_check else None,
            support_check_reason=support_check.reason if support_check else None,
        )
        log_run_event(run_id=run_id, event="qa_metrics", **metrics.model_dump())
        return metrics

    @staticmethod
    def _insufficient(run_id: str, metrics: QAMetrics | None = None) -> QAResponse:
        return QAResponse(
            run_id=run_id,
            answer=FALLBACK_ANSWER,
            status="insufficient_information",
            sources=[],
            metrics=metrics,
        )


_qa_service = QAService(Retriever(get_document_service()))


def get_qa_service() -> QAService:
    return _qa_service
