"""Content jobs, inputs, context pack, workflow runs and live events."""
import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.schemas import ContextPackRequest, JobCreate, WorkflowRunRequest
from backend.api.serializers import draft_row, input_row, job_summary, pack_row, run_row
from backend.auth.deps import STAFF, can_view_job, get_current_user, require_role
from backend.config import get_settings
from backend.database.models import AgentRun, ContentJob, JobInput, Profile
from backend.database.session import get_db, new_session
from backend.orchestration import runner
from backend.orchestration.states import RUNNING
from backend.services.audit import audit
from backend.services.errors import AppError
from ai.text_utils import INJECTION_RE
from backend.services.redaction import redact

router = APIRouter(prefix="/api", tags=["content jobs"])
ALLOWED_EXT = {".md", ".txt", ".diff", ".patch", ".json", ".yaml", ".yml", ".py", ".rb", ".go", ".js", ".ts",
               ".graphql", ".rst", ".csv", ""}
KIND_BY_EXT = {".diff": "diff", ".patch": "diff", ".yaml": "api_spec", ".yml": "api_spec", ".json": "api_spec",
               ".graphql": "api_spec"}


def get_job_for(db: Session, job_id: str, user: Profile) -> ContentJob:
    job = db.get(ContentJob, job_id)
    if job is None or not can_view_job(user, job.owner_id):
        raise AppError("NOT_FOUND", "Content job not found.", job_id)
    return job


def _require_owner_or_lead(job: ContentJob, user: Profile) -> None:
    if user.id != job.owner_id and user.role not in ("doc_lead", "admin"):
        raise AppError("FORBIDDEN", "Only the job owner or a documentation lead can change this job.", job.id)


def add_input(db: Session, job: ContentJob, kind: str, filename: str, text: str, actor: Profile) -> JobInput:
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    if len(text.encode()) > max_bytes:
        raise AppError("INPUT_INVALID", f"{filename} is larger than {get_settings().max_upload_mb} MB.", job.id)
    if not text.strip():
        raise AppError("INPUT_INVALID", f"{filename} is empty.", job.id)
    clean, findings = redact(text)
    if INJECTION_RE.search(clean):
        findings.append({"type": "prompt_injection_suspected", "count": len(INJECTION_RE.findall(clean))})
    row = JobInput(job_id=job.id, kind=kind, filename=filename, text=clean, redacted=bool(findings),
                   redactions=findings)
    db.add(row)
    audit(db, "input.added", actor.id, job.id, filename=filename, kind=kind, redactions=findings)
    return row


@router.post("/content-jobs", status_code=201)
def create_job(body: JobCreate, db: Session = Depends(get_db),
               user: Profile = Depends(require_role("creator", "doc_lead"))):
    if body.reviewer_id and db.get(Profile, body.reviewer_id) is None:
        raise AppError("INPUT_INVALID", "reviewer_id does not match a user.")
    job = ContentJob(**body.model_dump(exclude={"inputs"}), owner_id=user.id)
    db.add(job)
    db.flush()
    for i in body.inputs:
        add_input(db, job, i.kind, i.filename, i.text, user)
    audit(db, "job.created", user.id, job.id, content_type=job.content_type, title=job.title)
    db.commit()
    db.refresh(job)
    return job_summary(job) | {"inputs": [input_row(i, False) for i in job.inputs]}


@router.get("/content-jobs")
def list_jobs(status: str | None = None, db: Session = Depends(get_db), user: Profile = Depends(get_current_user)):
    q = select(ContentJob).order_by(ContentJob.updated_at.desc())
    if user.role not in STAFF:
        q = q.where(ContentJob.owner_id == user.id)
    if status:
        q = q.where(ContentJob.status == status)
    return [job_summary(j) for j in db.scalars(q).all()]


