"""AI output checks: grounding, citation validity, tone, structure (deterministic in mock mode)."""
from ai.agents.technical_reviewer.agent import check_claim, mock_review
from ai.agents.tone_optimizer.agent import retone
from ai.evaluation.quality import score_draft
from ai.schemas import Draft, Section, SourceRef
from tests.conftest import auth, create_and_run

SOURCES = [
    SourceRef(id="S1", chunk_id="input:mr.md#0", origin="input", title="mr",
              text="Cache analytics is available in GitLab 18.6 for Premium and Ultimate."),
    SourceRef(id="S2", chunk_id="input:mr.md#1", origin="input", title="mr",
              text="The include_misses parameter defaults to true."),
]


def test_supported_claim():
    assert check_claim("Cache analytics is available in GitLab 18.6 for Premium and Ultimate [S1].",
                       {s.id: s for s in SOURCES}).verdict == "supported"


def test_planted_unsupported_claim_is_flagged():
    chk = check_claim("Cache analytics supports 10,000 concurrent runners on every tier.", {s.id: s for s in SOURCES})
    assert chk.verdict == "unsupported"
    assert chk.fix


def test_hallucinated_citation_is_caught():
    draft = Draft(title="t", summary="s", sections=[Section(heading="Overview",
                  body_markdown="The include_misses parameter defaults to true [S99].")])
    report = mock_review(draft, SOURCES).report
    assert report.claims[0].verdict != "supported"
    scores = score_draft(draft, None, SOURCES, report.claims, "release_note")
    assert scores.citation_validity == 0.0
    assert scores.invalid_citations == ["S99"]


def test_missing_citation_is_added_by_reviewer():
    draft = Draft(title="t", summary="s", sections=[Section(heading="Overview",
                  body_markdown="The include_misses parameter defaults to true.")])
    out = mock_review(draft, SOURCES)
    assert "[S2]" in out.draft.sections[0].body_markdown


def test_writer_v1_unsupported_claim_blocks_approval(client):
    job = create_and_run(client, prompt_versions={"draft": 1})
    draft = job["latest_draft"]
    unsupported = [c for c in draft["claims"] if c["verdict"] == "unsupported"]
    assert unsupported and "dramatically faster" in unsupported[0]["claim"]
    r = client.post(f"/api/drafts/{draft['id']}/review", json={"action": "approve"}, headers=auth("tech_reviewer"))
    assert r.status_code == 409 and r.json()["error"]["code"] == "UNSUPPORTED_CLAIMS"
    # Reviewer removes the claim; a new version is created and approval then succeeds.
    r = client.post(f"/api/drafts/{draft['id']}/review", headers=auth("tech_reviewer"),
                    json={"action": "resolve_claim", "claim_id": unsupported[0]["id"], "resolution": "remove"})
    assert r.status_code == 200, r.text
    new_id = r.json()["new_draft_id"]
    new = client.get(f"/api/drafts/{new_id}", headers=auth("tech_reviewer")).json()
    assert "dramatically faster" not in new["content_md"]
    assert new["quality_scores"]["unsupported_claims"] == 1  # still counted, but resolved
    r = client.post(f"/api/drafts/{new_id}/review", json={"action": "approve"}, headers=auth("tech_reviewer"))
    assert r.status_code == 200, r.text


def test_override_requires_justification(client):
    job = create_and_run(client, prompt_versions={"draft": 1})
    draft = job["latest_draft"]
    claim = next(c for c in draft["claims"] if c["verdict"] == "unsupported")
    r = client.post(f"/api/drafts/{draft['id']}/review", headers=auth("tech_reviewer"),
                    json={"action": "resolve_claim", "claim_id": claim["id"], "resolution": "override"})
    assert r.status_code == 422


def test_tone_keeps_citations_and_code_and_fixes_terms():
    text = "Simply open a pull request and click on `pull request` settings [S3]."
    out, changes = retone(text, "docs")
    assert "merge request" in out and "`pull request`" in out and "[S3]" in out
    assert "Simply" not in out and "select" in out
    assert changes


def test_structure_matches_template_for_every_content_type(client):
    from ai.prompts.loader import content_type_template
    for ctype, channel in (("release_note", "release_notes"), ("docs_page", "docs"), ("blog", "blog"),
                           ("onboarding_guide", "onboarding")):
        body = {"title": f"Cache analytics {ctype}", "content_type": ctype, "audience": "Developers",
                "product_area": "Verify", "target_channel": channel,
                "inputs": [{"kind": "mr", "filename": "mr.md",
                            "text": open("data/sample_inputs/pipeline_cache_analytics/mr_description.md").read()}]}
        job = create_and_run(client, body)
        assert job["status"] == "IN_REVIEW", (ctype, job["last_error"])
        headings = [s["heading"] for s in job["latest_draft"]["draft"]["sections"]]
        assert headings == content_type_template(ctype)["required_headings"]
