"""Access control, approval gate, secret redaction and prompt-injection handling."""
from backend.services.redaction import redact
from tests.conftest import api_job_body, auth, create_and_run, read


def test_requires_auth(client):
    r = client.get("/api/content-jobs")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"


def test_export_of_unapproved_draft_is_refused(client):
    job = create_and_run(client)
    r = client.post("/api/publish/export", json={"draft_id": job["latest_draft"]["id"], "format": "markdown"},
                    headers=auth("publisher"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_APPROVED"


def test_creator_cannot_approve_or_export(client):
    job = create_and_run(client)
    did = job["latest_draft"]["id"]
    r = client.post(f"/api/drafts/{did}/review", json={"action": "approve"}, headers=auth("creator"))
    assert r.status_code == 403
    r = client.post("/api/publish/export", json={"draft_id": did}, headers=auth("creator"))
    assert r.status_code == 403


def test_reviewer_cannot_create_jobs(client):
    r = client.post("/api/content-jobs", json=api_job_body(), headers=auth("tech_reviewer"))
    assert r.status_code == 403


def test_editing_an_approved_draft_invalidates_approval(client):
    job = create_and_run(client)
    did = job["latest_draft"]["id"]
    client.post(f"/api/drafts/{did}/review", json={"action": "approve"}, headers=auth("tech_reviewer"))
    md = job["latest_draft"]["content_md"] + "\nExtra line added after approval.\n"
    r = client.post(f"/api/drafts/{did}/review", json={"action": "edit", "content_md": md}, headers=auth("doc_lead"))
    assert r.status_code == 200 and r.json()["job_status"] == "IN_REVIEW"
    r = client.post("/api/publish/export", json={"draft_id": r.json()["new_draft_id"]}, headers=auth("publisher"))
    assert r.status_code == 403


def test_secrets_are_redacted_before_storage(client):
    body = api_job_body(inputs=[{"kind": "notes", "filename": "debug.md", "text": read("edge_cases/with_secrets.md")}])
    r = client.post("/api/content-jobs", json=body, headers=auth("creator"))
    job = client.get(f"/api/content-jobs/{r.json()['id']}", headers=auth("creator")).json()
    text = job["inputs"][0]["text"]
    assert "glpat-" not in text and "AKIA" not in text and "SuperSecret" not in text and "acme-corp" not in text
    assert job["inputs"][0]["redacted"] is True
    kinds = {f["type"] for f in job["inputs"][0]["redactions"]}
    assert {"gitlab_token", "aws_access_key", "password_assignment", "email"} <= kinds


def test_redaction_keeps_safe_text():
    text, findings = redact("Contact docs@example.com about the cache endpoint.")
    assert "docs@example.com" in text and findings == []


def test_prompt_injection_is_treated_as_data(client):
    body = {"title": "Cache hit rate in the merge request widget", "content_type": "release_note",
            "audience": "Developers", "product_area": "Create", "target_channel": "release_notes",
            "inputs": [{"kind": "notes", "filename": "notes.md", "text": read("edge_cases/prompt_injection.md")}]}
    job = create_and_run(client, body)
    assert job["status"] == "IN_REVIEW"  # never auto-approved
    md = job["latest_draft"]["content_md"].lower()
    assert "free for everyone" not in md and "developer mode" not in md
    assert any(f["type"] == "prompt_injection_suspected" for f in job["inputs"][0]["redactions"])
    assert any("prompt injection" in g.lower() for g in job["context_pack"]["pack"]["gaps"])


def test_simulate_failure_disabled_in_production(client, monkeypatch):
    from backend.config import get_settings
    job = client.post("/api/content-jobs", json=api_job_body(), headers=auth("creator")).json()
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    r = client.post("/api/agent-workflow/run", json={"job_id": job["id"], "simulate_failure": "tone"},
                    headers=auth("creator"))
    assert r.status_code == 403
