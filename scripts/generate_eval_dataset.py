from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.llm.client import get_llm_client  # noqa: E402


class GeneratedQuestion(BaseModel):
    question: str = Field(min_length=3)
    expected_facts: list[str] = Field(default_factory=list)


class GeneratedDatasetCandidate(BaseModel):
    factual_questions: list[GeneratedQuestion] = Field(min_length=1, max_length=5)
    negative_question: str = Field(min_length=3)
    expected_fields: dict[str, Any] = Field(default_factory=dict)


def main() -> None:
    args = parse_args()
    if not os.getenv("ENABLE_LLM"):
        os.environ["ENABLE_LLM"] = "true"
    client = get_llm_client()
    if client is None:
        raise SystemExit(
            "No LLM client configured. Set ENABLE_LLM=true and OPENROUTER_API_KEY, "
            "then rerun this candidate generator."
        )

    sample_paths = sorted(args.samples_dir.glob("*.txt"))
    if args.limit is not None:
        sample_paths = sample_paths[: args.limit]
    if not sample_paths:
        raise SystemExit(f"No .txt sample documents found under {args.samples_dir}.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    question_rows: list[dict[str, Any]] = []
    negative_rows: list[dict[str, Any]] = []
    extraction_rows: list[dict[str, Any]] = []

    for path in sample_paths:
        candidate = generate_candidate(client, path)
        stem = path.stem
        for index, question in enumerate(candidate.factual_questions, start=1):
            question_rows.append(
                {
                    "question_id": f"generated_{stem}_{index}",
                    "question": question.question,
                    "expected_filenames": [path.name],
                    "expected_facts": question.expected_facts,
                    "expected_response_type": "answer",
                    "review_status": "needs_manual_review",
                }
            )
        negative_rows.append(
            {
                "question_id": f"generated_{stem}_negative",
                "question": candidate.negative_question,
                "expected_response_type": "insufficient_information",
                "review_status": "needs_manual_review",
            }
        )
        extraction_rows.append(
            {
                "filename": path.name,
                "expected_fields": candidate.expected_fields,
                "review_status": "needs_manual_review",
            }
        )

    write_jsonl(args.output_dir / "questions.generated.jsonl", question_rows)
    write_jsonl(args.output_dir / "negative_questions.generated.jsonl", negative_rows)
    write_jsonl(args.output_dir / "expected_extractions.generated.jsonl", extraction_rows)
    print(f"Wrote generated candidates to {args.output_dir}")
    print("Manually review before copying any rows into data/evaluation/*.jsonl.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate evaluation dataset candidates from synthetic sample documents."
    )
    parser.add_argument(
        "--samples-dir",
        type=Path,
        default=ROOT / "data" / "sample_documents",
        help="Directory of synthetic sample .txt documents.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "evaluation" / "generated_candidates",
        help="Directory for generated candidate JSONL files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max number of sample documents to process.",
    )
    return parser.parse_args()


def generate_candidate(client: object, path: Path) -> GeneratedDatasetCandidate:
    raw = client.complete(
        build_prompt(path.name, path.read_text(encoding="utf-8")),
        temperature=0.0,
        json_mode=True,
    )
    return GeneratedDatasetCandidate.model_validate(json.loads(strip_json_fence(raw)))


def build_prompt(filename: str, text: str) -> str:
    return f"""
You are generating candidate evaluation data for IntelliDocs AI.

Document filename: {filename}

Document text:
{text}

Return only valid JSON matching this schema:
{{
  "factual_questions": [
    {{
      "question": "A factual question answerable only from this document",
      "expected_facts": ["short exact fact strings expected in a good answer"]
    }}
  ],
  "negative_question": "A plausible but unanswerable question for this document",
  "expected_fields": {{
    "document_type": "invoice|contract|policy|report|unknown",
    "vendor": null,
    "amount": null,
    "currency": null,
    "invoice_date": null,
    "due_date": null,
    "party_name": null,
    "effective_date": null,
    "renewal_terms": null,
    "risk_level": "low|medium|high|unknown"
  }}
}}

Rules:
- Generate exactly 3 factual questions.
- Generate exactly 1 negative question.
- Use synthetic, non-confidential content only.
- Do not invent facts not present in the document.
- Keep expected facts short and reviewable.
""".strip()


def strip_json_fence(value: str) -> str:
    stripped = value.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
