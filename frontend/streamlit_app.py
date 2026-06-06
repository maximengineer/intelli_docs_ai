import os
import time

import requests
import streamlit as st

API_URL = os.getenv("INTELLIDOCS_API_URL", "http://localhost:8000")

st.set_page_config(page_title="IntelliDocs AI", page_icon="ID", layout="wide")
st.title("IntelliDocs AI")

with st.sidebar:
    st.header("Document Upload")
    uploaded_file = st.file_uploader(
        "Upload TXT, DOCX or digital-native PDF", type=["txt", "docx", "pdf"]
    )
    if uploaded_file and st.button("Process document", type="primary"):
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
            st.error(response.json().get("detail", response.text))

upload = st.session_state.get("document_upload")
if upload and "document" not in st.session_state:
    with st.spinner("Processing document"):
        for _ in range(30):
            status_response = requests.get(
                f"{API_URL}/documents/{upload['document_id']}/status",
                timeout=10,
            )
            if not status_response.ok:
                st.error(status_response.text)
                break
            current_status = status_response.json()
            if current_status["status"] == "completed":
                document_response = requests.get(
                    f"{API_URL}/documents/{upload['document_id']}",
                    timeout=10,
                )
                if document_response.ok:
                    st.session_state["document"] = document_response.json()
                else:
                    st.error(document_response.text)
                break
            if current_status["status"] == "failed":
                st.error(current_status.get("error") or "Document processing failed")
                break
            time.sleep(0.5)

document = st.session_state.get("document")
if document:
    st.subheader(document["filename"])
    metric_cols = st.columns(3)
    metric_cols[0].metric("Status", document["status"])
    metric_cols[1].metric("Type", document["document_type"])
    metric_cols[2].metric("Chunks", document["chunk_count"])
    if document.get("needs_review"):
        st.warning("Extraction completed with review recommended.")

    left, right = st.columns([1, 1])
    with left:
        st.markdown("### Summary")
        st.markdown(document["summary"])
    with right:
        st.markdown("### Extracted Fields")
        st.json(document["extracted_fields"])

st.divider()
st.subheader("Ask A Source-Grounded Question")
question = st.text_input("Question", placeholder="Which invoices are above 10,000 EUR?")
if st.button("Ask", disabled=not question):
    with st.spinner("Retrieving evidence and generating answer"):
        response = requests.post(f"{API_URL}/qa", json={"question": question}, timeout=60)
    if response.ok:
        result = response.json()
        if result["status"] == "insufficient_information":
            st.warning(result["answer"])
        elif result["status"] == "failed":
            st.error(result.get("error") or "Q&A failed")
        else:
            st.write(result["answer"])
            st.markdown("### Sources")
            for source in result["sources"]:
                page = source.get("page_number") or "n/a"
                st.caption(f"{source['filename']} | page {page} | {source['chunk_id']}")
                st.write(source["snippet"])
        st.caption(f"run_id: {result['run_id']}")
        if result.get("metrics"):
            st.caption(
                " | ".join(
                    [
                        f"latency: {result['metrics']['latency_ms']} ms",
                        f"context: {result['metrics']['context_chunks_used']}",
                        f"citations: {result['metrics']['citation_count']}",
                    ]
                )
            )
    else:
        st.error(response.text)
