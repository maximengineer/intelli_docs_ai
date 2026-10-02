import re
from decimal import Decimal, InvalidOperation

# A word token: starts alphanumeric, then alphanumerics, underscores or hyphens.
# Shared by the hash embedder and the heuristic answerer so they tokenise alike.
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")

# A number as written in business text: "12,450.00", "3", "2026", "5.5".
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
# Dotted dates ("12.05.2026") would otherwise read as the decimal 12.05 plus
# 2026; split them into day, month and year like ISO and slashed dates.
DOTTED_DATE_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")

# General English function words. They carry no evidence, so they must not count
# as overlap between an answer and the text it cites. Words of two characters or
# fewer are already dropped by ``content_tokens``.
FUNCTION_WORDS = frozenset(
    {
        "about", "above", "after", "again", "against", "all", "also", "and", "any",
        "are", "because", "been", "before", "being", "below", "between", "both",
        "but", "can", "could", "did", "does", "doing", "down", "during", "each",
        "few", "for", "from", "further", "had", "has", "have", "having", "her",
        "here", "hers", "him", "his", "how", "into", "its", "itself", "just",
        "more", "most", "not", "now", "off", "once", "only", "other", "our",
        "out", "over", "own", "per", "same", "she", "should", "some", "such",
        "than", "that", "the", "their", "them", "then", "there", "these", "they",
        "this", "those", "through", "too", "under", "until", "very", "was",
        "were", "what", "when", "where", "which", "while", "who", "whom", "why",
        "will", "with", "would", "you", "your",
    }
)  # fmt: skip


def content_tokens(text: str) -> set[str]:
    """Lower-cased word tokens that can carry evidence (no short or function words)."""
    return {
        token
        for token in (match.lower() for match in WORD_RE.findall(text))
        if len(token) > 2 and token not in FUNCTION_WORDS
    }


def numeric_values(text: str) -> set[Decimal]:
    """Numbers in ``text`` normalised so "12,450.00", "12450" and "12450.0" compare equal."""
    values: set[Decimal] = set()
    text = DOTTED_DATE_RE.sub(lambda match: match.group().replace(".", " "), text)
    for match in NUMBER_RE.findall(text):
        try:
            values.add(Decimal(match.replace(",", "")).normalize())
        except InvalidOperation:
            continue
    return values
