"""Agent 6 - Publishing Coordinator: prepares an APPROVED draft for a Git-based docs workflow."""
import json
from datetime import date

from ai.agents.base import AgentResult, AgentSpec, run_agent
from ai.schemas import Draft, PublishPackage, SourceRef
from ai.text_utils import slugify

SPEC = AgentSpec(name="publishing_coordinator", stage="publish_prep", output_model=PublishPackage)

PATHS = {"release_note": "releases", "blog": "blog", "api_reference": "doc/api"}
MR_PREFIX = {"release_note": "Release notes", "blog": "Blog", "api_reference": "API docs"}


def mock_publish(draft: Draft, sources: list[SourceRef], job: dict, owner: str, approvers: list[str]) -> PublishPackage:
    slug = slugify(draft.title)
    folder = PATHS.get(job["content_type"], f"doc/{slugify(job['product_area'])}")
    used = sorted({sid for s in draft.sections for sid in s.source_ids}, key=lambda x: int(x[1:]))
    by_id = {s.id: s for s in sources}
    source_lines = [f"- [{sid}] {by_id[sid].title} (`{by_id[sid].chunk_id}`)" for sid in used if sid in by_id]
    front = {
        "title": draft.title, "content_type": job["content_type"], "stage": job["product_area"],
        "group": "Technical Writing", "owner": owner, "last_reviewed": date.today().isoformat(),
        "info": "Generated with the AI Content & Documentation Engine and approved by a human reviewer.",
        "sources": [by_id[sid].chunk_id for sid in used if sid in by_id],
    }
    description = "\n".join([
        f"## What does this MR do?\n\nAdds the {job['content_type'].replace('_', ' ')} **{draft.title}**.",
        f"\n{draft.summary}",
        "\n## Sources\n", *source_lines,
        "\n## Approvals\n", *[f"- {a}" for a in approvers],
        "\n## Reviewer checklist\n", "- [ ] Technical accuracy confirmed by the feature owner",
        "- [ ] Vale and markdownlint pass", "- [ ] Links and examples tested",
    ])
    return PublishPackage(
        slug=slug, file_path=f"{folder}/{slug}.md", front_matter=front,
        mr_title=f"{MR_PREFIX.get(job['content_type'], 'Docs')}: {draft.title}", mr_description=description,
        labels=["documentation", f"type::{job['content_type']}", f"area::{slugify(job['product_area'])}"],
        target_channel=job["target_channel"], owner=owner, approved_by=approvers,
    )


def run(draft: Draft, sources: list[SourceRef], job: dict, owner: str, approvers: list[str],
        prompt_version: int | None = None) -> AgentResult:
    variables = {
        "owner": owner, "approvers": ", ".join(approvers), "target_channel": job["target_channel"],
        "product_area": slugify(job["product_area"]), "draft_json": draft.model_dump_json(indent=1),
        "sources_json": json.dumps([{"id": s.id, "title": s.title, "chunk_id": s.chunk_id} for s in sources]),
    }
    return run_agent(SPEC, variables, lambda: mock_publish(draft, sources, job, owner, approvers), prompt_version)
