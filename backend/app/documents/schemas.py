from typing import Literal

from pydantic import BaseModel, Field


class ParsedPage(BaseModel):
    page_number: int | None = None
    text: str
    section_title: str | None = None


class ParsedDocument(BaseModel):
    document_id: str
    filename: str
    text: str
    pages: list[ParsedPage]
    metadata: dict[str, str] = Field(default_factory=dict)


class ExtractedFields(BaseModel):
    document_type: Literal["invoice", "contract", "policy", "report", "unknown"] = "unknown"
    vendor: str | None = None
    amount: float | None = None
    currency: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    party_name: str | None = None
    effective_date: str | None = None
    renewal_terms: str | None = None
    risk_level: Literal["low", "medium", "high", "unknown"] = "unknown"


class DocumentChunk(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    text: str
    page_number: int | None = None
    section_title: str | None = None
    chunk_index: int


class DocumentResponse(BaseModel):
    document_id: str
    filename: str
    status: Literal["uploaded", "processing", "completed", "failed"]
    summary: str
    document_type: str
    extracted_fields: ExtractedFields
    chunk_count: int
    error: str | None = None
