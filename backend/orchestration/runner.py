"""Workflow orchestrator.

Each stage is one agent (one single-task crew). The runner persists every stage output to
agent_runs (and a new draft version where the stage changes the draft) BEFORE the next stage
starts, which gives the UI live intermediate outputs, single-stage reruns and crash recovery.
"""
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.agents import base as agent_base
from ai.agents.context_reader import agent as context_reader
from ai.agents.documentation_writer import agent as documentation_writer
from ai.agents.publishing_coordinator import agent as publishing_coordinator
from ai.agents.structure_optimizer import agent as structure_optimizer
from ai.agents.technical_reviewer import agent as technical_reviewer
from ai.agents.tone_optimizer import agent as tone_optimizer
from ai.evaluation.quality import score_draft
from ai.prompts.loader import all_prompts
from ai.retrieval.context_builder import build_sources
from ai.schemas import ClaimCheck as ClaimSchema
from ai.schemas import ContextPack, Draft, PublishPackage, SourceRef
from ai.text_utils import draft_to_markdown
from backend.database.models import (AgentRun, ClaimCheck, ContentJob, ContextPackRecord, Draft as DraftRow,
                                     Profile, PromptVersion, ReviewAction)
from backend.orchestration.states import STAGE_STATUS, STAGES, assert_transition
from backend.services.audit import audit, log
from backend.services.errors import AppError


class SimulatedFailure(agent_base.AgentError):
    pass


# ---------------------------------------------------------------- helpers
def job_dict(job: ContentJob) -> dict:
    return {"id": job.id, "title": job.title, "content_type": job.content_type, "audience": job.audience,
            "product_area": job.product_area, "target_channel": job.target_channel,
            "target_length": job.target_length}


def set_status(db: Session, job: ContentJob, new: str, stage: str | None = None, actor: str | None = None,
               check: bool = True) -> None:
    if check and new != job.status:
        assert_transition(job.id, job.status, new)
    old = job.status
    job.status = new
    if stage is not None:
        job.current_stage = stage
    if new != "FAILED":
        job.last_error = None
    audit(db, "job.status_changed", actor, job.id, old=old, new=new, stage=stage)
    db.commit()


def sync_prompts(db: Session) -> None:
    for p in all_prompts():
        row = db.get(PromptVersion, p.id)
        if row is None:
            db.add(PromptVersion(id=p.id, agent=p.agent, version=p.version, file_hash=p.file_hash, body=p.body))
        elif row.file_hash != p.file_hash:
            row.file_hash, row.body = p.file_hash, p.body
    db.commit()


def latest_pack(db: Session, job_id: str) -> ContextPackRecord | None:
    return db.scalars(select(ContextPackRecord).where(ContextPackRecord.job_id == job_id)
                      .order_by(ContextPackRecord.version.desc())).first()


def latest_draft(db: Session, job_id: str) -> DraftRow | None:
    return db.scalars(select(DraftRow).where(DraftRow.job_id == job_id).order_by(DraftRow.version.desc())).first()


def sources_of(pack_row: ContextPackRecord) -> list[SourceRef]:
    return [SourceRef.model_validate(s) for s in pack_row.retrieval_json["sources"]]


def _record_run(db: Session, job: ContentJob, stage: str, result, input_payload: str) -> AgentRun:
    run = AgentRun(job_id=job.id, stage=stage, prompt_version_id=result.prompt.id, model=result.model,
                   input_hash=hashlib.sha256(input_payload.encode()).hexdigest()[:16],
                   output_json=json.loads(result.output.model_dump_json()), status="succeeded",
                   latency_ms=result.latency_ms, tokens_in=result.tokens_in, tokens_out=result.tokens_out,
                   attempt=result.attempts, finished_at=datetime.now(timezone.utc))
    db.add(run)
    db.commit()
    log.info("agent.run", job_id=job.id, stage=stage, prompt_version=result.prompt.id,
             latency_ms=result.latency_ms, tokens_in=result.tokens_in, tokens_out=result.tokens_out)
    return run


def _save_draft(db: Session, job: ContentJob, draft: Draft, stage: str, created_by: str,
                parent: DraftRow | None) -> DraftRow:
    version = (parent.version + 1) if parent else 1
    last = latest_draft(db, job.id)
    if last and last.version >= version:
        version = last.version + 1
    row = DraftRow(job_id=job.id, version=version, parent_version=parent.version if parent else None,
                   stage=stage, content_md=draft_to_markdown(draft), draft_json=json.loads(draft.model_dump_json()),
                   created_by=created_by)
    db.add(row)
    db.commit()
    return row


