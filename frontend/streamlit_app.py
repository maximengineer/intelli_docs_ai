import json
import os
import time

import requests
import streamlit as st
from requests import RequestException

API_URL = os.getenv("INTELLIDOCS_API_URL", "http://localhost:8000")

SAMPLE_QUESTIONS = [
    {
        "question": "Which invoice is above 10,000 EUR?",
        "scope": "Upload invoice_acme.txt",
    },
    {
        "question": "What are the renewal terms in the Northwind service agreement?",
        "scope": "Upload contract_northwind.txt",
    },
    {
        "question": "Which document mentions a Singapore office?",
        "scope": "Unsupported check",
    },
]

STATUS_LABELS = {
    "uploaded": "Uploaded",
    "queued": "Queued",
    "parsing": "Parsing",
    "privacy_processing": "Preparing privacy-safe text",
    "chunking": "Chunking",
    "processing": "Running AI branches",
    "completed": "Completed",
    "failed": "Failed",
    "accepted_for_verification": "Accepted for verified Q&A",
    "building_verified_answer": "Building final verified answer",
    "success": "Answer verified",
    "insufficient_information": "Insufficient information",
}

STEP_LABELS = {
    "parsing": "Parse document",
    "privacy_processing": "Prepare privacy variants",
    "chunking": "Create chunks",
    "embedding": "Embed chunks",
    "extracting": "Extract key fields",
    "summarising": "Generate summary",
}


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status.replace("_", " ").title())


def step_line(name: str, status: str, error: str | None = None) -> str:
    state = status.replace("_", " ")
    label = STEP_LABELS.get(name, name.replace("_", " ").title())
    suffix = f" - {error}" if error else ""
    return f"- {label}: {state}{suffix}"


def progress_value(steps: list[dict], branches: list[dict], status: str) -> float:
    if status == "completed":
        return 1.0
    units = steps + branches
    if not units:
        return 0.05
    completed = sum(1 for unit in units if unit.get("status") == "completed")
    running = sum(1 for unit in units if unit.get("status") == "running")
    return min(0.95, max(0.05, (completed + (running * 0.5)) / len(units)))


def render_processing_status(payload: dict) -> None:
    st.caption(f"Document ID: `{payload['document_id']}`")
    steps = payload.get("steps", [])
    branches = payload.get("branches", [])
    st.progress(progress_value(steps, branches, payload["status"]))
    st.markdown(f"**Current status:** {status_label(payload['status'])}")
    if steps:
        st.markdown("**Sequential steps**")
        st.markdown(
            "\n".join(
                step_line(step["name"], step["status"], step.get("error")) for step in steps
            )
        )
    if branches:
        st.markdown("**Parallel AI branches**")
        st.markdown(
            "\n".join(
                step_line(branch["name"], branch["status"], branch.get("error"))
                for branch in branches
            )
        )


def render_extracted_fields(fields: dict) -> None:
    rows = [
        {"Field": key.replace("_", " ").title(), "Value": value}
        for key, value in fields.items()
        if value not in (None, "", "unknown")
    ]
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info("No high-confidence fields were extracted.")


def render_source(source: dict, index: int) -> None:
    page = source.get("page_number") or "n/a"
    section = source.get("section_title") or "n/a"
    with st.expander(f"Source {index}: {source['filename']}"):
        st.caption(f"page: {page} | section: {section} | chunk: {source['chunk_id']}")
        st.write(source["snippet"])


def show_response_error(response: requests.Response) -> None:
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    st.error(detail)


st.set_page_config(page_title="IntelliDocs AI", page_icon="ID", layout="wide")
st.title("IntelliDocs AI")
st.caption("Upload documents, extract facts, ask source-grounded questions, and verify citations.")

with st.sidebar:
    st.header("Document Upload")
    st.caption("Synthetic TXT, DOCX and digital-native PDF files are supported.")
    uploaded_file = st.file_uploader(
        "Upload TXT, DOCX or digital-native PDF", type=["txt", "docx", "pdf"]
    )
    if uploaded_file and st.button("Process document", type="primary"):
        try:
            with st.spinner("Uploading document"):
                response = requests.post(
                    f"{API_URL}/documents/upload",
                    files={"file": (uploaded_file.name, uploaded_file.getvalue())},
                    timeout=60,
                )
            if response.ok:
                upload = response.json()
                st.session_state["document_upload"] = upload
                st.session_state.pop("document", None)
                st.success(f"Queued {upload['filename']}")
            else:
                show_response_error(response)
        except RequestException as exc:
            st.error(f"Could not reach IntelliDocs AI backend at {API_URL}: {exc}")

