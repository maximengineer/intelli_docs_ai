from __future__ import annotations

import logging
import threading
from functools import lru_cache
from typing import Protocol

from app.core.settings import get_settings
from app.observability.costs import TokenUsage

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    model_name: str

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        """Return a text completion from an LLM provider."""

    def pop_usage(self) -> TokenUsage | None:
        """Return and clear token usage recorded for the current thread, if any."""


class OpenAICompatibleLLMClient:
    """Client for any OpenAI-compatible chat endpoint (OpenRouter, Ollama, ...).

    Timeouts and bounded retries are delegated to the OpenAI SDK. The provider's
    real token usage from the most recent call is recorded per-thread so callers
    can report actual (not estimated) cost. ``model_name`` is the model this
    client calls, so metrics label answers with what actually produced them.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float,
        max_retries: int,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        from openai import OpenAI  # lazy import keeps offline installs slim

        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.model_name = model
        self._extra_headers = extra_headers or {}
        self._local = threading.local()

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, object] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
        }
        if self._extra_headers:
            kwargs["extra_headers"] = self._extra_headers
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(**kwargs)
        self._record_usage(getattr(response, "usage", None))
        return (response.choices[0].message.content or "").strip()

    def _record_usage(self, usage: object | None) -> None:
        if usage is None:
            return
        self._local.usage = TokenUsage(
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        )

    def pop_usage(self) -> TokenUsage | None:
        usage = getattr(self._local, "usage", None)
        self._local.usage = None
        return usage


@lru_cache
def get_llm_client() -> LLMClient | None:
    """Return a configured LLM client, or ``None`` to use offline heuristics."""
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    try:
        if settings.llm_provider == "ollama":
            # Ollama ignores the key but the SDK requires a non-empty one.
            client = OpenAICompatibleLLMClient(
                api_key="ollama",
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                timeout=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
            )
        else:
            client = OpenAICompatibleLLMClient(
                api_key=settings.openrouter_api_key or "",
                base_url=settings.openrouter_base_url,
                model=settings.llm_model,
                timeout=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
                # OpenRouter app attribution; meaningless to other providers.
                extra_headers={"HTTP-Referer": settings.llm_referer, "X-Title": settings.llm_title},
            )
    except Exception:  # pragma: no cover - misconfiguration / missing SDK
        if settings.strict_provider_mode:
            raise
        logger.warning("llm_client_init_failed; falling back to offline heuristics", exc_info=True)
        return None
    logger.info("llm_client_ready provider=%s model=%s", settings.llm_provider, client.model_name)
    return client
