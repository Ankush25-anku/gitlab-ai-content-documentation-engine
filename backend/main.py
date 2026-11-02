"""FastAPI application entry point.

Run locally:  uvicorn backend.main:app --reload
API docs:     http://localhost:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from backend.api import admin, drafts, jobs, metrics, publish
from backend.auth.deps import ensure_demo_users
from backend.config import get_settings
from backend.database.models import KBChunk
from backend.database.session import init_db, new_session
from backend.orchestration.runner import sync_prompts
from backend.services.errors import AppError, app_error_handler


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.app_env == "production" and settings.auth_mode == "dev":
        raise RuntimeError("Refusing to start: AUTH_MODE=dev is not allowed when APP_ENV=production.")
    init_db()
    with new_session() as db:
        sync_prompts(db)
        if settings.auth_mode == "dev":
            ensure_demo_users(db)
        if db.scalar(select(func.count()).select_from(KBChunk)) == 0:
            from ai.retrieval.ingest import ingest_all
            ingest_all(db)
    yield


app = FastAPI(
    title="GitLab AI Content & Documentation Engine",
    version="0.1.0",
    description="Governed multi-agent pipeline that turns technical change into review-ready content.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.add_exception_handler(AppError, app_error_handler)


@app.exception_handler(RequestValidationError)
async def validation_handler(_, exc: RequestValidationError):
    errors = [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": {
        "code": "INPUT_INVALID", "message": "Request validation failed.", "job_id": None, "retryable": False,
        "details": {"errors": errors}}})


for r in (jobs.router, drafts.router, publish.router, metrics.router, admin.router):
    app.include_router(r)


@app.get("/health", tags=["health"])
def health():
    s = get_settings()
    return {"status": "ok", "llm_provider": s.llm_provider, "auth_mode": s.auth_mode}
