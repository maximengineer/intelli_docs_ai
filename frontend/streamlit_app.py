import hashlib
import json
import os
import time

import requests
import streamlit as st
from requests import RequestException

API_URL = os.getenv("INTELLIDOCS_API_URL", "http://localhost:8000")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
MAX_DOCUMENTS = int(os.getenv("MAX_DOCUMENTS", "10"))
TERMINAL_DOCUMENT_STATUSES = {"completed", "failed"}
WORKSPACE_DOCUMENTS_KEY = "workspace_documents"

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


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status.replace("_", " ").title())


def workspace_documents() -> list[dict]:
    return st.session_state.setdefault(WORKSPACE_DOCUMENTS_KEY, [])


def upsert_workspace_document(document: dict) -> None:
    documents = workspace_documents()
    for index, current in enumerate(documents):
        if current["document_id"] == document["document_id"]:
            documents[index] = {**current, **document}
            break
    else:
        documents.append(document)
    st.session_state[WORKSPACE_DOCUMENTS_KEY] = documents


def selected_document_id() -> str | None:
    documents = workspace_documents()
    selected = st.session_state.get("selected_document_id")
    if selected and any(document["document_id"] == selected for document in documents):
        return selected
    if not documents:
        return None
    selected = documents[-1]["document_id"]
    st.session_state["selected_document_id"] = selected
    return selected


