"""Shared fixtures: every test gets a fresh in-memory database, mock LLM and dev auth."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "sample_inputs"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")  # never call the Gemini API from tests, whatever .env says
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("MOCK_LATENCY_MS", "0")
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    monkeypatch.delenv("PROMPT_VERSION_DOCUMENTATION_WRITER", raising=False)
    from backend.config import get_settings
    from backend.database.session import reset_engine
    get_settings.cache_clear()
    reset_engine()

    from fastapi.testclient import TestClient
    from backend.main import app
    with TestClient(app) as c:
        yield c
    reset_engine()
    get_settings.cache_clear()


def auth(role: str) -> dict:
    return {"Authorization": f"Bearer demo:{role}"}


def read(rel: str) -> str:
    return (DATA / rel).read_text()


def api_job_body(**overrides) -> dict:
    body = {
        "title": "Pipeline cache statistics API", "content_type": "api_reference",
        "audience": "Developers who automate GitLab with the REST API", "product_area": "Verify",
        "target_channel": "api_reference", "target_length": 500,
        "inputs": [
            {"kind": "diff", "filename": "cache_stats.diff", "text": read("pipeline_cache_analytics/cache_stats.diff")},
            {"kind": "api_spec", "filename": "openapi_cache_stats.yaml",
             "text": read("pipeline_cache_analytics/openapi_cache_stats.yaml")},
            {"kind": "mr", "filename": "mr_description.md", "text": read("pipeline_cache_analytics/mr_description.md")},
        ],
    }
    body.update(overrides)
    return body


def create_and_run(client, body: dict | None = None, **run_kwargs) -> dict:
    r = client.post("/api/content-jobs", json=body or api_job_body(), headers=auth("creator"))
    assert r.status_code == 201, r.text
    job = r.json()
    r = client.post("/api/agent-workflow/run", json={"job_id": job["id"], **run_kwargs}, headers=auth("creator"))
    assert r.status_code == 202, r.text
    return client.get(f"/api/content-jobs/{job['id']}", headers=auth("creator")).json()
