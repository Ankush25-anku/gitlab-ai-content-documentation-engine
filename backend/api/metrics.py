"""Operations metrics for the Publishing Dashboard."""
from collections import Counter, defaultdict
from statistics import mean

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth.deps import get_current_user
from backend.database.models import AgentRun, AuditLog, ContentJob, Draft, Export, Profile, ReviewAction
from backend.database.session import get_db

router = APIRouter(prefix="/api", tags=["metrics"])
REVIEW_OR_LATER = {"IN_REVIEW", "APPROVED", "PUBLISH_PREPARING", "PUBLISH_READY", "EXPORTED", "REVISION_REQUESTED",
                   "REJECTED"}


def _week(dt) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def _avg(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(mean(values), 3) if values else None


@router.get("/metrics")
def metrics(db: Session = Depends(get_db), user: Profile = Depends(get_current_user)):
    jobs = db.scalars(select(ContentJob)).all()
    runs = db.scalars(select(AgentRun)).all()
    drafts = db.scalars(select(Draft)).all()
    reviews = db.scalars(select(ReviewAction)).all()
    exports = [e for e in db.scalars(select(Export)).all() if e.status == "succeeded"]
    events = db.scalars(select(AuditLog).where(AuditLog.event == "job.status_changed")).all()

    by_status = Counter(j.status for j in jobs)
    latest_by_job: dict[str, Draft] = {}
    for d in drafts:
        if d.job_id not in latest_by_job or d.version > latest_by_job[d.job_id].version:
            latest_by_job[d.job_id] = d
    reviewed_jobs = [j for j in jobs if j.status in REVIEW_OR_LATER]

    # Rework: jobs that needed at least one revision request or rerun after first review.
    revised = {e.job_id for e in events if (e.details or {}).get("new") == "REVISION_REQUESTED"}
    rework_rate = len(revised & {j.id for j in reviewed_jobs}) / len(reviewed_jobs) if reviewed_jobs else 0.0

    # Approval cycle time: first IN_REVIEW -> first APPROVED, per job (hours).
    first: dict[tuple[str, str], object] = {}
    for e in sorted(events, key=lambda e: e.created_at):
        key = (e.job_id, (e.details or {}).get("new"))
        first.setdefault(key, e.created_at)
    cycle = [(first[(j.id, "APPROVED")] - first[(j.id, "IN_REVIEW")]).total_seconds() / 3600
             for j in jobs if (j.id, "APPROVED") in first and (j.id, "IN_REVIEW") in first]
    # Draft generation time: job creation -> first IN_REVIEW (minutes).
    gen = [(first[(j.id, "IN_REVIEW")] - j.created_at.replace(tzinfo=first[(j.id, "IN_REVIEW")].tzinfo))
           .total_seconds() / 60 for j in jobs if (j.id, "IN_REVIEW") in first]

    stage_stats = defaultdict(list)
    for r in runs:
        if r.status == "succeeded" and r.stage not in ("quality",):
            stage_stats[r.stage].append(r.latency_ms)
    failed = [r for r in runs if r.status == "failed"]

    scores = [d.quality_scores for d in latest_by_job.values() if d.quality_scores and "overall" in d.quality_scores]

    # Prompt version comparison: final quality by writer prompt version.
    writer_version: dict[str, str] = {}
    for r in sorted(runs, key=lambda r: r.started_at):
        if r.stage == "draft" and r.status == "succeeded":
            writer_version[r.job_id] = r.prompt_version_id
    by_prompt = defaultdict(list)
    for job_id, pv in writer_version.items():
        d = latest_by_job.get(job_id)
        if d and d.quality_scores and "overall" in d.quality_scores:
            by_prompt[pv].append(d.quality_scores)

    weekly = defaultdict(lambda: {"created": 0, "in_review": 0, "exported": 0})
    for j in jobs:
        weekly[_week(j.created_at)]["created"] += 1
    for (job_id, status), at in first.items():
        if status == "IN_REVIEW":
            weekly[_week(at)]["in_review"] += 1
    for e in exports:
        weekly[_week(e.created_at)]["exported"] += 1

    return {
        "totals": {
            "jobs": len(jobs), "drafts_generated": sum(1 for d in drafts if d.stage == "draft"),
            "in_review": by_status.get("IN_REVIEW", 0), "approved": sum(by_status.get(s, 0) for s in
                                                                          ("APPROVED", "PUBLISH_READY")),
            "exported": by_status.get("EXPORTED", 0), "failed": by_status.get("FAILED", 0),
            "needs_input": by_status.get("NEEDS_INPUT", 0),
            "backlog": sum(by_status.get(s, 0) for s in ("INTAKE", "CONTEXT_READY", "NEEDS_INPUT",
                                                         "REVISION_REQUESTED", "IN_REVIEW", "FAILED")),
        },
        "jobs_by_status": dict(by_status),
        "rework_rate": round(rework_rate, 3),
        "avg_approval_cycle_hours": _avg(cycle),
        "avg_time_to_first_draft_minutes": _avg(gen),
        "avg_revision_requests_per_job": round(sum(1 for r in reviews if r.action == "request_revision")
                                               / max(1, len(reviewed_jobs)), 2),
        "stage_latency_ms": {k: {"avg": int(mean(v)), "runs": len(v)} for k, v in stage_stats.items()},
        "model_error_rate": round(len(failed) / max(1, len(runs)), 3),
        "tokens": {"in": sum(r.tokens_in for r in runs), "out": sum(r.tokens_out for r in runs)},
        "quality": {
            "avg_overall": _avg(s.get("overall") for s in scores),
            "avg_claim_support_rate": _avg(s.get("claim_support_rate") for s in scores),
            "avg_citation_validity": _avg(s.get("citation_validity") for s in scores),
            "avg_source_coverage": _avg(s.get("source_coverage") for s in scores),
            "avg_unsupported_claims": _avg(s.get("unsupported_claims") for s in scores),
        },
        "quality_by_writer_prompt": {pv: {"jobs": len(v), "avg_overall": _avg(s.get("overall") for s in v),
                                          "avg_unsupported_claims": _avg(s.get("unsupported_claims") for s in v)}
                                     for pv, v in by_prompt.items()},
        "review_issue_categories": dict(Counter(r.issue_category for r in reviews if r.issue_category)),
        "weekly_throughput": [{"week": w, **v} for w, v in sorted(weekly.items())],
        "recent_exports": [{"draft_id": e.draft_id, "format": e.format, "target": e.target, "mr_url": e.mr_url,
                            "created_at": e.created_at.isoformat()} for e in
                           sorted(exports, key=lambda e: e.created_at, reverse=True)[:10]],
    }
