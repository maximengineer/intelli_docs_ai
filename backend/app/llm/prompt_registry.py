from functools import lru_cache
from pathlib import Path

import yaml

from app.llm.schemas import PromptTemplate


class PromptRegistry:
    def __init__(self, prompt_dir: Path | None = None) -> None:
        self.prompt_dir = prompt_dir or Path(__file__).resolve().parents[3] / "prompts"

    def load(self, name: str) -> PromptTemplate:
        path = self.prompt_dir / f"{name}.yaml"
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
        return PromptTemplate(**data)


@lru_cache
def get_prompt(name: str) -> PromptTemplate:
    """Load and cache a versioned prompt template by name."""
    return PromptRegistry().load(name)
