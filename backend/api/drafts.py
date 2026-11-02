"""Drafts, version history, human review actions and stage reruns."""
import difflib
import json

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.schemas import Draft as DraftSchema
from ai.text_utils import draft_to_markdown, markdown_to_draft, remove_sentence
from backend.api.jobs import _bg_run, _check_prompt_versions, get_job_for
from backend.api.schemas import RefineRequest, ReviewRequest
from backend.api.serializers import draft_row
from backend.auth.deps import get_current_user
from backend.database.models import ClaimCheck, ContentJob, Draft, Profile, ReviewAction
from backend.database.session import get_db
from backend.orchestration import runner
from backend.orchestration.states import RUNNING
from backend.services.audit import audit
from backend.services.errors import AppError

router = APIRouter(prefix="/api/drafts", tags=["drafts and review"])
REVIEWERS = ("tech_reviewer", "doc_lead", "admin")


def _draft_and_job(db: Session, draft_id: str, user: Profile) -> tuple[Draft, ContentJob]:
    draft = db.get(Draft, draft_id)
    if draft is None:
        raise AppError("NOT_FOUND", "Draft not found.")
    job = get_job_for(db, draft.job_id, user)
    return draft, job


def _require_latest(db: Session, draft: Draft, job: ContentJob) -> None:
    latest = runner.latest_draft(db, job.id)
    if latest.id != draft.id:
        raise AppError("INVALID_STATE", f"Draft v{draft.version} is not the latest version (v{latest.version}).", job.id)


def _new_version_from(db: Session, job: ContentJob, parent: Draft, schema: DraftSchema, actor: Profile,
                      stage: str = "human_edit") -> Draft:
    row = Draft(job_id=job.id, version=runner.latest_draft(db, job.id).version + 1, parent_version=parent.version,
                stage=stage, content_md=draft_to_markdown(schema), draft_json=json.loads(schema.model_dump_json()),
                created_by=actor.id, quality_scores=parent.quality_scores)
    db.add(row)
    db.flush()
    for c in parent.claims:
        db.add(ClaimCheck(draft_id=row.id, claim=c.claim, verdict=c.verdict, source_ids=c.source_ids, fix=c.fix,
                          resolved=c.resolved, resolved_by=c.resolved_by, resolution_note=c.resolution_note))
    db.flush()
    return row


def _rescore(db: Session, job: ContentJob) -> None:
    pack_row = runner.latest_pack(db, job.id)
    from ai.schemas import ContextPack
    runner.finalize_quality(db, job, ContextPack.model_validate(pack_row.pack_json), runner.sources_of(pack_row))


@router.get("/{draft_id}")
def get_draft(draft_id: str, db: Session = Depends(get_db), user: Profile = Depends(get_current_user)):
    draft, _ = _draft_and_job(db, draft_id, user)
    reviews = db.scalars(select(ReviewAction).where(ReviewAction.draft_id == draft.id)
                         .order_by(ReviewAction.created_at)).all()
    return draft_row(draft) | {"reviews": [
        {"id": r.id, "reviewer_id": r.reviewer_id, "action": r.action, "comment": r.comment,
         "issue_category": r.issue_category, "created_at": r.created_at.isoformat()} for r in reviews]}


@router.get("/{draft_id}/versions")
def versions(draft_id: str, compare: str | None = None, db: Session = Depends(get_db),
             user: Profile = Depends(get_current_user)):
    """List versions of the draft's job. `compare=a,b` (version numbers) adds a unified diff."""
    draft, job = _draft_and_job(db, draft_id, user)
    rows = job.drafts
    out: dict = {"job_id": job.id, "versions": [
        {"id": d.id, "version": d.version, "stage": d.stage, "created_by": d.created_by,
         "review_state": d.review_state, "overall": (d.quality_scores or {}).get("overall"),
         "created_at": d.created_at.isoformat()} for d in rows]}
    if compare:
        try:
            a, b = (int(x) for x in compare.split(","))
        except ValueError as exc:
            raise AppError("INPUT_INVALID", "compare must be two version numbers, e.g. compare=2,5") from exc
        by_v = {d.version: d for d in rows}
        if a not in by_v or b not in by_v:
            raise AppError("NOT_FOUND", "Version not found.", job.id)
        out["diff"] = "".join(difflib.unified_diff(
            by_v[a].content_md.splitlines(keepends=True), by_v[b].content_md.splitlines(keepends=True),
            fromfile=f"v{a} ({by_v[a].stage})", tofile=f"v{b} ({by_v[b].stage})"))
        out["left"], out["right"] = by_v[a].content_md, by_v[b].content_md
    return out


