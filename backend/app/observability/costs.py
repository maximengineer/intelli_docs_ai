from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.core.settings import get_settings


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    source: Literal["provider", "estimate"] = "provider"


def estimate_tokens(text: str) -> int:
    # Conservative local approximation for logging only. Provider token counts
    # should replace this when a real model response includes usage metadata.
    return max(1, len(text.split()))


def estimate_cost_usd(usage: TokenUsage) -> float:
    settings = get_settings()
    input_cost = (usage.input_tokens / 1_000_000) * settings.llm_input_price_per_1m_tokens
    output_cost = (usage.output_tokens / 1_000_000) * settings.llm_output_price_per_1m_tokens
    return round(input_cost + output_cost, 8)
