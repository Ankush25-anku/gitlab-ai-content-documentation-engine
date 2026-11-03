"""Central configuration. Every secret is read from environment variables only."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Runtime
    app_env: str = "development"
    log_level: str = "INFO"

    # Database: SQLite for local dev, Supabase Postgres (pgvector) in production
    database_url: str = "sqlite:///./local.db"

    # Auth: "dev" accepts demo tokens (Bearer demo:<role>), "supabase" verifies Supabase JWTs
    auth_mode: str = "dev"
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_service_role_key: str = ""

    # LLM: "mock" runs the full pipeline deterministically with no API key
    llm_provider: str = "mock"
    gemini_api_key: str = ""
    llm_model_draft: str = "gemini/gemini-flash-latest"
    llm_model_review: str = "gemini/gemini-flash-latest"
    gemini_fallback_model: str = ""  # used when the main model stays busy (503/429); empty = no fallback
    embedding_provider: str = "hash"  # "hash" (offline) or "gemini"
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768
    llm_max_retries: int = 2
    mock_latency_ms: int = 900  # mock mode only: simulated thinking time so the live workflow view is watchable

    # Retrieval
    retrieval_top_k: int = 8
    stale_after_days: int = 365

    # Publishing
    gitlab_url: str = "https://gitlab.com"
    gitlab_project_id: str = ""
    gitlab_token: str = ""
    gitlab_target_branch: str = "main"
    export_dir: str = "./exports"

    # Security
    allowed_origins: str = "http://localhost:3000"
    max_upload_mb: int = 5
    input_retention_days: int = 30

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
