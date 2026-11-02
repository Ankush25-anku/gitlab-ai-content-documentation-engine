"""Turns ORM rows into API JSON."""
from backend.database.models import AgentRun, ClaimCheck, ContentJob, ContextPackRecord, Draft, JobInput
from backend.orchestration.states import STAGE_LABEL


def iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def job_summary(job: ContentJob) -> dict:
    return {
        "id": job.id, "title": job.title, "content_type": job.content_type, "audience": job.audience,
        "product_area": job.product_area, "target_channel": job.target_channel, "target_length": job.target_length,
        "owner_id": job.owner_id, "reviewer_id": job.reviewer_id, "deadline": job.deadline,
        "publication_format": job.publication_format, "status": job.status, "current_stage": job.current_stage,
        "last_error": job.last_error, "created_at": iso(job.created_at), "updated_at": iso(job.updated_at),
    }


def input_row(i: JobInput, with_text: bool = True) -> dict:
    d = {"id": i.id, "kind": i.kind, "filename": i.filename, "redacted": i.redacted, "redactions": i.redactions,
         "chars": len(i.text), "created_at": iso(i.created_at)}
    if with_text:
        d["text"] = i.text
    return d


def claim_row(c: ClaimCheck) -> dict:
    return {"id": c.id, "claim": c.claim, "verdict": c.verdict, "source_ids": c.source_ids, "fix": c.fix,
            "resolved": c.resolved, "resolved_by": c.resolved_by, "resolution_note": c.resolution_note}


def draft_row(d: Draft, with_claims: bool = True) -> dict:
    out = {"id": d.id, "job_id": d.job_id, "version": d.version, "parent_version": d.parent_version,
           "stage": d.stage, "created_by": d.created_by, "content_md": d.content_md, "draft": d.draft_json,
           "quality_scores": d.quality_scores, "review_state": d.review_state, "created_at": iso(d.created_at)}
    if with_claims:
        out["claims"] = [claim_row(c) for c in d.claims]
    return out


def run_row(r: AgentRun) -> dict:
    return {"id": r.id, "stage": r.stage, "agent": STAGE_LABEL.get(r.stage, r.stage), "status": r.status,
            "attempt": r.attempt, "model": r.model, "prompt_version": r.prompt_version_id,
            "latency_ms": r.latency_ms, "tokens_in": r.tokens_in, "tokens_out": r.tokens_out, "error": r.error,
            "output": r.output_json, "started_at": iso(r.started_at), "finished_at": iso(r.finished_at)}


def pack_row(p: ContextPackRecord | None) -> dict | None:
    if p is None:
        return None
    return {"id": p.id, "version": p.version, "sources": p.retrieval_json.get("sources", []),
            "warnings": p.retrieval_json.get("warnings", []), "pack": p.pack_json, "created_at": iso(p.created_at)}
