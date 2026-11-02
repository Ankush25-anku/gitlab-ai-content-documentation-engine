"""Structured outputs for every agent stage. Agents must return JSON that validates against these."""
from typing import Literal

from pydantic import BaseModel, Field

ContentType = Literal["release_note", "docs_page", "blog", "api_reference", "onboarding_guide"]
Confidence = Literal["high", "medium", "low"]
Verdict = Literal["supported", "partial", "unsupported"]


class SourceRef(BaseModel):
    """A source offered to the agents: one chunk of a job input or of the knowledge base."""
    id: str = Field(description="Short citation id, e.g. S3")
    chunk_id: str = Field(description="Stable chunk id, e.g. input:diff.patch#2 or ci-caching#cache-keys#0")
    origin: Literal["input", "kb"]
    title: str
    text: str
    score: float | None = None
    updated_at: str | None = None
    stale: bool = False


class SourceFact(BaseModel):
    id: str = Field(description="Fact id, e.g. F1")
    source_id: str = Field(description="Citation id of the source that states this fact, e.g. S3")
    text: str
    confidence: Confidence = "high"


class ContextPack(BaseModel):
    """Output of the Context Reader."""
    summary: str
    audience: str
    content_type: ContentType
    key_points: list[str] = Field(default_factory=list)
    facts: list[SourceFact]
    gaps: list[str] = Field(default_factory=list)
    blocking_gaps: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    terminology: list[str] = Field(default_factory=list)


class Section(BaseModel):
    heading: str
    body_markdown: str = Field(description="Markdown body; factual sentences cite sources as [S#]")
    source_ids: list[str] = Field(default_factory=list)
    generated_example: bool = False


class Draft(BaseModel):
    """Output of the Documentation Writer, Tone Optimizer and Structure Optimizer."""
    title: str
    summary: str
    sections: list[Section]
    assumptions: list[str] = Field(default_factory=list)
    reviewer_notes: list[str] = Field(default_factory=list)
    change_log: list[str] = Field(default_factory=list, description="What this stage changed")


class ClaimCheck(BaseModel):
    claim: str
    verdict: Verdict
    source_ids: list[str] = Field(default_factory=list)
    fix: str | None = None


class ReviewReport(BaseModel):
    """Output of the Technical Reviewer."""
    claims: list[ClaimCheck]
    risk_flags: list[str] = Field(default_factory=list)
    reviewer_questions: list[str] = Field(default_factory=list)


class TechReviewOutput(BaseModel):
    """The Technical Reviewer returns its report and a draft with unsupported claims removed or marked."""
    report: ReviewReport
    draft: Draft


class PublishPackage(BaseModel):
    """Output of the Publishing Coordinator."""
    slug: str
    file_path: str
    front_matter: dict
    mr_title: str
    mr_description: str
    labels: list[str] = Field(default_factory=list)
    target_channel: str
    owner: str
    approved_by: list[str] = Field(default_factory=list)


class QualityScores(BaseModel):
    """Computed deterministically by ai/evaluation/quality.py (no LLM)."""
    source_coverage: float = Field(description="Share of context facts cited in the draft (0-1)")
    citation_validity: float = Field(description="Share of [S#] markers that resolve to a real source (0-1)")
    invalid_citations: list[str] = Field(default_factory=list)
    claim_support_rate: float = Field(description="Supported claims / all claims (0-1)")
    unsupported_claims: int
    needs_source_markers: int = Field(description="Count of [NEEDS SOURCE: ...] markers left in the draft")
    structure_compliance: float = Field(description="Share of required template headings present (0-1)")
    missing_headings: list[str] = Field(default_factory=list)
    readability_avg_sentence_words: float
    word_count: int
    overall: float = Field(description="Weighted 0-100 score shown as the headline badge")
