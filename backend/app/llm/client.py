from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol

from app.core.settings import get_settings

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
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


class OpenRouterLLMClient:
    """OpenAI-compatible client pointed at OpenRouter.

    A single ``OPENROUTER_API_KEY`` unlocks chat completions across many model
    providers. Timeouts and bounded retries are delegated to the OpenAI SDK.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float,
        max_retries: int,
        referer: str,
        title: str,
    ) -> None:
        from openai import OpenAI  # lazy import keeps offline installs slim

        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._model = model
        self._extra_headers = {"HTTP-Referer": referer, "X-Title": title}

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
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "extra_headers": self._extra_headers,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(**kwargs)
        return (response.choices[0].message.content or "").strip()


@lru_cache
def get_llm_client() -> LLMClient | None:
    """Return a configured LLM client, or ``None`` to use offline heuristics."""
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    try:
        client = OpenRouterLLMClient(
            api_key=settings.openrouter_api_key or "",
            base_url=settings.openrouter_base_url,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            referer=settings.llm_referer,
            title=settings.llm_title,
        )
    except Exception:  # pragma: no cover - misconfiguration / missing SDK
        logger.warning("llm_client_init_failed; falling back to offline heuristics", exc_info=True)
        return None
    logger.info("llm_client_ready model=%s", settings.llm_model)
    return client
