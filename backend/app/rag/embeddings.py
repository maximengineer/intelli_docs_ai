from __future__ import annotations

import hashlib
import logging
import math
from functools import lru_cache
from typing import Protocol

from app.core.settings import get_settings
from app.core.text import WORD_RE

logger = logging.getLogger(__name__)


class EmbeddingModel(Protocol):
    name: str

    def embed(self, text: str) -> list[float]:
        """Return a single embedding vector."""

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


class HashEmbeddingModel:
    """Small deterministic embedding model for offline demos and tests.

    Lexical, not semantic: it hashes tokens into a fixed-width vector. Good
    enough to keep retrieval working with no API key, but it does not capture
    meaning. For real semantic search use a local sentence-transformers model or
    :class:`OpenRouterEmbeddingModel`.
    """

    name = "local-hash-embedding"
    version = "0.1.0"

    def embed(self, text: str) -> list[float]:
        dimension = get_settings().embedding_dimension
        vector = [0.0] * dimension
        for token in WORD_RE.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        return _l2_normalize(vector)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class SentenceTransformerEmbeddingModel:
    """Real semantic embeddings computed locally (no API key, no data leaves the box).

    Requires the optional ``local-embeddings`` install (sentence-transformers /
    torch). The model is downloaded once on first use and cached on disk.
    """

    def __init__(self, model_name: str, *, local_files_only: bool = False) -> None:
        from sentence_transformers import SentenceTransformer  # heavy, optional

        self._model = SentenceTransformer(model_name, local_files_only=local_files_only)
        self.name = f"sentence-transformers:{model_name}"

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return [vector.tolist() for vector in vectors]


class OpenRouterEmbeddingModel:
    """Semantic embeddings via OpenRouter's OpenAI-compatible endpoint."""

    name = "openrouter-embedding"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float,
        max_retries: int,
    ) -> None:
        from openai import OpenAI  # lazy import keeps offline installs slim

        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._model = model

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(model=self._model, input=texts)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [_l2_normalize(list(item.embedding)) for item in ordered]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Cosine similarity between two vectors (safe for unnormalised input)."""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


@lru_cache
def get_embedding_model() -> EmbeddingModel:
    settings = get_settings()
    backend = settings.resolve_embedding_backend()

    if backend == "local":
        try:
            model = SentenceTransformerEmbeddingModel(settings.local_embedding_model)
            logger.info(
                "embedding_model_ready backend=local model=%s", settings.local_embedding_model
            )
            return model
        except Exception:  # pragma: no cover - missing optional dep / download issue
            logger.warning(
                "local_embedding_init_failed; falling back to hash embeddings", exc_info=True
            )
            return HashEmbeddingModel()

    if backend == "openrouter":
        try:
            model = OpenRouterEmbeddingModel(
                api_key=settings.openrouter_api_key or "",
                base_url=settings.openrouter_base_url,
                model=settings.embedding_model,
                timeout=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
            )
            logger.info(
                "embedding_model_ready backend=openrouter model=%s", settings.embedding_model
            )
            return model
        except Exception:  # pragma: no cover - misconfiguration / missing SDK
            logger.warning(
                "openrouter_embedding_init_failed; falling back to hash embeddings", exc_info=True
            )

    return HashEmbeddingModel()
