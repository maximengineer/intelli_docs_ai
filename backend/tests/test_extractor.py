from app.documents.extractor import extract_fields


def test_invoice_extraction_schema_and_values() -> None:
    fields = extract_fields(
        "Invoice\nVendor: Acme Analytics Ltd\nInvoice Date: 2026-01-15\nTotal Amount: EUR 12,450.00"
    )

    assert fields.document_type == "invoice"
    assert fields.vendor == "Acme Analytics Ltd"
    assert fields.amount == 12450.0
    assert fields.currency == "EUR"


def test_contract_extraction_schema_and_values() -> None:
    fields = extract_fields(
        "\n".join(
            [
                "Service Agreement",
                "Party: Northwind Retail Group",
                "Effective Date: 2026-02-01",
                "Renewal Terms: Auto-renewal for one-year terms.",
                "This agreement includes termination for cause.",
            ]
        )
    )

    assert fields.document_type == "contract"
    assert fields.party_name == "Northwind Retail Group"
    assert fields.effective_date == "2026-02-01"
    assert fields.renewal_terms == "Auto-renewal for one-year terms."
    assert fields.risk_level == "high"


def test_invoice_extraction_normalises_currency_symbols() -> None:
    fields = extract_fields("Invoice\nVendor: Example Ltd\nTotal Amount: £1,200.50")

    assert fields.amount == 1200.5
    assert fields.currency == "GBP"


def test_invoice_extraction_accepts_currency_suffix() -> None:
    fields = extract_fields("Invoice\nVendor: Suffix Ltd\nTotal Amount: 1,200.50 GBP")

    assert fields.amount == 1200.5
    assert fields.currency == "GBP"