@router.post("/{draft_id}/review")
def review(draft_id: str, body: ReviewRequest, background: BackgroundTasks, db: Session = Depends(get_db),
           user: Profile = Depends(get_current_user)):
    draft, job = _draft_and_job(db, draft_id, user)
    is_reviewer = user.role in REVIEWERS
    if body.action != "comment" and not is_reviewer and not (body.action == "edit" and user.id == job.owner_id):
        raise AppError("FORBIDDEN", f"Role '{user.role}' cannot perform '{body.action}'.", job.id)
    if job.status in RUNNING:
        raise AppError("INVALID_STATE", "Wait for the running stage to finish.", job.id)
    result: dict = {"action": body.action}

    if body.action == "comment":
        if not body.comment:
            raise AppError("INPUT_INVALID", "A comment needs text.", job.id)

    elif body.action == "edit":
        _require_latest(db, draft, job)
        if not body.content_md:
            raise AppError("INPUT_INVALID", "content_md is required for an edit.", job.id)
        edited = markdown_to_draft(body.content_md, DraftSchema.model_validate(draft.draft_json))
        new = _new_version_from(db, job, draft, edited, user)
        if job.status != "IN_REVIEW":  # an edit after approval invalidates the approval
            if job.status not in ("REVISION_REQUESTED", "FAILED"):
                runner.set_status(db, job, "REVISION_REQUESTED", actor=user.id)
            runner.set_status(db, job, "IN_REVIEW", actor=user.id)
        db.commit()
        _rescore(db, job)
        result["new_draft_id"] = new.id

    elif body.action == "resolve_claim":
        _require_latest(db, draft, job)
        claim = db.get(ClaimCheck, body.claim_id or "")
        if claim is None or claim.draft_id != draft.id:
            raise AppError("NOT_FOUND", "Claim not found on this draft.", job.id)
        if body.resolution == "override":
            if not body.comment:
                raise AppError("INPUT_INVALID", "Overriding a flagged claim requires a justification comment.", job.id)
            claim.resolved, claim.resolved_by, claim.resolution_note = True, user.id, f"Overridden: {body.comment}"
        elif body.resolution == "remove":
            schema, found = remove_sentence(DraftSchema.model_validate(draft.draft_json), claim.claim)
            if not found:
                raise AppError("INVALID_STATE", "Could not find that sentence in the draft; edit it manually.", job.id)
            new = _new_version_from(db, job, draft, schema, user, stage="claim_removed")
            for c in new.claims:
                if c.claim == claim.claim:
                    c.resolved, c.resolved_by, c.resolution_note = True, user.id, "Removed from draft"
            result["new_draft_id"] = new.id
        else:
            raise AppError("INPUT_INVALID", "resolution must be 'remove' or 'override'.", job.id)
        db.commit()
        _rescore(db, job)

    elif body.action == "request_revision":
        if job.status not in ("IN_REVIEW", "APPROVED", "PUBLISH_READY", "REJECTED"):
            raise AppError("INVALID_STATE", f"Cannot request revision while {job.status}.", job.id)
        draft.review_state = "pending"
        runner.set_status(db, job, "REVISION_REQUESTED", actor=user.id)
        if body.revision_stages:
            stages = [s for s in body.revision_stages if s != "context"]
            background.add_task(_bg_run, job.id, stages=stages, instructions=body.comment or "", actor=user.id)
            result["rerunning"] = stages

    elif body.action == "reject":
        if job.status != "IN_REVIEW":
            raise AppError("INVALID_STATE", "Only drafts in review can be rejected.", job.id)
        draft.review_state = "rejected"
        runner.set_status(db, job, "REJECTED", actor=user.id)

    elif body.action == "approve":
        _require_latest(db, draft, job)
        if job.status != "IN_REVIEW":
            raise AppError("INVALID_STATE", f"Only drafts in review can be approved (job is {job.status}).", job.id)
        open_claims = [c for c in draft.claims if c.verdict == "unsupported" and not c.resolved]
        if open_claims:
            raise AppError("UNSUPPORTED_CLAIMS",
                           f"{len(open_claims)} unsupported claim(s) must be removed or overridden before approval.",
                           job.id, {"claim_ids": [c.id for c in open_claims]})
        draft.review_state = "approved"
        runner.set_status(db, job, "APPROVED", stage="approved", actor=user.id)

    db.add(ReviewAction(draft_id=draft.id, reviewer_id=user.id, action=body.action, comment=body.comment,
                        issue_category=body.issue_category))
    audit(db, f"review.{body.action}", user.id, job.id, draft_id=draft.id, version=draft.version,
          comment=body.comment, claim_id=body.claim_id, resolution=body.resolution)
    db.commit()
    return result | {"job_status": job.status}


@router.post("/{draft_id}/refine", status_code=202)
def refine(draft_id: str, body: RefineRequest, background: BackgroundTasks, db: Session = Depends(get_db),
           user: Profile = Depends(get_current_user)):
    """Rerun selected stages (e.g. only tone) on the latest draft, without redoing earlier stages."""
    draft, job = _draft_and_job(db, draft_id, user)
    if user.id != job.owner_id and user.role not in REVIEWERS:
        raise AppError("FORBIDDEN", "Only the owner or a reviewer can rerun stages.", job.id)
    _require_latest(db, draft, job)
    if job.status in RUNNING:
        raise AppError("INVALID_STATE", "The workflow is already running.", job.id)
    if job.status not in ("IN_REVIEW", "REVISION_REQUESTED", "REJECTED", "FAILED", "APPROVED", "PUBLISH_READY",
                          "EXPORTED"):
        raise AppError("INVALID_STATE", f"Cannot refine while the job is {job.status}.", job.id)
    if job.status != "REVISION_REQUESTED" and job.status != "FAILED":
        draft.review_state = "pending"
        runner.set_status(db, job, "REVISION_REQUESTED", actor=user.id)
    audit(db, "workflow.refine_requested", user.id, job.id, stages=body.stages, instructions=body.instructions)
    db.commit()
    if body.prompt_versions:
        _check_prompt_versions(body.prompt_versions, job.id)
    background.add_task(_bg_run, job.id, stages=body.stages, instructions=body.instructions, actor=user.id,
                        prompt_versions=body.prompt_versions)
    return {"job_id": job.id, "status": "accepted", "stages": body.stages}
