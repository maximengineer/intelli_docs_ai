from app.documents.extractor import extract_fields


def test_invoice_extraction_schema_and_values() -> None:
    fields = extract_fields(
        "Invoice\nVendor: Acme Analytics Ltd\nInvoice Date: 2026-01-15\nTotal Amount: EUR 12,450.00"
    )

    assert fields.document_type == "invoice"
    assert fields.vendor == "Acme Analytics Ltd"
    assert fields.amount == 12450.0
    assert fields.currency == "EUR"