upload = st.session_state.get("document_upload")
if upload and "document" not in st.session_state:
    with st.status("Processing document", expanded=True) as processing_status:
        status_placeholder = st.empty()
        try:
            for _ in range(240):
                status_response = requests.get(
                    f"{API_URL}/documents/{upload['document_id']}/status",
                    timeout=10,
                )
                if not status_response.ok:
                    show_response_error(status_response)
                    processing_status.update(label="Document status unavailable", state="error")
                    break
                current_status = status_response.json()
                with status_placeholder.container():
                    render_processing_status(current_status)
                if current_status["status"] == "completed":
                    document_response = requests.get(
                        f"{API_URL}/documents/{upload['document_id']}",
                        timeout=10,
                    )
                    if document_response.ok:
                        st.session_state["document"] = document_response.json()
                        processing_status.update(label="Document ready", state="complete")
                    else:
                        show_response_error(document_response)
                        processing_status.update(label="Document fetch failed", state="error")
                    break
                if current_status["status"] == "failed":
                    st.error(current_status.get("error") or "Document processing failed")
                    processing_status.update(label="Document processing failed", state="error")
                    break
                time.sleep(0.5)
            else:
                st.info(
                    "Document is still processing. Leave this page open or press Process document "
                    "again later to refresh the status."
                )
        except RequestException as exc:
            st.error(f"Could not reach IntelliDocs AI backend at {API_URL}: {exc}")
            processing_status.update(label="Backend unavailable", state="error")

document = st.session_state.get("document")
if document:
    st.subheader(document["filename"])
    metric_cols = st.columns(4)
    metric_cols[0].metric("Status", document["status"])
    metric_cols[1].metric("Type", document["document_type"])
    metric_cols[2].metric("Chunks", document["chunk_count"])
    confidence = document.get("extraction_confidence")
    metric_cols[3].metric(
        "Extraction confidence",
        "n/a" if confidence is None else f"{confidence:.2f}",
    )
    if document.get("needs_review"):
        st.warning("Extraction completed with review recommended.")

    left, right = st.columns([1, 1])
    with left:
        st.markdown("### Summary")
        st.markdown(document["summary"])
    with right:
        st.markdown("### Extracted Fields")
        render_extracted_fields(document["extracted_fields"])

st.divider()
st.subheader("Ask A Source-Grounded Question")
st.caption("These sample questions match the demo walkthrough uploads.")
sample_cols = st.columns(3)
for index, sample in enumerate(SAMPLE_QUESTIONS):
    with sample_cols[index % 3]:
        if st.button(sample["question"], key=f"sample_question_{index}"):
            st.session_state["question"] = sample["question"]
        st.caption(sample["scope"])

question = st.text_input(
    "Question",
    key="question",
    placeholder="Which invoices are above 10,000 EUR?",
)
use_streaming = st.toggle("Use verified streaming", value=True)
if st.button("Ask", disabled=not question):
    result = None
    try:
        if use_streaming:
            status_box = st.empty()
            with requests.post(
                f"{API_URL}/qa/stream",
                json={"question": question},
                stream=True,
                timeout=60,
            ) as response:
                if response.ok:
                    for line in response.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        event = json.loads(line)
                        if event["event"] == "status":
                            status_box.info(status_label(event["message"]))
                        elif event["event"] == "final":
                            result = event["response"]
                    status_box.empty()
                else:
                    show_response_error(response)
        else:
            with st.spinner("Retrieving evidence and generating answer"):
                response = requests.post(f"{API_URL}/qa", json={"question": question}, timeout=60)
            result = response.json() if response.ok else None
            if not response.ok:
                show_response_error(response)
    except RequestException as exc:
        st.error(f"Could not reach IntelliDocs AI backend at {API_URL}: {exc}")

    if result:
        if result["status"] == "insufficient_information":
            st.warning(result["answer"])
            st.caption(
                "No sources are shown because retrieved context was not accepted as evidence."
            )
        elif result["status"] == "failed":
            st.error(result.get("error") or "Q&A failed")
        else:
            st.write(result["answer"])
            st.markdown("### Sources")
            for source_index, source in enumerate(result["sources"], start=1):
                render_source(source, source_index)
        st.caption(f"run_id: {result['run_id']}")
        if result.get("metrics"):
            metrics = result["metrics"]
            st.caption(
                " | ".join(
                    [
                        f"latency: {metrics['latency_ms']} ms",
                        f"retrieved: {metrics['candidates_retrieved']}",
                        f"context: {metrics['context_chunks_used']}",
                        f"citations: {metrics['citation_count']}",
                        f"model: {metrics['model_name']}",
                    ]
                )
            )
