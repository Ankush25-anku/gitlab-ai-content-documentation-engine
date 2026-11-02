"""Agent 4 - Tone Optimizer: applies channel tone rules and GitLab terminology without changing facts."""
import re

from ai.agents.base import AgentResult, AgentSpec, run_agent
from ai.prompts.loader import channel_for, tone_rules
from ai.retrieval.knowledge import glossary_prompt_text, glossary_terms, marketing_words
from ai.schemas import Draft
from ai.text_utils import CITATION_RE, NEEDS_SOURCE_RE

SPEC = AgentSpec(name="tone_optimizer", stage="tone", output_model=Draft)

FACTUAL_CHANNELS = {"docs", "api_reference", "release_notes"}


def _protect(text: str) -> tuple[str, dict[str, str]]:
    """Shield code spans, citations and markers so replacements never touch them."""
    vault: dict[str, str] = {}

    def keep(m: re.Match) -> str:
        key = f"\u0000{len(vault)}\u0000"
        vault[key] = m.group(0)
        return key
    text = re.sub(r"```.*?```", keep, text, flags=re.S)
    text = re.sub(r"`[^`]+`", keep, text)
    text = CITATION_RE.sub(keep, text)
    text = NEEDS_SOURCE_RE.sub(keep, text)
    return text, vault


def _restore(text: str, vault: dict[str, str]) -> str:
    for key, val in vault.items():
        text = text.replace(key, val)
    return text


def retone(text: str, channel: str, instructions: str = "") -> tuple[str, list[str]]:
    changes: list[str] = []
    work, vault = _protect(text)
    for entry in glossary_terms():
        for bad in sorted(entry["avoid"], key=len, reverse=True):
            if bad.lower() == "click" and channel not in ("docs", "onboarding"):
                continue
            rx = re.compile(rf"(?<![\w-]){re.escape(bad)}(?![\w-])", re.I)
            if rx.search(work):
                work = rx.sub(entry["term"], work)
                changes.append(f'Terminology: "{bad}" -> "{entry["term"]}"')
    if channel in FACTUAL_CHANNELS or "neutral" in instructions.lower():
        for word in marketing_words():
            rx = re.compile(rf"\s?\b{re.escape(word)}\b", re.I)
            if rx.search(work):
                work = rx.sub("", work)
                changes.append(f'Removed marketing word "{word}"')
    work = re.sub(r"\bwill be able to\b", "can", work)
    work = re.sub(r"\bin order to\b", "to", work)
    work = re.sub(r"  +", " ", work)
    if "concise" in instructions.lower():
        work = re.sub(r"\b(very|really|basically|actually|quite)\s+", "", work, flags=re.I)
        changes.append("Tightened wording on request")
    return _restore(work, vault), sorted(set(changes))


def mock_tone(draft: Draft, channel: str, instructions: str) -> Draft:
    log: list[str] = []
    summary, c = retone(draft.summary, channel, instructions)
    log += c
    sections = []
    for s in draft.sections:
        body, c = retone(s.body_markdown, channel, instructions)
        log += c
        sections.append(s.model_copy(update={"body_markdown": body}))
    title, _ = retone(draft.title, channel)
    log = sorted(set(log)) or [f"No tone changes needed for the {channel} channel."]
    return draft.model_copy(update={"title": title, "summary": summary, "sections": sections, "change_log": log})


def run(draft: Draft, job: dict, instructions: str = "", prompt_version: int | None = None) -> AgentResult:
    channel = channel_for(job["content_type"], job.get("target_channel"))
    variables = {
        "target_channel": channel, "tone_rules": "\n".join(f"- {r}" for r in tone_rules(channel)),
        "glossary_terms": glossary_prompt_text(), "draft_json": draft.model_dump_json(indent=1),
        "instructions": instructions or "No extra instructions.",
    }
    return run_agent(SPEC, variables, lambda: mock_tone(draft, channel, instructions), prompt_version)