def _copy_claims(db: Session, src: DraftRow, dst: DraftRow) -> None:
    for c in src.claims:
        db.add(ClaimCheck(draft_id=dst.id, claim=c.claim, verdict=c.verdict, source_ids=c.source_ids, fix=c.fix,
                          resolved=c.resolved, resolved_by=c.resolved_by, resolution_note=c.resolution_note))
    db.commit()


def _busy_notice(db: Session, job: ContentJob, stage: str):
    """Show "AI service busy, retrying…" on a running job. The next set_status clears it."""
    def notify(message: str) -> None:
        job.last_error = {"code": "MODEL_BUSY", "stage": stage, "message": message, "retryable": True}
        audit(db, "workflow.model_busy", None, job.id, stage=stage, message=message)
        db.commit()
    return agent_base.busy_notifications(notify)


def _fail(db: Session, job: ContentJob, stage: str, exc: Exception) -> None:
    db.rollback()
    db.add(AgentRun(job_id=job.id, stage=stage, model="-", status="failed", error=str(exc)[:2000],
                    finished_at=datetime.now(timezone.utc)))
    job.last_error = {"code": "MODEL_FAILED", "stage": stage, "message": str(exc)[:500], "retryable": True}
    set_status(db, job, "FAILED", stage=stage, check=False)
    audit(db, "workflow.failed", None, job.id, stage=stage, error=str(exc)[:300])
    db.commit()


# ---------------------------------------------------------------- context
def prepare_context(db: Session, job: ContentJob, actor: str | None = None,
                    simulate_failure: str | None = None) -> ContextPackRecord:
    """Retrieval + Context Reader. Ends in CONTEXT_READY or NEEDS_INPUT."""
    sync_prompts(db)
    inputs = [{"kind": i.kind, "filename": i.filename, "text": i.text} for i in job.inputs]
    set_status(db, job, "CONTEXT_PREPARING", stage="context", actor=actor)
    sources, warnings = build_sources(db, job_dict(job), inputs, exclude=set(job.excluded_chunk_ids or []))
    prev = latest_pack(db, job.id)
    row = ContextPackRecord(job_id=job.id, version=(prev.version + 1) if prev else 1,
                            retrieval_json={"sources": [json.loads(s.model_dump_json()) for s in sources],
                                            "warnings": warnings})
    db.add(row)
    db.commit()
    try:
        if simulate_failure == "context":
            raise SimulatedFailure("Simulated model timeout in context stage (demo/test).")
        with _busy_notice(db, job, "context"):
            result = context_reader.run(sources, job_dict(job))
    except agent_base.AgentError as exc:
        _fail(db, job, "context", exc)
        raise AppError("MODEL_FAILED", str(exc), job.id) from exc
    pack: ContextPack = result.output
    row.pack_json = json.loads(pack.model_dump_json())
    db.commit()
    _record_run(db, job, "context", result, json.dumps([s.chunk_id for s in sources]))
    if pack.blocking_gaps:
        set_status(db, job, "NEEDS_INPUT", stage="context", actor=actor)
    else:
        set_status(db, job, "CONTEXT_READY", stage="context", actor=actor)
    return row


# ---------------------------------------------------------------- stages
def _run_stage(db: Session, job: ContentJob, stage: str, pack: ContextPack, sources: list[SourceRef],
               instructions: str, prompt_versions: dict[str, int] | None = None) -> None:
    pv = (prompt_versions or {}).get(stage)
    parent = latest_draft(db, job.id)
    jd = job_dict(job)
    if stage == "draft":
        result = documentation_writer.run(pack, sources, jd, prompt_version=pv)
        _record_run(db, job, stage, result, pack.model_dump_json())
        _save_draft(db, job, result.output, stage, "documentation_writer", parent)
        return
    if parent is None:
        raise AppError("INVALID_STATE", "No draft exists yet; run the draft stage first.", job.id)
    current = Draft.model_validate(parent.draft_json)
    if stage == "tech_review":
        result = technical_reviewer.run(current, pack, sources, prompt_version=pv)
        _record_run(db, job, stage, result, parent.content_md)
        row = _save_draft(db, job, result.output.draft, stage, "technical_reviewer", parent)
        for c in result.output.report.claims:
            db.add(ClaimCheck(draft_id=row.id, claim=c.claim, verdict=c.verdict, source_ids=c.source_ids, fix=c.fix,
                              resolved=c.verdict != "unsupported"))
        row.quality_scores = {"risk_flags": result.output.report.risk_flags,
                              "reviewer_questions": result.output.report.reviewer_questions}
        db.commit()
        return
    if stage == "tone":
        result = tone_optimizer.run(current, jd, instructions, prompt_version=pv)
    elif stage == "structure":
        result = structure_optimizer.run(current, jd, instructions, prompt_version=pv)
    else:
        raise AppError("INPUT_INVALID", f"Unknown stage {stage}", job.id)
    _record_run(db, job, stage, result, parent.content_md)
    row = _save_draft(db, job, result.output, stage, stage + "_optimizer", parent)
    row.quality_scores = parent.quality_scores
    _copy_claims(db, parent, row)


