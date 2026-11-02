"""Loads versioned prompt files, content-type templates and tone rules.

Layout:
  ai/prompts/<agent>/v<N>.yaml          one file per prompt version
  ai/prompts/content_types/<type>.yaml   required headings + guidance per content type
  ai/prompts/tone/<channel>.yaml         tone rules per channel

The active version of an agent's prompt is the highest v<N>, unless overridden with an
environment variable such as PROMPT_VERSION_DOCUMENTATION_WRITER=1.
"""
import hashlib
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

PROMPT_DIR = Path(__file__).parent

CHANNEL_FOR_TYPE = {
    "release_note": "release_notes",
    "docs_page": "docs",
    "blog": "blog",
    "api_reference": "api_reference",
    "onboarding_guide": "onboarding",
}


@dataclass(frozen=True)
class PromptTemplate:
    agent: str
    version: int
    role: str
    goal: str
    backstory: str
    system: str
    user: str
    body: str  # raw file text

    @property
    def id(self) -> str:
        return f"{self.agent}@v{self.version}"

    @property
    def file_hash(self) -> str:
        return hashlib.sha256(self.body.encode()).hexdigest()[:16]

    def render(self, **variables) -> tuple[str, str]:
        return _fill(self.system, variables), _fill(self.user, variables)

    def render_field(self, field: str, **variables) -> str:
        return _fill(getattr(self, field), variables)


def _fill(text: str, variables: dict) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1).strip()
        return str(variables.get(key, m.group(0)))
    return re.sub(r"\{\{\s*([\w]+)\s*\}\}", repl, text or "")


def available_versions(agent: str) -> list[int]:
    folder = PROMPT_DIR / agent
    return sorted(int(p.stem[1:]) for p in folder.glob("v*.yaml"))


def load_prompt(agent: str, version: int | None = None) -> PromptTemplate:
    if version is None:
        override = os.getenv(f"PROMPT_VERSION_{agent.upper()}")
        version = int(override) if override else available_versions(agent)[-1]
    return _load(agent, version)


@lru_cache(maxsize=64)
def _load(agent: str, version: int) -> PromptTemplate:
    path = PROMPT_DIR / agent / f"v{version}.yaml"
    body = path.read_text(encoding="utf-8")
    data = yaml.safe_load(body)
    return PromptTemplate(
        agent=agent, version=int(data["version"]), role=data.get("role", ""), goal=data.get("goal", ""),
        backstory=data.get("backstory", ""), system=data.get("system", ""), user=data.get("user", ""), body=body,
    )


def all_prompts() -> list[PromptTemplate]:
    out = []
    for folder in sorted(PROMPT_DIR.iterdir()):
        if folder.is_dir() and folder.name not in ("content_types", "tone", "evaluation", "__pycache__"):
            for v in available_versions(folder.name):
                out.append(load_prompt(folder.name, v))
    return out


@lru_cache(maxsize=16)
def content_type_template(content_type: str) -> dict:
    return yaml.safe_load((PROMPT_DIR / "content_types" / f"{content_type}.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=16)
def tone_rules(channel: str) -> list[str]:
    path = PROMPT_DIR / "tone" / f"{channel}.yaml"
    if not path.exists():
        path = PROMPT_DIR / "tone" / "docs.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["rules"]


def channel_for(content_type: str, target_channel: str | None = None) -> str:
    if target_channel and (PROMPT_DIR / "tone" / f"{target_channel}.yaml").exists():
        return target_channel
    return CHANNEL_FOR_TYPE.get(content_type, "docs")
