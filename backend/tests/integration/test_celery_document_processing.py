import hashlib
import os
import time
import uuid

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_CELERY_INTEGRATION") != "1",
    reason=(
        "Set RUN_CELERY_INTEGRATION=1 and INTELLIDOCS_API_URL to run Docker "
        "Celery integration tests."
    ),
)


def test_celery_document_processing_round_trip() -> None:
    api_url = os.environ.get("INTELLIDOCS_API_URL", "http://127.0.0.1:7777").rstrip("/")
    content = _successful_content()

    with httpx.Client(timeout=10.0) as client:
        ready_payload = _wait_for_ready(client, api_url)
        assert ready_payload["checks"]["database"] is True
        assert ready_payload["checks"]["vector_store"] is True
        assert ready_payload["checks"]["celery_broker"] is True
        assert ready_payload["checks"]["celery_result_backend"] is True
        assert ready_payload["checks"]["celery_worker"] is True

        upload = client.post(
            f"{api_url}/documents/upload",
            files={"file": ("integration_invoice.txt", content, "text/plain")},
        )
        upload.raise_for_status()
        upload_payload = upload.json()
        document_id = upload_payload["document_id"]
        uuid.UUID(upload_payload["task_id"])

        status_payload = _wait_for_terminal_status(client, api_url, document_id)
        assert status_payload["status"] == "completed"
        assert status_payload["processing_backend"] == "celery"
        assert status_payload["task_id"] == upload_payload["task_id"]
        assert {step["status"] for step in status_payload["steps"]} == {"completed"}
        assert {branch["status"] for branch in status_payload["branches"]} == {"completed"}

        document = client.get(f"{api_url}/documents/{document_id}")
        document.raise_for_status()
        document_payload = document.json()
        assert document_payload["status"] == "completed"
        assert document_payload["extracted_fields"]["vendor"] == "Integration Ltd"


def test_celery_document_failure_is_durable() -> None:
    api_url = os.environ.get("INTELLIDOCS_API_URL", "http://127.0.0.1:7777").rstrip("/")
    corrupt_content = f"not-a-docx-{_integration_run_id()}".encode()

    with httpx.Client(timeout=10.0) as client:
        _wait_for_ready(client, api_url)
        upload = client.post(
            f"{api_url}/documents/upload",
            files={
                "file": (
                    "corrupt_integration.docx",
                    corrupt_content,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        upload.raise_for_status()
        upload_payload = upload.json()
        uuid.UUID(upload_payload["task_id"])

        status_payload = _wait_for_terminal_status(client, api_url, upload_payload["document_id"])

        assert status_payload["status"] == "failed"
        assert status_payload["processing_backend"] == "celery"
        assert status_payload["task_id"] == upload_payload["task_id"]
        assert status_payload["error"]
        parsing = next(step for step in status_payload["steps"] if step["name"] == "parsing")
        assert parsing["status"] == "failed"
        assert parsing["error"]


def test_completed_document_survives_backend_restart() -> None:
    api_url = os.environ.get("INTELLIDOCS_API_URL", "http://127.0.0.1:7777").rstrip("/")
    document_id = _document_id(_successful_content())

    with httpx.Client(timeout=10.0) as client:
        _wait_for_ready(client, api_url)
        status_response = client.get(f"{api_url}/documents/{document_id}/status")
        status_response.raise_for_status()
        status_payload = status_response.json()
        assert status_payload["status"] == "completed"
        assert status_payload["processing_backend"] == "celery"
        uuid.UUID(status_payload["task_id"])

        document_response = client.get(f"{api_url}/documents/{document_id}")
        document_response.raise_for_status()
        document_payload = document_response.json()
        assert document_payload["status"] == "completed"
        assert document_payload["extracted_fields"]["vendor"] == "Integration Ltd"


def _wait_for_ready(client: httpx.Client, api_url: str) -> dict[str, object]:
    ready_payload: dict[str, object] | None = None
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        try:
            ready = client.get(f"{api_url}/ready")
            ready.raise_for_status()
            ready_payload = ready.json()
            if ready_payload["status"] == "ready":
                return ready_payload
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise AssertionError(f"Backend did not become ready: {ready_payload}")


def _wait_for_terminal_status(
    client: httpx.Client,
    api_url: str,
    document_id: str,
) -> dict[str, object]:
    status_payload: dict[str, object] | None = None
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        status_response = client.get(f"{api_url}/documents/{document_id}/status")
        status_response.raise_for_status()
        status_payload = status_response.json()
        if status_payload["status"] in {"completed", "failed"}:
            return status_payload
        time.sleep(0.5)
    raise AssertionError(f"Document did not reach a terminal status: {status_payload}")


def _successful_content() -> bytes:
    return (
        "Invoice\nVendor: Integration Ltd\nTotal Amount: EUR 123.00\n"
        f"Integration Run: {_integration_run_id()}"
    ).encode()


def _integration_run_id() -> str:
    return os.environ.get("CELERY_INTEGRATION_RUN_ID") or uuid.uuid4().hex


def _document_id(content: bytes) -> str:
    return "doc_" + hashlib.sha256(content).hexdigest()[:16]
