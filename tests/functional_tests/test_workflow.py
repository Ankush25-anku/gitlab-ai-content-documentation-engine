"""End-to-end: intake -> context -> six agents -> review -> approve -> export."""
from tests.conftest import api_job_body, auth, create_and_run


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_full_workflow_reaches_review_with_all_stages(client):
    job = create_and_run(client)
    assert job["status"] == "IN_REVIEW", job["last_error"]
    stages = [r["stage"] for r in job["runs"]]
    assert stages == ["context", "draft", "tech_review", "tone", "structure", "quality"]
    assert all(r["status"] == "succeeded" for r in job["runs"])
    assert job["runs"][1]["prompt_version"] == "documentation_writer@v2"
    draft = job["latest_draft"]
    assert draft["version"] == 4  # draft, tech_review, tone, structure
    assert draft["quality_scores"]["structure_compliance"] == 1.0
    assert draft["quality_scores"]["citation_validity"] == 1.0
    assert "GET /projects/:id/pipelines/:pipeline_id/cache_stats" in draft["content_md"]
    assert "| `include_misses` | boolean | No |" in draft["content_md"]


def test_context_pack_endpoint_and_source_exclusion(client):
    r = client.post("/api/content-jobs", json=api_job_body(), headers=auth("creator"))
    job_id = r.json()["id"]
    r = client.post("/api/context-pack", json={"job_id": job_id}, headers=auth("creator"))
    assert r.status_code == 200, r.text
    pack = r.json()["context_pack"]
    assert r.json()["job"]["status"] == "CONTEXT_READY"
    kb = [s for s in pack["sources"] if s["origin"] == "kb"]
    assert kb and pack["sources"][0]["chunk_id"] == "job:metadata"
    excluded = kb[0]["chunk_id"]
    r = client.post("/api/context-pack", json={"job_id": job_id, "excluded_chunk_ids": [excluded]},
                    headers=auth("creator"))
    assert excluded not in [s["chunk_id"] for s in r.json()["context_pack"]["sources"]]
    assert r.json()["context_pack"]["version"] == 2


def test_rerun_only_tone_stage(client):
    job = create_and_run(client)
    draft_id = job["latest_draft"]["id"]
    r = client.post(f"/api/drafts/{draft_id}/refine", json={"stages": ["tone"], "instructions": "more concise"},
                    headers=auth("creator"))
    assert r.status_code == 202, r.text
    after = client.get(f"/api/content-jobs/{job['id']}", headers=auth("creator")).json()
    assert after["status"] == "IN_REVIEW"
    new_runs = after["runs"][len(job["runs"]):]
    assert [r["stage"] for r in new_runs] == ["tone", "quality"]  # nothing else re-executed
    assert after["latest_draft"]["version"] == job["latest_draft"]["version"] + 1


def test_version_diff(client):
    job = create_and_run(client)
    did = job["latest_draft"]["id"]
    r = client.get(f"/api/drafts/{did}/versions?compare=1,4", headers=auth("creator"))
    assert r.status_code == 200
    assert len(r.json()["versions"]) == 4
    assert r.json()["diff"].startswith("--- v1 (draft)")


def test_review_approve_and_export_markdown(client):
    job = create_and_run(client)
    did = job["latest_draft"]["id"]
    r = client.post(f"/api/drafts/{did}/review", json={"action": "approve", "comment": "Accurate."},
                    headers=auth("tech_reviewer"))
    assert r.status_code == 200, r.text
    assert r.json()["job_status"] == "APPROVED"
    r = client.post("/api/publish/export", json={"draft_id": did, "format": "markdown"}, headers=auth("publisher"))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["job_status"] == "EXPORTED"
    assert out["content"].startswith("---\ntitle: Pipeline cache statistics API")
    assert "[S1]" not in out["content"]  # internal citation markers stripped for publication
    assert out["file_path"] == "doc/api/pipeline-cache-statistics-api.md"


def test_export_cms_json_and_metrics(client):
    job = create_and_run(client)
    did = job["latest_draft"]["id"]
    client.post(f"/api/drafts/{did}/review", json={"action": "approve"}, headers=auth("doc_lead"))
    r = client.post("/api/publish/export", json={"draft_id": did, "format": "cms_json"}, headers=auth("doc_lead"))
    assert r.status_code == 200
    assert r.json()["payload"]["blocks"][0]["heading"] == "Overview"
    m = client.get("/api/metrics", headers=auth("doc_lead")).json()
    assert m["totals"]["exported"] == 1
    assert m["quality"]["avg_overall"] is not None
    assert "documentation_writer@v2" in m["quality_by_writer_prompt"]


def test_gitlab_export_without_config_fails_visibly(client):
    job = create_and_run(client)
    did = job["latest_draft"]["id"]
    client.post(f"/api/drafts/{did}/review", json={"action": "approve"}, headers=auth("tech_reviewer"))
    r = client.post("/api/publish/export", json={"draft_id": did, "format": "gitlab_mr"}, headers=auth("publisher"))
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "EXPORT_FAILED"
    assert r.json()["error"]["retryable"] is True
    job_after = client.get(f"/api/content-jobs/{job['id']}", headers=auth("publisher")).json()
    assert job_after["status"] in ("PUBLISH_READY", "APPROVED")  # approval kept, export can be retried


def test_audit_log_records_the_journey(client):
    job = create_and_run(client)
    events = [e["event"] for e in client.get(f"/api/audit-logs?job_id={job['id']}", headers=auth("doc_lead")).json()]
    for e in ("job.created", "input.added", "workflow.requested", "workflow.completed", "job.status_changed"):
        assert e in events


def test_upload_files_multipart(client):
    r = client.post("/api/content-jobs", json=api_job_body(inputs=[]), headers=auth("creator"))
    jid = r.json()["id"]
    r = client.post(f"/api/content-jobs/{jid}/inputs", headers=auth("creator"),
                    files=[("files", ("change.diff", b"diff --git a/x b/x\n+ # Adds a new cache endpoint for pipelines.\n",
                                      "text/plain"))])
    assert r.status_code == 201, r.text
    assert r.json()[0]["kind"] == "diff"
