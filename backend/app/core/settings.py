from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "IntelliDocs AI"
    max_upload_mb: int = Field(default=10, ge=1, le=100)
    allowed_extensions: set[str] = {".txt", ".docx", ".pdf"}
    allowed_mime_types: set[str] = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    }
    parser_timeout_seconds: float = Field(default=10.0, gt=0)
    cors_origins: list[str] = [
        "http://localhost:9999",
        "http://127.0.0.1:9999",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ]
    chunk_size_tokens: int = 800
    chunk_overlap_tokens: int = 100
    embedding_dimension: int = 256
    retrieval_top_k: int = 5
    min_relevance_score: float = 0.08
    retrieval_candidate_k: int = Field(default=30, ge=1)
    reranker_enabled: bool = True

    # --- Phase 2 storage/readiness -----------------------------------------
    database_url: str | None = None
    require_database_ready: bool = False
    vector_store_backend: Literal["memory", "postgres"] = "memory"
    postgres_vector_dimension: int = 1536
    postgres_vector_distance_metric: str = "cosine"
    postgres_vector_operator_class: str = "vector_cosine_ops"
    postgres_vector_index_type: str = "hnsw"
    database_pool_min_size: int = Field(default=1, ge=0)
    database_pool_max_size: int = Field(default=5, ge=1)
    database_pool_timeout_seconds: float = Field(default=5.0, gt=0)

    # --- Phase 3 hardening ---------------------------------------------------
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    document_processing_backend: Literal["thread", "celery"] = "thread"
    upload_storage_dir: str = "data/uploads"
    support_check_enabled: bool = True
    support_check_min_citation_count: int = Field(default=1, ge=0)
    # Minimum number of shared content tokens between the answer and its cited
    # chunk text. This is the signal that lets the gate actually reject an answer
    # that cites context it did not use (0 = grounding check disabled).
    support_check_min_overlap: int = Field(default=1, ge=0)
    streaming_enabled: bool = True
    celery_task_soft_time_limit_seconds: int = Field(default=50, ge=1)
    celery_task_time_limit_seconds: int = Field(default=60, ge=1)

    # --- Phase 2 cost estimation ------------------------------------------
    price_table_as_of: str = "2026-06-06"
    llm_input_price_per_1m_tokens: float = 0.0
    llm_output_price_per_1m_tokens: float = 0.0

    # --- LLM provider (OpenRouter, OpenAI-compatible) -----------------------
    # Generation/summarisation/extraction use the model only when enable_llm is
    # true AND an API key is present. Otherwise the deterministic offline
    # fallbacks run, so tests, CI and key-less demos always work.
    enable_llm: bool = False
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "openai/gpt-4o-mini"
    llm_temperature: float = 0.0
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)
    llm_max_input_chars: int = 12_000
    # Sent to OpenRouter for attribution; harmless if left at defaults.
    llm_referer: str = "http://localhost:9999"
    llm_title: str = "IntelliDocs AI"

    # --- Embeddings ---------------------------------------------------------
    # "auto"       -> OpenRouter embeddings when a key is present, else hash.
    # "local"      -> sentence-transformers (real semantic search, offline, free;
    #                 needs the optional 'local-embeddings' install).
    # "openrouter" -> OpenRouter embeddings API.
    # "hash"       -> zero-dependency lexical fallback.
    embedding_backend: Literal["auto", "local", "openrouter", "hash"] = "auto"
    embedding_model: str = "openai/text-embedding-3-small"
    local_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def llm_enabled(self) -> bool:
        return self.enable_llm and bool(self.openrouter_api_key)

    @property
    def durable_document_state_enabled(self) -> bool:
        return self.vector_store_backend == "postgres"

    def resolve_embedding_backend(self) -> Literal["local", "openrouter", "hash"]:
        if self.embedding_backend != "auto":
            return self.embedding_backend
        # "auto" never silently pulls in torch; local is an explicit opt-in.
        return "openrouter" if self.openrouter_api_key else "hash"


@lru_cache
def get_settings() -> Settings:
    return Settings()
