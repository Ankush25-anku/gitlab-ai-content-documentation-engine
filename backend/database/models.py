"""SQLAlchemy models. Mirrors backend/database/migrations/001_init.sql (the Supabase schema)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


try:  # pgvector column on Postgres, JSON list on SQLite
    from pgvector.sqlalchemy import Vector

    from backend.config import get_settings

    EmbeddingType = JSON().with_variant(Vector(get_settings().embedding_dim), "postgresql")
except ImportError:  # pragma: no cover - pgvector is optional for local dev
    EmbeddingType = JSON()


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)  # creator | tech_reviewer | doc_lead | publisher | admin
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContentJob(Base):
    __tablename__ = "content_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    audience: Mapped[str] = mapped_column(String)
    product_area: Mapped[str] = mapped_column(String)
    target_channel: Mapped[str] = mapped_column(String)
    target_length: Mapped[int] = mapped_column(Integer, default=600)
    owner_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"))
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("profiles.id"), nullable=True)
    deadline: Mapped[str | None] = mapped_column(String, nullable=True)
    publication_format: Mapped[str] = mapped_column(String, default="markdown")
    status: Mapped[str] = mapped_column(String, default="INTAKE")
    current_stage: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    excluded_chunk_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    inputs: Mapped[list["JobInput"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    drafts: Mapped[list["Draft"]] = relationship(back_populates="job", cascade="all, delete-orphan",
                                                 order_by="Draft.version")


class JobInput(Base):
    __tablename__ = "job_inputs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("content_jobs.id"))
    kind: Mapped[str] = mapped_column(String)  # diff | mr | issue | api_spec | brief | release_notes | doc
    filename: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    redacted: Mapped[bool] = mapped_column(Boolean, default=False)
    redactions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    job: Mapped[ContentJob] = relationship(back_populates="inputs")


class ContextPackRecord(Base):
    __tablename__ = "context_packs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("content_jobs.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    retrieval_json: Mapped[dict] = mapped_column(JSON)  # sources offered to agents (inputs + KB chunks)
    pack_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Context Reader output
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # "<agent>@v<n>"
    agent: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer)
    file_hash: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("content_jobs.id"))
    stage: Mapped[str] = mapped_column(String)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    prompt_version_id: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str] = mapped_column(String)
    input_hash: Mapped[str] = mapped_column(String, default="")
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, default="running")  # running | succeeded | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Draft(Base):
    __tablename__ = "drafts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("content_jobs.id"))
    version: Mapped[int] = mapped_column(Integer)
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage: Mapped[str] = mapped_column(String)  # stage that produced it, or "human_edit"
    content_md: Mapped[str] = mapped_column(Text)
    draft_json: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String)  # agent name or user id
    quality_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    review_state: Mapped[str] = mapped_column(String, default="pending")  # pending | approved | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    job: Mapped[ContentJob] = relationship(back_populates="drafts")
    claims: Mapped[list["ClaimCheck"]] = relationship(back_populates="draft", cascade="all, delete-orphan")


class ClaimCheck(Base):
    __tablename__ = "claim_checks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id"))
    claim: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String)  # supported | partial | unsupported
    source_ids: Mapped[list] = mapped_column(JSON, default=list)
    fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft: Mapped[Draft] = relationship(back_populates="claims")


class ReviewAction(Base):
    __tablename__ = "review_actions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id"))
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"))
    action: Mapped[str] = mapped_column(String)  # approve | reject | edit | request_revision | comment | resolve_claim
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_category: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KBDocument(Base):
    __tablename__ = "kb_documents"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # slug
    title: Mapped[str] = mapped_column(String)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    product_area: Mapped[str] = mapped_column(String, default="general")
    content_type: Mapped[str] = mapped_column(String, default="docs_page")
    kind: Mapped[str] = mapped_column(String, default="doc")  # doc | style_guide | glossary | template
    owner: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[str] = mapped_column(String)  # ISO date from front matter (freshness signal)


class KBChunk(Base):
    __tablename__ = "kb_chunks"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # <slug>#<anchor>#<n>
    document_id: Mapped[str] = mapped_column(ForeignKey("kb_documents.id"))
    heading: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(EmbeddingType)  # vector(768) in Postgres (see migration)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class Export(Base):
    __tablename__ = "exports"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id"))
    format: Mapped[str] = mapped_column(String)  # markdown | cms_json | gitlab_mr
    target: Mapped[str | None] = mapped_column(String, nullable=True)
    mr_url: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String)
    exported_by: Mapped[str] = mapped_column(String)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    event: Mapped[str] = mapped_column(String)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MetricSnapshot(Base):
    """Optional cache table for dashboard aggregates (not required; metrics are computed live)."""
    __tablename__ = "metric_snapshots"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String)
    value: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
