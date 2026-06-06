from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# Deterministic by default: force the offline path so the committed numbers are
# reproducible and the script never makes paid LLM calls. Pass --use-llm to
# evaluate the real OpenRouter + embedding path configured in .env. Must run
# before importing the app so the cached settings/singletons pick it up.
USE_LLM = "--use-llm" in sys.argv
if not USE_LLM:
    os.environ["ENABLE_LLM"] = "false"
    os.environ["EMBEDDING_BACKEND"] = "hash"
    os.environ["VECTOR_STORE_BACKEND"] = "memory"

from app.core.settings import get_settings
from app.documents.service import DocumentService
from app.evaluation.datasets import load_jsonl
from app.evaluation.extraction_eval import extraction_field_accuracy
from app.evaluation.report import average
from app.evaluation.retrieval_eval import citation_coverage, document_hit_at_k
from app.rag.retriever import Retriever
from app.rag.schemas import QARequest
from app.rag.service import QAService

SAMPLES = ROOT / "data" / "sample_documents"
EVAL = ROOT / "data" / "evaluation"


def main() -> None:
    document_service = DocumentService()
    qa_service = QAService(Retriever(document_service))

    filename_to_doc_id: dict[str, str] = {}
    for path in sorted(SAMPLES.glob("*.txt")):
        document = document_service.upload(path.name, path.read_bytes())
        filename_to_doc_id[path.name] = document.document_id

    latencies: list[float] = []
    answer_count = 0
    cited_answer_count = 0
    document_hit_scores: list[float] = []
    unsupported_total = 0
    unsupported_rejected = 0

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
        doc_id = filename_to_doc_id[row["filename"]]
        document = document_service.get(doc_id)
        if document:
            extraction_scores.append(
                extraction_field_accuracy(document.extracted_fields, row["expected_fields"])
            )

    settings = get_settings()
    report = {
        "embedding_backend": settings.resolve_embedding_backend(),
        "llm_enabled": settings.llm_enabled,
        "documents_loaded": len(filename_to_doc_id),
        "document_hit_at_5": average(document_hit_scores),
        "citation_coverage": citation_coverage(answer_count, cited_answer_count),
        "unsupported_answer_rejection_rate": (
            unsupported_rejected / unsupported_total if unsupported_total else 0.0
        ),
        "extraction_field_accuracy": average(extraction_scores),
        "average_latency_ms": round(average(latencies), 2),
        "notes": "Measured on the local synthetic Phase 1 dataset. These are not benchmark claims.",
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
