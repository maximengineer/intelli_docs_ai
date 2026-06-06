from __future__ import annotations

import logging
import re

from app.core.text import WORD_RE
from app.llm.client import LLMClient
from app.llm.prompt_registry import get_prompt
from app.rag.schemas import RetrievedChunk

logger = logging.getLogger(__name__)

FALLBACK_ANSWER = (
    "The available documents do not contain enough information to answer this question."
)
STOPWORDS = {
    "about",
    "above",
    "are",
    "company",
    "contains",
    "does",
    "document",
    "documents",
    "from",
    "has",
    "have",
    "mentions",
    "mention",
    "office",
    "that",
    "the",
    "what",
    "when",
    "where",
    "which",
    "with",
}


def generate_answer_with_placeholders(
    question: str,
    context: list[RetrievedChunk],
    llm_client: LLMClient | None = None,
) -> str:
    """Produce an answer that cites context with ``<cite index="N">`` placeholders.

    When an LLM client is configured the model writes the answer and chooses the
    citation indexes; the backend later validates those indexes and maps them to
    real metadata (see ``citations.map_citations``). With no client, a
    deterministic keyword-overlap extractor runs so the demo works offline.
    """
    if not context:
        return FALLBACK_ANSWER
    if llm_client is not None:
        try:
            return _generate_with_llm(question, context, llm_client)
        except Exception:  # pragma: no cover - network/provider failure
            logger.warning("llm_generation_failed; using offline fallback", exc_info=True)
    return _generate_with_heuristic(question, context)


def _generate_with_llm(question: str, context: list[RetrievedChunk], llm_client: LLMClient) -> str:
    prompt = get_prompt("answer_question")
    enumerated = "\n\n".join(
        f"[{index}] (file: {chunk.filename}, page: {chunk.page_number or 'n/a'})\n{chunk.text}"
        for index, chunk in enumerate(context)
    )
    user_message = (
        f"Context passages:\n{enumerated}\n\n"
        f"Question: {question}\n\n"
        "Answer using only the context above. Cite each supporting passage with a "
        'placeholder like <cite index="0"> using the bracketed passage numbers. '
        "If the context does not support an answer, reply with exactly:\n"
        f"{FALLBACK_ANSWER}"
    )
    return llm_client.complete(user_message, system=prompt.template, temperature=0.0)


def _generate_with_heuristic(question: str, context: list[RetrievedChunk]) -> str:
    question_terms = {
        token.lower()
        for token in WORD_RE.findall(question)
        if len(token) > 2 and token.lower() not in STOPWORDS
    }
    if not question_terms:
        return FALLBACK_ANSWER
    evidence: list[str] = []
    for index, chunk in enumerate(context):
        sentence = _best_sentence(chunk.text, question_terms)
        if sentence:
            evidence.append(f'{sentence} <cite index="{index}">')
    if not evidence:
        return FALLBACK_ANSWER
    if len(evidence) == 1:
        return evidence[0]
    return " ".join(evidence[:3])


def _best_sentence(text: str, question_terms: set[str]) -> str | None:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    best_sentence = None
    best_score = 0
    required_score = min(2, len(question_terms))
    for sentence in sentences:
        terms = {token.lower() for token in WORD_RE.findall(sentence)}
        score = len(question_terms & terms)
        if score > best_score:
            best_score = score
            best_sentence = sentence.strip()
    if best_score < required_score:
        return None
    return best_sentence[:500]