def finalize_quality(db: Session, job: ContentJob, pack: ContextPack, sources: list[SourceRef]) -> DraftRow:
    row = latest_draft(db, job.id)
    claims = [ClaimSchema(claim=c.claim, verdict=c.verdict, source_ids=c.source_ids, fix=c.fix) for c in row.claims]
    scores = score_draft(Draft.model_validate(row.draft_json), pack, sources, claims, job.content_type)
    extra = {k: v for k, v in (row.quality_scores or {}).items() if k in ("risk_flags", "reviewer_questions")}
    row.quality_scores = json.loads(scores.model_dump_json()) | extra
    db.add(AgentRun(job_id=job.id, stage="quality", model="deterministic", status="succeeded",
                    output_json=row.quality_scores, finished_at=datetime.now(timezone.utc)))
    db.commit()
    return row


def run_workflow(db: Session, job_id: str, from_stage: str = "context", stages: list[str] | None = None,
                 instructions: str = "", actor: str | None = None, simulate_failure: str | None = None,
                 prompt_versions: dict[str, int] | None = None) -> None:
    """Run (or resume) the pipeline. `stages` limits a refinement rerun to selected stages."""
    job = db.get(ContentJob, job_id)
    if job is None:
        raise AppError("NOT_FOUND", "Job not found", job_id)

    if from_stage == "context" and not stages:
        prepare_context(db, job, actor, simulate_failure)
        if job.status == "NEEDS_INPUT":
            return
        from_stage = "draft"

    pack_row = latest_pack(db, job.id)
    if pack_row is None or pack_row.pack_json is None:
        raise AppError("INVALID_STATE", "No context pack; build the context pack first.", job.id)
    pack = ContextPack.model_validate(pack_row.pack_json)
    if pack.blocking_gaps:
        raise AppError("CONTEXT_INSUFFICIENT", "Context has blocking gaps: " + "; ".join(pack.blocking_gaps),
                       job.id, {"blocking_gaps": pack.blocking_gaps})
    sources = sources_of(pack_row)
    if stages and "draft" in stages and "tech_review" not in stages:
        stages = [*stages, "tech_review"]  # a new draft must always be fact-checked again
    todo = [s for s in STAGES[1:] if (s in stages)] if stages else STAGES[STAGES.index(from_stage):]

    audit(db, "workflow.started", actor, job.id, stages=todo, instructions=instructions or None,
          prompt_versions=prompt_versions or None)
    for stage in todo:
        set_status(db, job, STAGE_STATUS[stage], stage=stage, actor=actor)
        try:
            if simulate_failure == stage:
                raise SimulatedFailure(f"Simulated model timeout in {stage} stage (demo/test).")
            with _busy_notice(db, job, stage):
                _run_stage(db, job, stage, pack, sources, instructions, prompt_versions)
        except agent_base.AgentError as exc:
            _fail(db, job, stage, exc)
            return
    finalize_quality(db, job, pack, sources)
    set_status(db, job, "IN_REVIEW", stage="review", actor=actor)
    audit(db, "workflow.completed", actor, job.id, stages=todo)
    db.commit()


# ---------------------------------------------------------------- publishing
def prepare_publish(db: Session, job: ContentJob, actor: str) -> PublishPackage:
    row = latest_draft(db, job.id)
    pack_row = latest_pack(db, job.id)
    owner = db.get(Profile, job.owner_id)
    approver_ids = db.scalars(select(ReviewAction.reviewer_id).where(
        ReviewAction.draft_id == row.id, ReviewAction.action == "approve")).all()
    approvers = [p.name for p in (db.get(Profile, a) for a in set(approver_ids)) if p]
    set_status(db, job, "PUBLISH_PREPARING", stage="publish_prep", actor=actor)
    try:
        with _busy_notice(db, job, "publish_prep"):
            result = publishing_coordinator.run(Draft.model_validate(row.draft_json), sources_of(pack_row),
                                                job_dict(job), owner.name if owner else job.owner_id, approvers)
    except agent_base.AgentError as exc:
        _fail(db, job, "publish_prep", exc)
        raise AppError("MODEL_FAILED", str(exc), job.id) from exc
    _record_run(db, job, "publish_prep", result, row.content_md)
    set_status(db, job, "PUBLISH_READY", stage="publish", actor=actor)
    return result.output
