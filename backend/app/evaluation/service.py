from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from app.core.settings import get_settings
from app.documents.service import DocumentService
from app.evaluation.datasets import load_jsonl
from app.evaluation.extraction_eval import extraction_field_accuracy
from app.evaluation.report import average
from app.evaluation.retrieval_eval import citation_coverage, document_hit_at_k
from app.rag.embeddings import HashEmbeddingModel
from app.rag.retriever import Retriever
from app.rag.schemas import QARequest
from app.rag.service import QAService
from app.rag.vector_store import InMemoryVectorStore

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
SAMPLES = ROOT / "data" / "sample_documents"
EVAL = ROOT / "data" / "evaluation"


def run_offline_evaluation(force_offline: bool = True) -> dict[str, Any]:
    """Run the synthetic evaluation loop and return a metrics report.

    ``force_offline`` (the default, and always used by the API) pins deterministic,
    key-less, in-memory components so a run is reproducible and can never make
    paid LLM calls — important because the endpoint is unauthenticated.
    """

    if force_offline:
        document_service = DocumentService(
            llm_client=None, vector_store=InMemoryVectorStore(HashEmbeddingModel())
        )
        qa_service = QAService(Retriever(document_service), llm_client=None)
        embedding_backend = "hash"
        llm_enabled = False
    else:
        document_service = DocumentService()
        qa_service = QAService(Retriever(document_service))
        settings = get_settings()
        embedding_backend = settings.resolve_embedding_backend()
        llm_enabled = settings.llm_enabled

    sample_paths = sorted(SAMPLES.glob("*.txt"))
    if not sample_paths:
        return {
            "status": "no_dataset",
            "embedding_backend": embedding_backend,
            "llm_enabled": llm_enabled,
            "documents_loaded": 0,
            "notes": f"No sample documents found under {SAMPLES}.",
        }

    filename_to_doc_id: dict[str, str] = {}
    for path in sample_paths:
        document = document_service.upload(path.name, path.read_bytes())
        filename_to_doc_id[path.name] = document.document_id

    latencies: list[float] = []
    answer_count = 0
    cited_answer_count = 0
    document_hit_scores: list[float] = []
    unsupported_total = 0
    unsupported_rejected = 0
    support_checked = 0
    support_passed = 0

    for row in load_jsonl(EVAL / "questions.jsonl"):
        started = time.perf_counter()
        expected_document_ids = [
            filename_to_doc_id[filename]
            for filename in row.get("expected_filenames", [])
            if filename in filename_to_doc_id
        ]
        retrieved = qa_service.retriever.retrieve(QARequest(question=row["question"])).context
        if expected_document_ids:
            document_hit_scores.append(document_hit_at_k(retrieved, expected_document_ids, 5))
        response = qa_service.answer(QARequest(question=row["question"]))
        latencies.append((time.perf_counter() - started) * 1000)
        if response.metrics and response.metrics.support_check_passed is not None:
            support_checked += 1
            if response.metrics.support_check_passed:
                support_passed += 1
        if response.status == "success":
            answer_count += 1
            if response.sources:
                cited_answer_count += 1

    for row in load_jsonl(EVAL / "negative_questions.jsonl"):
        unsupported_total += 1
        response = qa_service.answer(QARequest(question=row["question"]))
        if response.status == "insufficient_information":
            unsupported_rejected += 1

    extraction_scores: list[float] = []
    for row in load_jsonl(EVAL / "expected_extractions.jsonl"):
        doc_id = filename_to_doc_id.get(row["filename"])
        if doc_id is None:
            continue
        document = document_service.get(doc_id)
        if document:
            extraction_scores.append(
                extraction_field_accuracy(document.extracted_fields, row["expected_fields"])
            )

    return {
        "status": "completed",
        "embedding_backend": embedding_backend,
        "llm_enabled": llm_enabled,
        "documents_loaded": len(filename_to_doc_id),
        "document_hit_at_5": average(document_hit_scores),
        "citation_coverage": citation_coverage(answer_count, cited_answer_count),
        "unsupported_answer_rejection_rate": (
            unsupported_rejected / unsupported_total if unsupported_total else 0.0
        ),
        "support_check_pass_rate": support_passed / support_checked if support_checked else 0.0,
        "extraction_field_accuracy": average(extraction_scores),
        "average_latency_ms": round(average(latencies), 2),
        "notes": "Measured on the local synthetic dataset. These are not benchmark claims.",
    }


@dataclass
class EvaluationRun:
    evaluation_id: str
    status: str  # "running" | "completed" | "failed"
    result: dict[str, Any] | None = None
    error: str | None = None


class EvaluationService:
    """Runs the offline evaluation asynchronously (the plan's async-only contract)."""

    def __init__(self) -> None:
        self._runs: dict[str, EvaluationRun] = {}
        self._lock = Lock()

    def submit(self) -> EvaluationRun:
        evaluation_id = "eval_" + uuid.uuid4().hex[:16]
        run = EvaluationRun(evaluation_id=evaluation_id, status="running")
        with self._lock:
            self._runs[evaluation_id] = run
        thread = threading.Thread(target=self._run, args=(evaluation_id,), daemon=True)
        thread.start()
        return run

    def get(self, evaluation_id: str) -> EvaluationRun | None:
        with self._lock:
            return self._runs.get(evaluation_id)

    def _run(self, evaluation_id: str) -> None:
        try:
            result = run_offline_evaluation(force_offline=True)
            self._update(evaluation_id, status="completed", result=result)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("evaluation_run_failed evaluation_id=%s", evaluation_id)
            self._update(evaluation_id, status="failed", error=str(exc))

    def _update(self, evaluation_id: str, **fields: Any) -> None:
        with self._lock:
            run = self._runs.get(evaluation_id)
            if run is None:
                return
            for key, value in fields.items():
                setattr(run, key, value)


_evaluation_service = EvaluationService()


def get_evaluation_service() -> EvaluationService:
    return _evaluation_service
