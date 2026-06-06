import asyncio
from io import BytesIO

import pytest
from app.api.routes_documents import upload_document
from fastapi import HTTPException, UploadFile, status
from starlette.datastructures import Headers


def test_upload_rejects_unsupported_mime_type() -> None:
    file = UploadFile(
        BytesIO(b"not really an executable"),
        filename="invoice.txt",
        headers=Headers({"content-type": "application/x-msdownload"}),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(upload_document(file))

    assert exc.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE


def test_upload_accepts_allowed_text_mime_type() -> None:
    file = UploadFile(
        BytesIO(b"Invoice\nVendor: Safe Upload Ltd\nTotal Amount: EUR 1,200.00"),
        filename="invoice.txt",
        headers=Headers({"content-type": "text/plain"}),
    )

    document = asyncio.run(upload_document(file))

    assert document.status == "completed"
    assert document.filename == "invoice.txt"
