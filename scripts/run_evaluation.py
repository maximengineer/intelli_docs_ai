from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evaluation.service import run_offline_evaluation


def main() -> None:
    # Deterministic offline by default; pass --use-llm to evaluate the real
    # OpenRouter + embedding path configured in .env.
    use_llm = "--use-llm" in sys.argv
    report = run_offline_evaluation(force_offline=not use_llm)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
