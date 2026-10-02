from __future__ import annotations

import logging
import time
import uuid
from functools import lru_cache

from app.core.settings import get_settings
from app.documents.service import get_document_service
from app.llm.client import LLMClient, get_llm_client
from app.observability.costs import TokenUsage, estimate_cost_usd, estimate_tokens
from app.observability.run_logger import log_run_event
from app.rag.citations import map_citations
from app.rag.critic import SupportCheckResult, check_answer_support
from app.rag.generator import FALLBACK_ANSWER, generate_answer
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

            def refuse(
                support_check: SupportCheckResult,
                *,
                used_llm: bool = False,
                answer_generated: bool = True,
            ) -> QAResponse:
                metrics = self._metrics(
                    run_id=run_id,
                    started=started,
                    question=request.question,
                    context=context,
                    candidates_retrieved=len(retrieval.candidates),
                    answer=FALLBACK_ANSWER,
                    citation_count=0,
                    status="insufficient_information",
                    support_check=support_check,
                    used_llm=used_llm,
                    answer_generated=answer_generated,
                )
                return QAResponse(
                    run_id=run_id,
                    answer=FALLBACK_ANSWER,
                    status="insufficient_information",
                    sources=[],
                    metrics=metrics,
                )

            # Gate on the best raw-retrieval cosine, not the post-rerank ordering.
            best_candidate_score = retrieval.candidates[0].score if retrieval.candidates else 0.0
            if not context or best_candidate_score < get_settings().min_relevance_score:
                return refuse(
                    SupportCheckResult(supported=False, reason="relevance_below_threshold"),
                    answer_generated=False,
                )

            generated = generate_answer(request.question, context, self.llm_client)
            used_llm = generated.used_llm
            answer, sources, supported = map_citations(generated.text, context)
            # A refusal is a refusal even when the model also attached a citation
            # or wrapped it in prose: never return it as a cited success.
            declined = FALLBACK_ANSWER in " ".join(generated.text.split())
            if declined or not supported or not sources:
                if used_llm and not declined:
                    # The model answered but broke the citation contract (no or
                    # invalid tags). Log it: otherwise this looks like an
                    # ordinary refusal and the provider's weakness stays hidden.
                    logger.warning(
                        "llm_citation_contract_failed run_id=%s model=%s",
                        run_id,
                        self._llm_model_name(),
                    )
                reason = "answer_declined" if declined else "citation_mapping_failed"
                return refuse(SupportCheckResult(supported=False, reason=reason), used_llm=used_llm)
            support_check = check_answer_support(answer, sources, context, request.question)
            if not support_check.supported:
                return refuse(support_check, used_llm=used_llm)
            metrics = self._metrics(
                run_id=run_id,
                started=started,
                question=request.question,
                context=context,
                candidates_retrieved=len(retrieval.candidates),
                answer=answer,
                citation_count=len(sources),
                status="success",
                support_check=support_check,
                used_llm=used_llm,
            )
            return QAResponse(
                run_id=run_id,
                answer=answer,
                status="success",
                sources=sources,
                metrics=metrics,
            )
        except Exception as exc:
            log_run_event(run_id=run_id, event="qa_failed", status="failed", error=str(exc))
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
        status: str,
        support_check: SupportCheckResult | None = None,
        used_llm: bool = False,
        answer_generated: bool = True,
    ) -> QAMetrics:
        settings = get_settings()
        # Always pop so per-thread usage never leaks into the next run, but only
        # count it when the LLM actually produced this answer.
        popped = self.llm_client.pop_usage() if self.llm_client is not None else None
        usage = popped if used_llm else None
        if not answer_generated:
            # Refused before any answerer ran: no model, nothing consumed.
            usage = TokenUsage(source="none")
        elif usage is None:
            # No real provider usage (offline heuristic, provider without usage
            # metadata, or no LLM call this turn): a clearly-approximate estimate.
            input_text = question + "\n" + "\n".join(chunk.text for chunk in context)
            usage = TokenUsage(
                input_tokens=estimate_tokens(input_text),
                output_tokens=estimate_tokens(answer),
                source="estimate",
            )
        model_name: str | None
        if not answer_generated:
            model_name = None
        elif used_llm:
            model_name = self._llm_model_name()
        else:
            model_name = "offline-heuristic"
        prices_configured = bool(
            settings.llm_input_price_per_1m_tokens or settings.llm_output_price_per_1m_tokens
        )
        estimated_cost_usd: float | None
        if not used_llm or settings.llm_provider == "ollama":
            # No provider call, or a local model: the API cost is a known zero.
            # Local compute cost is out of scope.
            estimated_cost_usd = 0.0
            cost_estimate_available = True
        elif prices_configured:
            estimated_cost_usd = estimate_cost_usd(usage)
            cost_estimate_available = True
        else:
            estimated_cost_usd = None
            cost_estimate_available = False
        metrics = QAMetrics(
            latency_ms=int((time.perf_counter() - started) * 1000),
            candidates_retrieved=candidates_retrieved,
            context_chunks_used=len(context),
            citation_count=citation_count,
            model_name=model_name,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            token_usage_source=usage.source,
            estimated_cost_usd=estimated_cost_usd,
            cost_estimate_available=cost_estimate_available,
            price_table_as_of=settings.price_table_as_of,
            reranker_enabled=settings.reranker_enabled,
            support_check_passed=support_check.supported if support_check else None,
            support_check_reason=support_check.reason if support_check else None,
        )
        log_run_event(run_id=run_id, event="qa_metrics", status=status, **metrics.model_dump())
        return metrics

    def _llm_model_name(self) -> str:
        # The client knows which model it calls; settings are only a fallback
        # for clients (e.g. test doubles) that do not expose one.
        return getattr(self.llm_client, "model_name", None) or get_settings().active_llm_model


@lru_cache(maxsize=1)
def get_qa_service() -> QAService:
    """Process-wide Q&A service, built on first use rather than at import."""
    return QAService(Retriever(get_document_service()))
