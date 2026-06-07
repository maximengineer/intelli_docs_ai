from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

USE_LLM = "--use-llm" in sys.argv
if not USE_LLM:
    # Pin the CLI evaluator before importing app modules. Several services have
    # import-time singletons, and .env may contain live provider settings.
    os.environ["ENABLE_LLM"] = "false"
    os.environ["EMBEDDING_BACKEND"] = "hash"
    os.environ["VECTOR_STORE_BACKEND"] = "memory"
    os.environ["DOCUMENT_PROCESSING_BACKEND"] = "thread"
    os.environ.pop("DATABASE_URL", None)

from app.evaluation.service import run_offline_evaluation  # noqa: E402


def main() -> None:
    # Deterministic offline by default; pass --use-llm to evaluate the real
    # OpenRouter + embedding path configured in .env.
    report = run_offline_evaluation(force_offline=not USE_LLM)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
