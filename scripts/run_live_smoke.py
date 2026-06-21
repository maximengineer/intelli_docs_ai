from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

import httpx

LIVE_DOCUMENT = b"""Invoice
Vendor: Live Test Supplies Ltd
Invoice Date: 2026-06-07
Due Date: 2026-06-30
Total Amount: EUR 4,321.09
Payment terms: Payment is due within 23 days.
"""


def main() -> None:
    started = time.monotonic()
    api_url = os.environ.get("INTELLIDOCS_API_URL", "http://backend:8000").rstrip("/")
    http_timeout = float(os.environ.get("LIVE_HTTP_TIMEOUT_SECONDS", "120"))
    poll_deadline = float(os.environ.get("LIVE_POLL_DEADLINE_SECONDS", "240"))
    embedding_backend = os.environ.get("EMBEDDING_BACKEND", "hash")
    require_provider_embeddings = _truthy(os.environ.get("LIVE_REQUIRE_PROVIDER_EMBEDDINGS"))

    if require_provider_embeddings and embedding_backend != "openrouter":
        raise SystemExit(
            "LIVE_REQUIRE_PROVIDER_EMBEDDINGS=true requires EMBEDDING_BACKEND=openrouter."
        )

    run_token = uuid.uuid4().hex
    live_document = LIVE_DOCUMENT + f"Smoke Run: {run_token}\n".encode()

    with httpx.Client(timeout=http_timeout) as client:
        _emit("readiness", "started")
        ready = _wait_for_ready(client, api_url, poll_deadline)
        if ready.get("vector_store_backend") != "postgres":
            raise SystemExit(f"Live backend is not using Postgres: {ready!r}")
        _emit("readiness", "completed")

        _emit("upload", "started")
        upload = client.post(
            f"{api_url}/documents/upload",
            files={
                "file": (
                    f"live-smoke-invoice-{run_token}.txt",
                    live_document,
                    "text/plain",
                )
            },
        )
        upload.raise_for_status()
        upload_payload = upload.json()
        document_id = str(upload_payload["document_id"])
        _emit("upload", "accepted", document_id=document_id)

        _emit("document_processing", "started", document_id=document_id)
        status_payload = _wait_for_terminal_status(
            client,
            api_url,
            document_id,
            poll_deadline,
        )
        if status_payload["status"] != "completed":
            raise SystemExit(f"Document processing failed: {status_payload!r}")
        _emit("document_processing", "completed", document_id=document_id)

        document_response = client.get(f"{api_url}/documents/{document_id}")
        document_response.raise_for_status()
        document = document_response.json()
        _validate_document(document)

        _emit("qa", "started", document_id=document_id)
        qa_response = client.post(
            f"{api_url}/qa",
            json={
                "question": "What is the total amount on the Live Test Supplies invoice?",
                "document_ids": [document_id],
            },
        )
        qa_response.raise_for_status()
        qa = qa_response.json()
        metrics = _validate_qa(qa, document_id)
        _emit("qa", "completed", run_id=qa["run_id"])

    result = {
        "status": "completed",
        "llm_model": metrics["model_name"],
        "embedding_backend": embedding_backend,
        "embedding_model": (
            os.environ.get("EMBEDDING_MODEL", "openai/text-embedding-3-small")
            if embedding_backend == "openrouter"
            else "local-hash-embedding"
        ),
        "document_id": document_id,
        "smoke_run": run_token,
        "document_status": document["status"],
        "chunk_count": document["chunk_count"],
        "qa_status": qa["status"],
        "citation_count": len(qa["sources"]),
        "run_id": qa["run_id"],
        "token_usage_source": metrics["token_usage_source"],
        "input_tokens": metrics["input_tokens"],
        "output_tokens": metrics["output_tokens"],
        "estimated_cost_usd": metrics["estimated_cost_usd"],
        "cost_estimate_available": metrics["cost_estimate_available"],
        "price_table_as_of": metrics["price_table_as_of"],
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }
    print(json.dumps(result, indent=2), flush=True)


def _wait_for_ready(
    client: httpx.Client,
    api_url: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            response = client.get(f"{api_url}/ready")
            response.raise_for_status()
            last_payload = response.json()
            if last_payload.get("status") == "ready":
                return last_payload
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise SystemExit(f"Live backend did not become ready: {last_payload!r}")


def _wait_for_terminal_status(
    client: httpx.Client,
    api_url: str,
    document_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"{api_url}/documents/{document_id}/status")
        response.raise_for_status()
        last_payload = response.json()
        if last_payload.get("status") in {"completed", "failed"}:
            return last_payload
        time.sleep(0.5)
    raise SystemExit(f"Live document did not reach a terminal status: {last_payload!r}")


def _validate_document(document: dict[str, Any]) -> None:
    fields = document.get("extracted_fields") or {}
    amount = fields.get("amount")
    if document.get("status") != "completed" or int(document.get("chunk_count", 0)) != 1:
        raise SystemExit(f"Unexpected live document result: {document!r}")
    if fields.get("vendor") != "Live Test Supplies Ltd":
        raise SystemExit(f"Provider extraction returned the wrong vendor: {fields!r}")
    if not isinstance(amount, int | float) or abs(float(amount) - 4321.09) > 0.001:
        raise SystemExit(f"Provider extraction returned the wrong amount: {fields!r}")
    if fields.get("currency") != "EUR":
        raise SystemExit(f"Provider extraction returned the wrong currency: {fields!r}")
    if not str(document.get("summary", "")).strip():
        raise SystemExit("Provider summarisation returned an empty summary.")


def _validate_qa(qa: dict[str, Any], document_id: str) -> dict[str, Any]:
    sources = qa.get("sources") or []
    metrics = qa.get("metrics") or {}
    if qa.get("status") != "success":
        raise SystemExit(f"Live Q&A failed: {qa!r}")
    if len(sources) != 1 or sources[0].get("document_id") != document_id:
        raise SystemExit(f"Live Q&A returned unexpected citations: {sources!r}")
    if metrics.get("token_usage_source") != "provider":
        raise SystemExit(f"Live Q&A did not record provider usage: {metrics!r}")
    if metrics.get("model_name") == "offline-heuristic":
        raise SystemExit(f"Live Q&A used the offline answerer: {metrics!r}")
    return metrics


def _emit(stage: str, status: str, **fields: object) -> None:
    print(
        json.dumps({"event": "live_smoke", "stage": stage, "status": status, **fields}),
        flush=True,
    )


def _truthy(value: str | None) -> bool:
    return value is not None and value.lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    main()
