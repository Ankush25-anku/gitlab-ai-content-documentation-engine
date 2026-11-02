"""Append-only audit trail and structured logging."""
import logging

import structlog
from sqlalchemy.orm import Session

from backend.database.models import AuditLog

structlog.configure(
    processors=[structlog.processors.add_log_level, structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)
log = structlog.get_logger("content-engine")


def audit(db: Session, event: str, actor_id: str | None = None, job_id: str | None = None, **details) -> None:
    db.add(AuditLog(actor_id=actor_id, job_id=job_id, event=event, details=details))
    log.info(event, actor_id=actor_id, job_id=job_id, **{k: v for k, v in details.items() if k != "text"})
