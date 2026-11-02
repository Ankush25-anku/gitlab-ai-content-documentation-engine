"""Structured knowledge that is not retrieved by similarity: glossary and marketing word list."""
from functools import lru_cache
from pathlib import Path

import yaml

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@lru_cache
def glossary() -> dict:
    return yaml.safe_load((DATA_DIR / "style_guides" / "glossary.yaml").read_text(encoding="utf-8"))


def glossary_terms() -> list[dict]:
    return glossary()["terms"]


def marketing_words() -> list[str]:
    return glossary().get("marketing_words", [])


def terms_found_in(text: str) -> list[str]:
    low = text.lower()
    return [t["term"] for t in glossary_terms() if t["term"].lower() in low]


def glossary_prompt_text(limit: int = 30) -> str:
    return "; ".join(f'"{t["term"]}" (not {", ".join(t["avoid"])})' for t in glossary_terms()[:limit])
