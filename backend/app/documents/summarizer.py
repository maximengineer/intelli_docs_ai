from __future__ import annotations

import logging
import re

from app.core.settings import get_settings
from app.llm.client import LLMClient
from app.llm.prompt_registry import get_prompt

logger = logging.getLogger(__name__)


def summarize_document(text: str, llm_client: LLMClient | None = None) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return "No readable text was extracted from this document."

    if llm_client is not None:
        try:
            return _summarize_with_llm(clean, llm_client)
        except Exception:  # pragma: no cover - network/provider failure
            logger.warning("llm_summary_failed; using offline fallback", exc_info=True)
    return _summarize_with_heuristic(clean)


def _summarize_with_llm(clean_text: str, llm_client: LLMClient) -> str:
    prompt = get_prompt("summarize_document")
    truncated = clean_text[: get_settings().llm_max_input_chars]
    summary = llm_client.complete(
        f"Document text:\n{truncated}",
        system=prompt.template,
        temperature=0.0,
        max_tokens=400,
    )
    return summary.strip() or _summarize_with_heuristic(clean_text)


def _summarize_with_heuristic(clean_text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", clean_text)
    leading = " ".join(sentences[:3]).strip()
    key_facts = "\n- Key facts: Review extracted fields for structured values." if leading else ""
    risks = (
        "\n- Risks or actions: Validate important fields against the cited "
        "source text before use."
    )
    return "- What this document is: " + leading[:300] + key_facts + risks
