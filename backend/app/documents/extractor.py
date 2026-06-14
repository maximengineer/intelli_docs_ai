from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from app.core.settings import get_settings
from app.documents.schemas import ExtractedFields
from app.llm.client import LLMClient
from app.llm.prompt_registry import get_prompt

logger = logging.getLogger(__name__)

AMOUNT_RE = re.compile(
    r"(?<!\w)(?:(?P<prefix>EUR|USD|GBP|\$|€|£)\s*"
    r"(?P<prefix_amount>[0-9][0-9,]*(?:\.[0-9]{2})?)|"
    r"(?P<suffix_amount>[0-9][0-9,]*(?:\.[0-9]{2})?)\s*"
    r"(?P<suffix>EUR|USD|GBP|\$|€|£))(?!\w)",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")


def extract_fields(text: str, llm_client: LLMClient | None = None) -> ExtractedFields:
    if llm_client is not None and text.strip():
        try:
            return _extract_with_llm(text, llm_client)
        except Exception:  # pragma: no cover - network/provider failure
            logger.warning("llm_extraction_failed; using offline fallback", exc_info=True)
    return _extract_with_heuristic(text)


def _extract_with_llm(text: str, llm_client: LLMClient) -> ExtractedFields:
    prompt = get_prompt("extract_fields")
    schema = json.dumps(ExtractedFields.model_json_schema())
    truncated = text[: get_settings().llm_max_input_chars]
    raw = llm_client.complete(
        f"JSON schema:\n{schema}\n\nDocument text:\n{truncated}",
        system=prompt.template,
        temperature=0.0,
        json_mode=True,
    )
    try:
        # Validate against the Pydantic schema rather than regex-parsing the JSON.
        return ExtractedFields.model_validate_json(raw)
    except ValidationError:
        logger.warning("llm_extraction_invalid_schema; using offline fallback")
        return _extract_with_heuristic(text)


def _extract_with_heuristic(text: str) -> ExtractedFields:
    lowered = text.lower()
    document_type = "unknown"
    if "report" in lowered:
        document_type = "report"
    elif "policy" in lowered:
        document_type = "policy"
    elif "invoice" in lowered or "total amount" in lowered:
        document_type = "invoice"
    elif "agreement" in lowered or "contract" in lowered:
        document_type = "contract"

    amount, currency = _extract_amount(text)
    vendor = _value_after_label(text, ["vendor", "supplier", "from", "company"])
    party_name = _value_after_label(text, ["party", "client", "customer"])
    dates = DATE_RE.findall(text)

    return ExtractedFields(
        document_type=document_type,
        vendor=vendor,
        amount=amount,
        currency=currency,
        invoice_date=_value_after_label(text, ["invoice date"]) or (dates[0] if dates else None),
        due_date=_value_after_label(text, ["due date", "payment due"]),
        party_name=party_name,
        effective_date=_value_after_label(text, ["effective date"])
        or (dates[0] if dates else None),
        renewal_terms=_value_after_label(text, ["renewal", "renewal terms"]),
        risk_level=_risk_level(text),
    )


def _extract_amount(text: str) -> tuple[float | None, str | None]:
    match = AMOUNT_RE.search(text)
    if not match:
        return None, None
    currency_token = (match.group("prefix") or match.group("suffix") or "").upper()
    amount_text = match.group("prefix_amount") or match.group("suffix_amount")
    if amount_text is None:
        return None, None
    currency = {"€": "EUR", "$": "USD", "£": "GBP"}.get(currency_token, currency_token)
    amount = float(amount_text.replace(",", ""))
    return amount, currency


def _value_after_label(text: str, labels: list[str]) -> str | None:
    for label in labels:
        pattern = re.compile(rf"^{re.escape(label)}\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
        match = pattern.search(text)
        if match:
            return match.group(1).strip()[:160]
    return None


def _risk_level(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ["termination for cause", "penalty", "indemnity"]):
        return "high"
    if any(term in lowered for term in ["auto-renew", "late fee", "limitation"]):
        return "medium"
    if any(term in lowered for term in ["standard terms", "routine", "low risk"]):
        return "low"
    return "unknown"
