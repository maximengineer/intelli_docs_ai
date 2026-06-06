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
    metrics: "QAMetrics | None" = None
    error: str | None = None


class RetrievedChunk(BaseModel):
    document_id: str
    filename: str
    page_number: int | None = None
    section_title: str | None = None
    chunk_id: str
    text: str
    score: float
    rerank_score: float | None = None


class QAMetrics(BaseModel):
    latency_ms: int
    candidates_retrieved: int
    context_chunks_used: int
    citation_count: int
    model_name: str
    # Real provider token counts when the LLM is used; a word-count approximation
    # otherwise (model_name == "offline-heuristic" signals the approximate case).
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    price_table_as_of: str
    reranker_enabled: bool
