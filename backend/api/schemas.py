"""Request bodies for the REST API."""
from typing import Literal

from pydantic import BaseModel, Field

from ai.schemas import ContentType

InputKind = Literal["diff", "mr", "issue", "api_spec", "brief", "release_notes", "doc", "notes"]
Stage = Literal["context", "draft", "tech_review", "tone", "structure"]


class InlineInput(BaseModel):
    kind: InputKind = "notes"
    filename: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)


class JobCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    content_type: ContentType
    audience: str = Field(min_length=2, max_length=200)
    product_area: str = Field(min_length=2, max_length=100)
    target_channel: Literal["docs", "release_notes", "blog", "api_reference", "onboarding"]
    target_length: int = Field(default=600, ge=100, le=3000)
    reviewer_id: str | None = None
    deadline: str | None = None
    publication_format: Literal["markdown", "gitlab_mr", "cms_json"] = "markdown"
    inputs: list[InlineInput] = Field(default_factory=list)


class ContextPackRequest(BaseModel):
    job_id: str
    excluded_chunk_ids: list[str] | None = None


class WorkflowRunRequest(BaseModel):
    job_id: str
    from_stage: Stage | None = None
    simulate_failure: Stage | None = Field(default=None, description="Dev/demo only: force a model failure")
    prompt_versions: dict[str, int] | None = Field(default=None, description='Pin prompt versions, e.g. {"draft": 1}')


class ReviewRequest(BaseModel):
    action: Literal["approve", "reject", "edit", "request_revision", "comment", "resolve_claim"]
    comment: str | None = None
    issue_category: Literal["accuracy", "unsupported_claim", "tone", "structure", "terminology",
                            "missing_info", "other"] | None = None
    content_md: str | None = Field(default=None, description="Full edited Markdown for action=edit")
    claim_id: str | None = None
    resolution: Literal["remove", "override"] | None = None
    revision_stages: list[Stage] | None = Field(default=None, description="Stages to rerun on request_revision")


class RefineRequest(BaseModel):
    stages: list[Literal["draft", "tech_review", "tone", "structure"]] = Field(min_length=1)
    instructions: str = Field(default="", max_length=1000)
    prompt_versions: dict[str, int] | None = None


class ExportRequest(BaseModel):
    draft_id: str
    format: Literal["markdown", "gitlab_mr", "cms_json"] = "markdown"


class PrepareRequest(BaseModel):
    draft_id: str
