from typing import Literal

from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    document_id: str
    filename: str
    page_number: int | None = None
    section_title: str | None = None
    chunk_id: str
    snippet: str


class QARequest(BaseModel):
    question: str = Field(min_length=3)
    document_ids: list[str] | None = None


class QAResponse(BaseModel):
    run_id: str
    answer: str
    status: Literal["success", "insufficient_information", "failed"]
    sources: list[SourceCitation]
    error: str | None = None


class RetrievedChunk(BaseModel):
    document_id: str
    filename: str
    page_number: int | None = None
    section_title: str | None = None
    chunk_id: str
    text: str
    score: float
