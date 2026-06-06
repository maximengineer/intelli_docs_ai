from __future__ import annotations

import re

from pydantic import BaseModel

PRIVACY_POLICY_VERSION = "phase2-basic-v1"

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b")
# 13-19 digits with at most a single space/hyphen between digits (card-like).
# Tighter than a greedy separator run, so it does not swallow arbitrary spaced
# text or short (<13 digit) phone numbers.
CARD_RE = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
ACCOUNT_RE = re.compile(r"\b(?:IBAN|Account|Acct)\s*[:#]?\s*[A-Z0-9 -]{8,34}\b", re.IGNORECASE)
TAX_ID_RE = re.compile(r"\b(?:Tax ID|VAT|TIN)\s*[:#]?\s*[A-Z0-9 -]{5,24}\b", re.IGNORECASE)
ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


class PrivacyTexts(BaseModel):
    raw_text: str
    ai_text: str
    display_text: str
    privacy_policy_version: str = PRIVACY_POLICY_VERSION


def apply_basic_privacy(text: str) -> PrivacyTexts:
    """Create Phase 2 raw/AI/display text variants.

    The policy intentionally preserves organisation and vendor names while
    redacting high-risk identifiers. ``raw_text`` is returned for local
    processing only and is never persisted, logged, or displayed; the pipeline
    uses ``ai_text`` for extraction/embeddings and ``display_text`` for snippets.
    """

    ai_text = _redact_high_risk(text)
    display_text = ai_text
    return PrivacyTexts(raw_text=text, ai_text=ai_text, display_text=display_text)


def _redact_high_risk(text: str) -> str:
    protected_dates: dict[str, str] = {}

    def protect_date(match: re.Match[str]) -> str:
        token = f"__DATE_{len(protected_dates)}__"
        protected_dates[token] = match.group(0)
        return token

    redacted = ISO_DATE_RE.sub(protect_date, text)
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
    redacted = CARD_RE.sub("[REDACTED_CARD]", redacted)
    redacted = PHONE_RE.sub("[REDACTED_PHONE]", redacted)
    redacted = ACCOUNT_RE.sub("[REDACTED_ACCOUNT]", redacted)
    redacted = TAX_ID_RE.sub("[REDACTED_TAX_ID]", redacted)
    for token, date_value in protected_dates.items():
        redacted = redacted.replace(token, date_value)
    return redacted
