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
    run_id = uuid.uuid4().hex
    content = (
        f"Invoice\nVendor: Integration Ltd\nTotal Amount: EUR 123.00\nIntegration Run: {run_id}"
    ).encode()

    with httpx.Client(timeout=10.0) as client:
        ready_payload = None
        ready_deadline = time.monotonic() + 30.0
        while time.monotonic() < ready_deadline:
            ready = client.get(f"{api_url}/ready")
            ready.raise_for_status()
            ready_payload = ready.json()
            if ready_payload["status"] == "ready":
                break
            time.sleep(0.5)
        assert ready_payload is not None
        assert ready_payload["status"] == "ready"

        upload = client.post(
            f"{api_url}/documents/upload",
            files={"file": (f"integration_invoice_{run_id}.txt", content, "text/plain")},
        )
        upload.raise_for_status()
        document_id = upload.json()["document_id"]

        deadline = time.monotonic() + 30.0
        status_payload = None
        while time.monotonic() < deadline:
            status_response = client.get(f"{api_url}/documents/{document_id}/status")
            status_response.raise_for_status()
            status_payload = status_response.json()
            if status_payload["status"] in {"completed", "failed"}:
                break
            time.sleep(0.5)

        assert status_payload is not None
        assert status_payload["status"] == "completed"
        assert {branch["status"] for branch in status_payload["branches"]} == {"completed"}

        document = client.get(f"{api_url}/documents/{document_id}")
        document.raise_for_status()
        document_payload = document.json()
        assert document_payload["status"] == "completed"
        assert document_payload["extracted_fields"]["vendor"] == "Integration Ltd"
