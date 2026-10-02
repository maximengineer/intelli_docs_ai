"""Headless Streamlit smoke test (no browser, no backend).

Skipped where the `frontend` dependency group is not installed, e.g. the Docker
`tests` image, which carries only backend dependencies.
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = Path(__file__).resolve().parents[2] / "frontend" / "streamlit_app.py"


class _CompletedDocument:
    ok = True
    status_code = 200

    def json(self) -> dict:
        return {
            "document_id": "doc_ui",
            "filename": "invoice.txt",
            "status": "completed",
            "document_type": "invoice",
            "chunk_count": 1,
            "extraction_confidence": 0.92,
            "needs_review": False,
            "summary": "- An invoice.",
            "extracted_fields": {"vendor": "Acme Analytics Ltd"},
        }


def test_workspace_renders_document_and_sample_questions_fill_the_input(monkeypatch) -> None:
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: _CompletedDocument())
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["workspace_documents"] = [
        {"document_id": "doc_ui", "filename": "invoice.txt", "status": "completed"}
    ]

    app.run()

    assert not app.exception
    labels = {metric.label: metric.value for metric in app.metric}
    assert labels["Field completeness"] == "0.92"
    app.button(key="sample_3").click().run()
    assert app.text_input(key="question").value == "Which document mentions a Singapore office?"


class _RefusalStream:
    ok = True

    def __enter__(self) -> "_RefusalStream":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def iter_lines(self, decode_unicode: bool = False):
        response = {
            "run_id": "run_ui",
            "answer": "The available documents do not contain enough information.",
            "status": "insufficient_information",
            "sources": [],
            "metrics": {
                "latency_ms": 3,
                "candidates_retrieved": 1,
                "context_chunks_used": 1,
                "citation_count": 0,
                "model_name": None,
            },
        }
        yield json.dumps({"event": "final", "run_id": "run_ui", "response": response})


def test_refusal_before_any_answerer_shows_no_model(monkeypatch) -> None:
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: _CompletedDocument())
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: _RefusalStream())
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["workspace_documents"] = [
        {"document_id": "doc_ui", "filename": "invoice.txt", "status": "completed"}
    ]
    app.run()

    app.text_input(key="question").input("Which document mentions a Singapore office?")
    app.button(key="FormSubmitter:qa_form-Ask").click().run()

    assert not app.exception
    captions = [caption.value for caption in app.caption]
    metrics_caption = next(value for value in captions if value.startswith("latency:"))
    assert "citations: 0" in metrics_caption
    assert "model" not in metrics_caption