@router.get("/content-jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db), user: Profile = Depends(get_current_user)):
    job = get_job_for(db, job_id, user)
    drafts = job.drafts
    runs = db.scalars(select(AgentRun).where(AgentRun.job_id == job.id).order_by(AgentRun.started_at)).all()
    owner = db.get(Profile, job.owner_id)
    return job_summary(job) | {
        "owner": {"id": owner.id, "name": owner.name} if owner else None,
        "inputs": [input_row(i) for i in job.inputs],
        "context_pack": pack_row(runner.latest_pack(db, job.id)),
        "drafts": [{"id": d.id, "version": d.version, "stage": d.stage, "created_by": d.created_by,
                    "review_state": d.review_state, "created_at": d.created_at.isoformat()} for d in drafts],
        "latest_draft": draft_row(drafts[-1]) if drafts else None,
        "runs": [run_row(r) for r in runs],
    }


@router.post("/content-jobs/{job_id}/inputs", status_code=201)
async def upload_inputs(job_id: str, files: list[UploadFile] | None = File(default=None),
                        text: str | None = Form(default=None), kind: str = Form(default="notes"),
                        filename: str = Form(default="pasted-notes.md"),
                        db: Session = Depends(get_db), user: Profile = Depends(get_current_user)):
    job = get_job_for(db, job_id, user)
    _require_owner_or_lead(job, user)
    if job.status in RUNNING:
        raise AppError("INVALID_STATE", "Wait for the running stage to finish before adding inputs.", job.id)
    added = []
    for f in files or []:
        ext = ("." + f.filename.rsplit(".", 1)[1].lower()) if "." in (f.filename or "") else ""
        if ext not in ALLOWED_EXT:
            raise AppError("INPUT_INVALID", f"Unsupported file type '{ext}'. Upload text, Markdown, diffs or specs.",
                           job.id)
        raw = await f.read()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AppError("INPUT_INVALID", f"{f.filename} is not UTF-8 text.", job.id) from exc
        added.append(add_input(db, job, KIND_BY_EXT.get(ext, kind), f.filename, content, user))
    if text:
        added.append(add_input(db, job, kind, filename, text, user))
    if not added:
        raise AppError("INPUT_INVALID", "Provide at least one file or a text input.", job.id)
    db.commit()
    return [input_row(i, False) for i in added]


@router.delete("/content-jobs/{job_id}/inputs/{input_id}", status_code=204)
def delete_input(job_id: str, input_id: str, db: Session = Depends(get_db),
                 user: Profile = Depends(get_current_user)):
    job = get_job_for(db, job_id, user)
    _require_owner_or_lead(job, user)
    row = db.get(JobInput, input_id)
    if row is None or row.job_id != job.id:
        raise AppError("NOT_FOUND", "Input not found.", job.id)
    db.delete(row)
    audit(db, "input.deleted", user.id, job.id, filename=row.filename)
    db.commit()


@router.post("/context-pack")
def build_context_pack(body: ContextPackRequest, db: Session = Depends(get_db),
                       user: Profile = Depends(get_current_user)):
    job = get_job_for(db, body.job_id, user)
    _require_owner_or_lead(job, user)
    if job.status in RUNNING:
        raise AppError("INVALID_STATE", "A stage is already running for this job.", job.id)
    if job.status not in ("INTAKE", "CONTEXT_READY", "NEEDS_INPUT", "FAILED", "REVISION_REQUESTED", "IN_REVIEW"):
        raise AppError("INVALID_STATE", f"Context cannot be rebuilt while the job is {job.status}.", job.id)
    if body.excluded_chunk_ids is not None:
        job.excluded_chunk_ids = body.excluded_chunk_ids
        audit(db, "context.sources_excluded", user.id, job.id, excluded=body.excluded_chunk_ids)
        db.commit()
    if job.status == "IN_REVIEW":
        runner.set_status(db, job, "REVISION_REQUESTED", actor=user.id)
    row = runner.prepare_context(db, job, actor=user.id)
    return {"job": job_summary(job), "context_pack": pack_row(row)}


STAGE_AGENT = {"context": "context_reader", "draft": "documentation_writer", "tech_review": "technical_reviewer",
               "tone": "tone_optimizer", "structure": "structure_optimizer"}


def _check_prompt_versions(versions: dict[str, int], job_id: str) -> None:
    from ai.prompts.loader import available_versions
    for stage, v in versions.items():
        if stage not in STAGE_AGENT or v not in available_versions(STAGE_AGENT[stage]):
            raise AppError("INPUT_INVALID", f"Prompt version {v} does not exist for stage '{stage}'.", job_id)


def _bg_run(job_id: str, **kwargs) -> None:
    with new_session() as db:
        try:
            runner.run_workflow(db, job_id, **kwargs)
        except AppError as exc:
            job = db.get(ContentJob, job_id)
            if job and job.status in RUNNING:
                job.last_error = exc.body()["error"]
                runner.set_status(db, job, "FAILED", check=False)


@router.post("/agent-workflow/run", status_code=202)
def run_workflow(body: WorkflowRunRequest, background: BackgroundTasks, db: Session = Depends(get_db),
                 user: Profile = Depends(get_current_user)):
    job = get_job_for(db, body.job_id, user)
    _require_owner_or_lead(job, user)
    if body.simulate_failure and get_settings().app_env == "production":
        raise AppError("FORBIDDEN", "simulate_failure is disabled in production.", job.id)
    if job.status in RUNNING:
        raise AppError("INVALID_STATE", "The workflow is already running.", job.id)
    if not job.inputs:
        raise AppError("INPUT_INVALID", "Add at least one input before running the workflow.", job.id)

    from_stage = body.from_stage
    if from_stage is None:
        if job.status == "FAILED" and job.current_stage in ("draft", "tech_review", "tone", "structure"):
            from_stage = job.current_stage  # resume where it failed, keeping earlier outputs
        elif job.status == "CONTEXT_READY":
            from_stage = "draft"
        else:
            from_stage = "context"
    if job.status == "NEEDS_INPUT" and from_stage != "context":
        raise AppError("CONTEXT_INSUFFICIENT", "Add the missing inputs and rebuild the context first.", job.id)
    if from_stage != "context":
        pack = runner.latest_pack(db, job.id)
        if pack is None or pack.pack_json is None:
            raise AppError("INVALID_STATE", "Build the context pack first.", job.id)
        if pack.pack_json.get("blocking_gaps"):
            raise AppError("CONTEXT_INSUFFICIENT", "Context has blocking gaps.", job.id,
                           {"blocking_gaps": pack.pack_json["blocking_gaps"]})
    if job.status in ("IN_REVIEW", "APPROVED", "PUBLISH_READY", "EXPORTED", "REJECTED"):
        runner.set_status(db, job, "REVISION_REQUESTED", actor=user.id)
    audit(db, "workflow.requested", user.id, job.id, from_stage=from_stage, simulate_failure=body.simulate_failure)
    db.commit()
    if body.prompt_versions:
        _check_prompt_versions(body.prompt_versions, job.id)
    background.add_task(_bg_run, job.id, from_stage=from_stage, actor=user.id,
                        simulate_failure=body.simulate_failure, prompt_versions=body.prompt_versions)
    return {"job_id": job.id, "status": "accepted", "from_stage": from_stage}


@router.get("/content-jobs/{job_id}/runs")
def list_runs(job_id: str, db: Session = Depends(get_db), user: Profile = Depends(get_current_user)):
    job = get_job_for(db, job_id, user)
    return [run_row(r) for r in db.scalars(select(AgentRun).where(AgentRun.job_id == job.id)
                                           .order_by(AgentRun.started_at)).all()]


@router.get("/content-jobs/{job_id}/events")
async def job_events(job_id: str, db: Session = Depends(get_db), user: Profile = Depends(get_current_user)):
    """Server-Sent Events: emits a snapshot whenever the job status or its runs change."""
    get_job_for(db, job_id, user)

    async def stream():
        last = None
        for _ in range(900):  # ~15 minutes max
            with new_session() as s:
                job = s.get(ContentJob, job_id)
                runs = s.scalars(select(AgentRun).where(AgentRun.job_id == job_id)
                                 .order_by(AgentRun.started_at)).all()
                snapshot = {"status": job.status, "current_stage": job.current_stage, "last_error": job.last_error,
                            "runs": [{k: v for k, v in run_row(r).items() if k != "output"} for r in runs]}
            payload = json.dumps(snapshot, default=str)
            if payload != last:
                yield f"event: job\ndata: {payload}\n\n"
                last = payload
            if snapshot["status"] not in RUNNING:
                yield "event: done\ndata: {}\n\n"
                return
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
