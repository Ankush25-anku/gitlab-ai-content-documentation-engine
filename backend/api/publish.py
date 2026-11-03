"""Publishing: prepare metadata (Publishing Coordinator) and export approved drafts only."""
import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.schemas import Draft as DraftSchema
from ai.schemas import PublishPackage
from backend.api.jobs import get_job_for
from backend.api.schemas import ExportRequest, PrepareRequest
from backend.auth.deps import require_role
from backend.database.models import AgentRun, Draft, Export, Profile, ReviewAction
from backend.database.session import get_db
from backend.orchestration import runner
from backend.orchestration.states import APPROVED_OR_LATER
from backend.publishing import exporters
from backend.services.audit import audit
from backend.services.errors import AppError

router = APIRouter(prefix="/api/publish", tags=["publishing"])
PUBLISHERS = ("publisher", "doc_lead")


def _approved_draft(db: Session, draft_id: str, user: Profile):
    draft = db.get(Draft, draft_id)
    if draft is None:
        raise AppError("NOT_FOUND", "Draft not found.")
    job = get_job_for(db, draft.job_id, user)
    latest = runner.latest_draft(db, job.id)
    approved = db.scalars(select(ReviewAction).where(ReviewAction.draft_id == draft.id,
                                                     ReviewAction.action == "approve")).first()
    # Enforced server-side: no export unless THIS draft version was approved by a human reviewer.
    if draft.id != latest.id or draft.review_state != "approved" or approved is None \
            or job.status not in APPROVED_OR_LATER:
        raise AppError("NOT_APPROVED", "Only the latest draft, approved by a reviewer, can be published.", job.id)
    return draft, job


def _package(db: Session, job, draft: Draft, user: Profile) -> PublishPackage:
    run = db.scalars(select(AgentRun).where(AgentRun.job_id == job.id, AgentRun.stage == "publish_prep",
                                            AgentRun.status == "succeeded")
                     .order_by(AgentRun.started_at.desc())).first()
    if run and job.status in ("PUBLISH_READY", "EXPORTED") and run.started_at >= draft.created_at:
        return PublishPackage.model_validate(run.output_json)
    if job.status == "PUBLISH_PREPARING":  # e.g. a double click; prepare_publish also guards the race itself
        raise AppError("INVALID_STATE", "Publishing metadata is already being prepared for this job. "
                       "Wait for it to finish.", job.id)
    return runner.prepare_publish(db, job, user.id)


@router.post("/prepare")
def prepare(body: PrepareRequest, db: Session = Depends(get_db),
            user: Profile = Depends(require_role(*PUBLISHERS, "tech_reviewer"))):
    draft, job = _approved_draft(db, body.draft_id, user)
    package = _package(db, job, draft, user)
    pack_row = runner.latest_pack(db, job.id)
    md = exporters.render_markdown(DraftSchema.model_validate(draft.draft_json), package,
                                   runner.sources_of(pack_row))
    return {"package": json.loads(package.model_dump_json()), "markdown_preview": md, "job_status": job.status}


@router.post("/export")
def export(body: ExportRequest, db: Session = Depends(get_db), user: Profile = Depends(require_role(*PUBLISHERS))):
    draft, job = _approved_draft(db, body.draft_id, user)
    package = _package(db, job, draft, user)
    schema = DraftSchema.model_validate(draft.draft_json)
    sources = runner.sources_of(runner.latest_pack(db, job.id))
    md = exporters.render_markdown(schema, package, sources)
    result: dict = {"format": body.format, "file_path": package.file_path}
    try:
        if body.format == "markdown":
            result["path"] = exporters.export_markdown(job.id, md, package)
            result["content"] = md
        elif body.format == "cms_json":
            result["payload"] = exporters.export_cms_json(schema, package)
        else:
            result |= exporters.export_gitlab_mr(job.id, md, package)
    except AppError as exc:
        db.add(Export(draft_id=draft.id, format=body.format, status="failed", exported_by=user.id,
                      payload={"error": exc.message}))
        audit(db, "export.failed", user.id, job.id, format=body.format, error=exc.message)
        db.commit()
        raise
    db.add(Export(draft_id=draft.id, format=body.format, target=package.file_path, mr_url=result.get("mr_url"),
                  status="succeeded", exported_by=user.id,
                  payload={k: v for k, v in result.items() if k not in ("content",)}))
    runner.set_status(db, job, "EXPORTED", stage="exported", actor=user.id)
    audit(db, "export.succeeded", user.id, job.id, format=body.format, mr_url=result.get("mr_url"),
          draft_version=draft.version)
    db.commit()
    return result | {"job_status": job.status}


@router.get("/exports")
def list_exports(db: Session = Depends(get_db), user: Profile = Depends(require_role(*PUBLISHERS, "tech_reviewer"))):
    rows = db.scalars(select(Export).order_by(Export.created_at.desc()).limit(50)).all()
    return [{"id": e.id, "draft_id": e.draft_id, "format": e.format, "target": e.target, "mr_url": e.mr_url,
             "status": e.status, "exported_by": e.exported_by, "created_at": e.created_at.isoformat()} for e in rows]
