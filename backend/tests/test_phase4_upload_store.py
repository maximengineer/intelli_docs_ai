from app.documents.service import DocumentService
from app.rag.schemas import RetrievedChunk
from app.storage.upload_store import LocalUploadStore


class NoopVectorStore:
    def __init__(self) -> None:
        self.embedding_model = None

    def index(self, chunks) -> None:
        return None

    def remove(self, document_id: str) -> None:
        return None

    def search(
        self,
        query: str,
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        return []


def test_upload_store_uses_content_hash_key_and_dedupes(tmp_path) -> None:
    store = LocalUploadStore(root=tmp_path)
    content = b"Invoice\nVendor: Durable Ltd"

    first = store.put(filename="invoice.txt", content=content)
    second = store.put(filename="../renamed.txt", content=content)

    assert first.content_hash == second.content_hash
    assert first.storage_key == second.storage_key
    assert first.path == second.path
    assert store.get(first.storage_key) == content


def test_upload_store_rejects_unsafe_storage_keys(tmp_path) -> None:
    store = LocalUploadStore(root=tmp_path)

    try:
        store.get("../secret.txt")
    except ValueError as exc:
        assert "Invalid upload storage key" in str(exc)
    else:
        raise AssertionError("Unsafe storage key was accepted.")


def test_completed_document_upload_cleans_stored_blob(tmp_path) -> None:
    service = DocumentService(
        vector_store=NoopVectorStore(),
        upload_store=LocalUploadStore(root=tmp_path),
    )

    service.upload(
        filename="invoice.txt",
        content=b"Invoice\nVendor: Cleanup Ltd\nTotal Amount: EUR 99.00",
    )

    assert list(tmp_path.iterdir()) == []


def test_async_duplicate_upload_does_not_recreate_completed_blob(tmp_path) -> None:
    service = DocumentService(
        vector_store=NoopVectorStore(),
        upload_store=LocalUploadStore(root=tmp_path),
    )
    content = b"Invoice\nVendor: Async Dedup Ltd\nTotal Amount: EUR 99.00"

    completed = service.upload(filename="invoice.txt", content=content)
    duplicate = service.submit_upload(filename="invoice.txt", content=content)

    assert duplicate.document_id == completed.document_id
    assert duplicate.status == "completed"
    assert list(tmp_path.iterdir()) == []
