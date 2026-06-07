from __future__ import annotations

# ruff: noqa: I001

import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.settings import get_settings
from app.documents.service import DocumentService
from app.llm.client import get_llm_client
from app.rag.embeddings import HashEmbeddingModel, get_embedding_model
from app.rag.retriever import Retriever
from app.rag.schemas import QARequest
from app.rag.service import QAService


LIVE_DOCUMENT = b"""Invoice
Vendor: Live Test Supplies Ltd
Invoice Date: 2026-06-07
Due Date: 2026-06-30
Total Amount: EUR 4,321.09
Payment terms: Payment is due within 23 days.
"""


def main() -> None:
    settings = get_settings()
    if not settings.llm_enabled:
        raise SystemExit(
            "Live smoke requires ENABLE_LLM=true and OPENROUTER_API_KEY in the runtime env."
        )

    llm_client = get_llm_client()
    if llm_client is None:
        raise SystemExit("Live smoke could not initialise the configured LLM client.")

    provider_reply = llm_client.complete(
        "Reply with exactly: ok",
        temperature=0.0,
        max_tokens=8,
    )
    if "ok" not in provider_reply.lower():
        raise SystemExit(f"Unexpected provider smoke response: {provider_reply!r}")

    embedding_model = get_embedding_model()
    if _truthy(os.getenv("LIVE_REQUIRE_PROVIDER_EMBEDDINGS")) and isinstance(
        embedding_model, HashEmbeddingModel
    ):
        raise SystemExit(
            "LIVE_REQUIRE_PROVIDER_EMBEDDINGS=true but the active embedding model is hash."
        )

    run_token = uuid.uuid4().hex
    live_document = LIVE_DOCUMENT + f"Smoke Run: {run_token}\n".encode()

    document_service = DocumentService(llm_client=llm_client)
    document = document_service.upload(f"live-smoke-invoice-{run_token}.txt", live_document)
    if document.status != "completed" or document.chunk_count < 1:
        raise SystemExit(f"Document processing failed: {document.model_dump(mode='json')}")

    qa_service = QAService(Retriever(document_service), llm_client=llm_client)
    response = qa_service.answer(
        QARequest(question="What is the total amount on the Live Test Supplies invoice?")
    )
    if response.status != "success" or not response.sources:
        raise SystemExit(f"Live Q&A failed: {response.model_dump(mode='json')}")

    print(
        json.dumps(
            {
                "status": "completed",
                "llm_model": settings.llm_model,
                "embedding_backend": settings.resolve_embedding_backend(),
                "embedding_model": getattr(embedding_model, "name", type(embedding_model).__name__),
                "document_id": document.document_id,
                "smoke_run": run_token,
                "document_status": document.status,
                "chunk_count": document.chunk_count,
                "qa_status": response.status,
                "citation_count": len(response.sources),
                "run_id": response.run_id,
            },
            indent=2,
        )
    )


def _truthy(value: str | None) -> bool:
    return value is not None and value.lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    main()
