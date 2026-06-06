import os

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
        with st.spinner("Processing document"):
            response = requests.post(
                f"{API_URL}/documents/upload",
                files={"file": (uploaded_file.name, uploaded_file.getvalue())},
                timeout=60,
            )
        if response.ok:
            document = response.json()
            st.session_state["document"] = document
            st.success(f"Processed {document['filename']}")
        else:
            st.error(response.json().get("detail", response.text))

document = st.session_state.get("document")
if document:
    st.subheader(document["filename"])
    metric_cols = st.columns(3)
    metric_cols[0].metric("Status", document["status"])
    metric_cols[1].metric("Type", document["document_type"])
    metric_cols[2].metric("Chunks", document["chunk_count"])

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
    else:
        st.error(response.text)