def upload_document_id(content: bytes) -> str:
    return "doc_" + hashlib.sha256(content).hexdigest()[:16]


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
st.markdown(
    """
    <style>
    [data-testid="stMainBlockContainer"] {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] {
        display: none !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        background: transparent !important;
        border: none !important;
        border-radius: 0 !important;
        padding: 0 !important;
        min-height: 0 !important;
        gap: 0 !important;
        justify-content: center !important;
        align-items: center !important;
    }
    [data-testid="stFileUploaderDropzone"] > span {
        width: 100% !important;
        display: block !important;
    }
    [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] {
        background-color: #ff4b4b !important;
        border-color: #ff4b4b !important;
        color: #ffffff !important;
        width: 100% !important;
    }
    [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"]:hover {
        background-color: #ff6b6b !important;
        border-color: #ff6b6b !important;
        color: #ffffff !important;
    }
    /* Tighten bordered document cards in the sidebar */
    [data-testid="stSidebarUserContent"]
      .st-emotion-cache-1ne20ew {
        gap: 0.25rem !important;
        padding: 0.5rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("IntelliDocs AI")
st.caption("Upload documents, extract facts, ask source-grounded questions, and verify citations.")

with st.sidebar:
    st.header("Document Upload")
    documents = workspace_documents()
    remaining_slots = MAX_DOCUMENTS - len(documents)
    uploader_version = st.session_state.setdefault("document_uploader_version", 0)
    uploaded_files = st.file_uploader(
        "Choose documents (TXT, DOCX, PDF)",
        type=["txt", "docx", "pdf"],
        accept_multiple_files=True,
        max_upload_size=MAX_UPLOAD_MB,
        disabled=remaining_slots == 0,
        key=f"document_uploader_{uploader_version}",
    )
    st.caption(f"Up to {MAX_DOCUMENTS} documents. Maximum file size: {MAX_UPLOAD_MB} MB each.")
    if st.button(
        "Process documents",
        type="primary",
        icon=":material/upload:",
        disabled=not uploaded_files or remaining_slots == 0,
        width="stretch",
    ):
        selected_files = uploaded_files or []
        existing_ids = {document["document_id"] for document in documents}
        selected_ids = {upload_document_id(file.getvalue()) for file in selected_files}
        if len(existing_ids | selected_ids) > MAX_DOCUMENTS:
            st.error(
                f"You can keep up to {MAX_DOCUMENTS} documents. Remove a document or "
                "select fewer files."
            )
        else:
            accepted: list[dict] = []
            errors: list[str] = []
            with st.spinner("Uploading documents"):
                for uploaded_file in selected_files:
                    try:
                        response = requests.post(
                            f"{API_URL}/documents/upload",
                            files={"file": (uploaded_file.name, uploaded_file.getvalue())},
                            timeout=60,
                        )
                        if response.ok:
                            upload = response.json()
                            upsert_workspace_document(upload)
                            accepted.append(upload)
                        else:
                            try:
                                detail = response.json().get("detail", response.text)
                            except ValueError:
                                detail = response.text
                            errors.append(f"{uploaded_file.name}: {detail}")
                    except RequestException as exc:
                        errors.append(f"{uploaded_file.name}: {exc}")
            if accepted:
                st.session_state["selected_document_id"] = accepted[-1]["document_id"]
                st.session_state["document_uploader_version"] = uploader_version + 1
                count = len(accepted)
                st.session_state["workspace_notice"] = (
                    f"Added {count} document{'s' if count != 1 else ''}."
                )
            if errors:
                st.session_state["workspace_errors"] = errors
            if accepted:
                st.rerun()

    notice = st.session_state.pop("workspace_notice", None)
    if notice:
        st.success(notice)
    for error in st.session_state.pop("workspace_errors", []):
        st.error(error)

    documents = workspace_documents()
    if documents:
        st.markdown(f"#### Documents ({len(documents)}/{MAX_DOCUMENTS})")
    current_selection = selected_document_id()
    for workspace_document in list(documents):
        document_id = workspace_document["document_id"]
        document_status = workspace_document.get("status", "queued")
        with st.container(border=True):
            if st.button(
                workspace_document["filename"],
                key=f"select_{document_id}",
                icon=":material/description:",
                type="primary" if document_id == current_selection else "tertiary",
                width="stretch",
            ):
                st.session_state["selected_document_id"] = document_id
                st.rerun()
            doc_info_cols = st.columns([1, 1], gap="small", vertical_alignment="center")
            doc_info_cols[0].caption(status_label(document_status))
            if doc_info_cols[1].button(
                "Remove",
                key=f"remove_{document_id}",
                icon=":material/close:",
                type="tertiary",
                disabled=document_status not in TERMINAL_DOCUMENT_STATUSES,
                help=(
                    "Remove this document from storage and question context."
                    if document_status in TERMINAL_DOCUMENT_STATUSES
                    else "Wait for processing to finish before removing this document."
                ),
            ):
                try:
                    response = requests.delete(
                        f"{API_URL}/documents/{document_id}",
                        timeout=30,
                    )
                    if response.status_code == 204:
                        remaining_documents = [
                            document
                            for document in workspace_documents()
                            if document["document_id"] != document_id
                        ]
                        st.session_state[WORKSPACE_DOCUMENTS_KEY] = remaining_documents
                        if st.session_state.get("selected_document_id") == document_id:
                            st.session_state["selected_document_id"] = (
                                remaining_documents[-1]["document_id"]
                                if remaining_documents
                                else None
                            )
                        st.session_state["workspace_notice"] = (
                            f"Removed {workspace_document['filename']}."
                        )
                        st.rerun()
                    else:
                        show_response_error(response)
                except RequestException as exc:
                    st.error(f"Could not remove {workspace_document['filename']}: {exc}")

documents = workspace_documents()
pending_documents = [
    document
    for document in documents
    if document.get("status", "queued") not in TERMINAL_DOCUMENT_STATUSES
]
if pending_documents:
    count = len(pending_documents)
    with st.status(
        f"Processing {count} document{'s' if count != 1 else ''}",
        expanded=True,
    ) as processing_status:
        status_placeholder = st.empty()
        try:
            for _ in range(240):
                refreshed_documents: list[dict] = []
                for workspace_document in workspace_documents():
                    status_response = requests.get(
                        f"{API_URL}/documents/{workspace_document['document_id']}/status",
                        timeout=10,
                    )
                    if status_response.status_code == 404:
                        continue
                    if not status_response.ok:
                        raise RequestException(
                            f"Status request failed for {workspace_document['filename']}: "
                            f"HTTP {status_response.status_code}"
                        )
                    refreshed_documents.append({**workspace_document, **status_response.json()})
                st.session_state[WORKSPACE_DOCUMENTS_KEY] = refreshed_documents
                status_placeholder.markdown(
                    "\n".join(
                        f"- **{document['filename']}**: {status_label(document['status'])}"
                        for document in refreshed_documents
                    )
                )
                if all(
                    document["status"] in TERMINAL_DOCUMENT_STATUSES
                    for document in refreshed_documents
                ):
                    processing_status.update(label="Documents ready", state="complete")
                    st.rerun()
                time.sleep(0.5)
            else:
                st.info("Documents are still processing. Leave this page open to continue polling.")
        except RequestException as exc:
            st.error(f"Could not reach IntelliDocs AI backend at {API_URL}: {exc}")
            processing_status.update(label="Backend unavailable", state="error")

document = None
current_selection = selected_document_id()
selected_record = next(
    (
        workspace_document
        for workspace_document in workspace_documents()
        if workspace_document["document_id"] == current_selection
    ),
    None,
)
if selected_record and selected_record.get("status") == "completed":
    try:
        document_response = requests.get(
            f"{API_URL}/documents/{selected_record['document_id']}",
            timeout=10,
        )
        if document_response.ok:
            document = document_response.json()
        else:
            show_response_error(document_response)
    except RequestException as exc:
        st.error(f"Could not load {selected_record['filename']}: {exc}")
elif selected_record and selected_record.get("status") == "failed":
    st.error(
        selected_record.get("error") or f"Processing failed for {selected_record['filename']}."
    )

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
st.subheader("Ask About Your Documents")
st.caption(
    "Ask a question about the documents you uploaded. IntelliDocs AI will answer "
    "using information found in those documents."
)
active_document_ids = [
    document["document_id"]
    for document in workspace_documents()
    if document.get("status") == "completed"
]
if not active_document_ids:
    st.info("Upload and process at least one document before asking a question.")
with st.form("qa_form", clear_on_submit=False):
    input_col, btn_col = st.columns([6, 1], vertical_alignment="bottom")
    question = input_col.text_input(
        "Question",
        key="question",
        placeholder="What would you like to know about your documents?",
        label_visibility="collapsed",
    )
    ask_submitted = btn_col.form_submit_button(
        "Ask",
        type="primary",
        icon=":material/send:",
        disabled=not active_document_ids,
    )
if ask_submitted and question.strip() and active_document_ids:
    result = None
    try:
        status_box = st.empty()
        with requests.post(
            f"{API_URL}/qa/stream",
            json={"question": question, "document_ids": active_document_ids},
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
