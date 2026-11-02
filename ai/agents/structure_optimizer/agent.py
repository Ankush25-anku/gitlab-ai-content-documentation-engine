"""Agent 5 - Structure Optimizer: enforces the content-type template and scannable formatting."""
import re

from ai.agents.base import AgentResult, AgentSpec, run_agent
from ai.prompts.loader import content_type_template
from ai.schemas import Draft, Section

SPEC = AgentSpec(name="structure_optimizer", stage="structure", output_model=Draft)

STEP_HEADINGS = {"steps", "step-by-step setup", "how to get started", "try it"}


def _numbered(body: str) -> str:
    """Turn a run of plain sentences into a numbered procedure."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if len(paras) < 2 or any(p.startswith(("```", "|", "1.", "[NEEDS")) for p in paras):
        return body
    return "\n".join(f"{i}. {p}" for i, p in enumerate(paras, 1))


def mock_structure(draft: Draft, content_type: str) -> Draft:
    required: list[str] = content_type_template(content_type)["required_headings"]
    log: list[str] = []
    by_heading = {s.heading.lower(): s for s in draft.sections}
    ordered: list[Section] = []
    for h in required:
        sec = by_heading.pop(h.lower(), None)
        if sec is None:
            sec = Section(heading=h, body_markdown=f"[NEEDS SOURCE: {h.lower()} details are not in the provided inputs]")
            log.append(f'Added missing required section "{h}"')
        if h.lower() in STEP_HEADINGS:
            new_body = _numbered(sec.body_markdown)
            if new_body != sec.body_markdown:
                log.append(f'Converted "{h}" into numbered steps')
                sec = sec.model_copy(update={"body_markdown": new_body})
        ordered.append(sec)
    for extra in by_heading.values():  # keep non-template sections after the template ones
        ordered.append(extra)
        log.append(f'Kept extra section "{extra.heading}" after the template sections')
    if [s.heading for s in draft.sections][:len(required)] != required:
        log.append("Reordered sections to match the template")

    summary = draft.summary
    words = summary.split()
    if len(words) > 40:
        summary = " ".join(words[:40]).rstrip(",;") + "…"
        log.append("Shortened summary to 40 words")
    return draft.model_copy(update={"summary": summary, "sections": ordered,
                                    "change_log": log or ["Structure already matched the template."]})


def run(draft: Draft, job: dict, instructions: str = "", prompt_version: int | None = None) -> AgentResult:
    template = content_type_template(job["content_type"])
    variables = {
        "content_type": job["content_type"],
        "structure_template": "\n".join(f"- {h}" for h in template["required_headings"]) + "\n" + template["guidance"],
        "draft_json": draft.model_dump_json(indent=1), "instructions": instructions or "No extra instructions.",
    }
    return run_agent(SPEC, variables, lambda: mock_structure(draft, job["content_type"]), prompt_version)
