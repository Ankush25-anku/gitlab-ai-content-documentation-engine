"""Knowledge base, prompts, audit logs, users and session info."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai.prompts.loader import content_type_template, tone_rules
from ai.retrieval.ingest import ingest_all
from ai.retrieval.knowledge import glossary_terms
from ai.retrieval.store import search
from backend.auth.deps import get_current_user, require_role
from backend.config import get_settings
from backend.database.models import AuditLog, KBChunk, KBDocument, Profile, PromptVersion
from backend.database.session import get_db
from backend.orchestration.runner import sync_prompts
from backend.services.audit import audit

router = APIRouter(prefix="/api", tags=["knowledge, prompts and admin"])
CONTENT_TYPES = ["release_note", "docs_page", "blog", "api_reference", "onboarding_guide"]
CHANNELS = ["docs", "release_notes", "blog", "api_reference", "onboarding"]


@router.get("/me")
def me(user: Profile = Depends(get_current_user)):
    s = get_settings()
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role,
            "llm_provider": s.llm_provider, "auth_mode": s.auth_mode, "app_env": s.app_env}


@router.get("/users")
def users(db: Session = Depends(get_db), user: Profile = Depends(get_current_user)):
    return [{"id": p.id, "name": p.name, "role": p.role} for p in db.scalars(select(Profile)).all()]


@router.post("/kb/ingest")
def kb_ingest(reset: bool = False, db: Session = Depends(get_db), user: Profile = Depends(require_role("admin"))):
    stats = ingest_all(db, reset=reset)
    audit(db, "kb.ingested", user.id, None, **stats)
    db.commit()
    return stats


@router.get("/kb/documents")
def kb_documents(db: Session = Depends(get_db), user: Profile = Depends(get_current_user)):
    counts = dict(db.execute(select(KBChunk.document_id, func.count()).group_by(KBChunk.document_id)).all())
    return [{"id": d.id, "title": d.title, "kind": d.kind, "product_area": d.product_area,
             "content_type": d.content_type, "owner": d.owner, "updated_at": d.updated_at,
             "source_url": d.source_url, "chunks": counts.get(d.id, 0)}
            for d in db.scalars(select(KBDocument).order_by(KBDocument.kind, KBDocument.title)).all()]


@router.get("/kb/search")
def kb_search(q: str, product_area: str | None = None, k: int = 5, db: Session = Depends(get_db),
              user: Profile = Depends(get_current_user)):
    return [h.__dict__ for h in search(db, q, top_k=min(k, 20), product_area=product_area,
                                       kinds=("doc", "style_guide", "template"))]


@router.get("/library")
def library(user: Profile = Depends(get_current_user)):
    return {
        "content_types": {t: content_type_template(t) for t in CONTENT_TYPES},
        "tone_rules": {c: tone_rules(c) for c in CHANNELS},
        "glossary": glossary_terms(),
    }


@router.get("/prompts")
def prompts(db: Session = Depends(get_db), user: Profile = Depends(get_current_user)):
    sync_prompts(db)
    return [{"id": p.id, "agent": p.agent, "version": p.version, "file_hash": p.file_hash, "body": p.body}
            for p in db.scalars(select(PromptVersion).order_by(PromptVersion.agent, PromptVersion.version)).all()]


@router.get("/audit-logs")
def audit_logs(job_id: str | None = None, limit: int = 200, db: Session = Depends(get_db),
               user: Profile = Depends(require_role("doc_lead", "tech_reviewer"))):
    q = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 1000))
    if job_id:
        q = q.where(AuditLog.job_id == job_id)
    return [{"id": a.id, "actor_id": a.actor_id, "job_id": a.job_id, "event": a.event, "details": a.details,
             "created_at": a.created_at.isoformat()} for a in db.scalars(q).all()]
