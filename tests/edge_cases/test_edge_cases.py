"""Edge cases from the brief: incomplete, conflicting, stale, oversized inputs and model failure."""
from tests.conftest import api_job_body, auth, create_and_run, read


def test_incomplete_api_inputs_need_input(client):
    body = api_job_body(title="Runner usage API", inputs=[
        {"kind": "notes", "filename": "notes.md", "text": read("edge_cases/incomplete_api_change.md")}])
    job = create_and_run(client, body)
    assert job["status"] == "NEEDS_INPUT"
    assert any("endpoint" in g for g in job["context_pack"]["pack"]["blocking_gaps"])
    assert job["latest_draft"] is None
    # Trying to continue without new inputs is refused clearly.
    r = client.post("/api/agent-workflow/run", json={"job_id": job["id"], "from_stage": "draft"},
                    headers=auth("creator"))
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONTEXT_INSUFFICIENT"


def test_adding_inputs_resolves_needs_input(client):
    body = api_job_body(title="Cache stats API", inputs=[
        {"kind": "notes", "filename": "notes.md", "text": read("edge_cases/incomplete_api_change.md")}])
    job = create_and_run(client, body)
    assert job["status"] == "NEEDS_INPUT"
    r = client.post(f"/api/content-jobs/{job['id']}/inputs", headers=auth("creator"),
                    data={"kind": "api_spec", "filename": "openapi.yaml",
                          "text": read("pipeline_cache_analytics/openapi_cache_stats.yaml")})
    assert r.status_code == 201, r.text
    client.post("/api/agent-workflow/run", json={"job_id": job["id"]}, headers=auth("creator"))
    after = client.get(f"/api/content-jobs/{job['id']}", headers=auth("creator")).json()
    assert after["status"] == "IN_REVIEW"


def test_conflicting_notes_are_reported(client):
    body = {"title": "Cache analytics data retention", "content_type": "docs_page", "audience": "Administrators",
            "product_area": "Verify", "target_channel": "docs",
            "inputs": [{"kind": "notes", "filename": "a.md", "text": read("edge_cases/conflicting_note_a.md")},
                       {"kind": "notes", "filename": "b.md", "text": read("edge_cases/conflicting_note_b.md")}]}
    job = create_and_run(client, body)
    conflicts = job["context_pack"]["pack"]["conflicts"]
    assert conflicts and "retention_days" in conflicts[0]
    questions = job["latest_draft"]["quality_scores"]["reviewer_questions"]
    assert any("retention_days" in q for q in questions)


def test_stale_docs_are_flagged(client):
    job = create_and_run(client)
    stale = [s for s in job["context_pack"]["sources"] if s.get("stale")]
    if stale:  # the legacy analytics page is old on purpose
        assert any("stale" in w.lower() or "older" in w.lower() for w in job["context_pack"]["warnings"])


def test_oversized_input_rejected(client, monkeypatch):
    big = "x " * (3 * 1024 * 1024)
    r = client.post("/api/content-jobs", headers=auth("creator"),
                    json=api_job_body(inputs=[{"kind": "notes", "filename": "big.md", "text": big}]))
    assert r.status_code == 422 and r.json()["error"]["code"] == "INPUT_INVALID"


def test_unsupported_file_type_rejected(client):
    jid = client.post("/api/content-jobs", json=api_job_body(inputs=[]), headers=auth("creator")).json()["id"]
    r = client.post(f"/api/content-jobs/{jid}/inputs", headers=auth("creator"),
                    files=[("files", ("image.png", b"\x89PNG....", "image/png"))])
    assert r.status_code == 422


def test_invalid_job_metadata_rejected(client):
    r = client.post("/api/content-jobs", headers=auth("creator"), json={"title": "x", "content_type": "poem"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INPUT_INVALID"


def test_model_failure_preserves_state_and_allows_retry(client):
    job = create_and_run(client, simulate_failure="tone")
    assert job["status"] == "FAILED"
    assert job["last_error"]["code"] == "MODEL_FAILED" and job["last_error"]["stage"] == "tone"
    assert job["latest_draft"]["stage"] == "tech_review"  # earlier outputs kept
    # Retry resumes at the failed stage instead of starting over.
    r = client.post("/api/agent-workflow/run", json={"job_id": job["id"]}, headers=auth("creator"))
    assert r.json()["from_stage"] == "tone"
    after = client.get(f"/api/content-jobs/{job['id']}", headers=auth("creator")).json()
    assert after["status"] == "IN_REVIEW"
    assert [r["stage"] for r in after["runs"]].count("context") == 1


def test_cannot_run_without_inputs(client):
    jid = client.post("/api/content-jobs", json=api_job_body(inputs=[]), headers=auth("creator")).json()["id"]
    r = client.post("/api/agent-workflow/run", json={"job_id": jid}, headers=auth("creator"))
    assert r.status_code == 422


def test_invalid_prompt_version_rejected(client):
    jid = client.post("/api/content-jobs", json=api_job_body(), headers=auth("creator")).json()["id"]
    r = client.post("/api/agent-workflow/run", json={"job_id": jid, "prompt_versions": {"draft": 9}},
                    headers=auth("creator"))
    assert r.status_code == 422
