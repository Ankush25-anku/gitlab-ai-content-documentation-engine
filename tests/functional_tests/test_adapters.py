"""Adapters tested without network: GitLab MR export (mock transport) and the CrewAI wiring."""
import json

import httpx
import pytest

from ai.schemas import Draft, FrontMatter, PublishPackage, Section


def _package() -> PublishPackage:
    front = FrontMatter(title="x", content_type="api_reference", stage="Verify", owner="Priya", last_reviewed="2026-11-03")
    return PublishPackage(slug="cache-stats", file_path="doc/api/cache-stats.md", front_matter=front,
                          mr_title="API docs: Cache stats", mr_description="desc", labels=["documentation"],
                          target_channel="api_reference", owner="Priya", approved_by=["Arjun"])


def test_gitlab_mr_export_calls_api_in_order(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "team/docs-sandbox")
    from backend.config import get_settings
    get_settings.cache_clear()
    from backend.publishing.exporters import export_gitlab_mr
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        assert request.headers["PRIVATE-TOKEN"] == "test-token"
        if request.url.path.endswith("/repository/branches"):
            return httpx.Response(201, json={"name": "b"})
        if "/repository/files/" in request.url.path:
            return httpx.Response(404, json={})
        if request.url.path.endswith("/repository/commits"):
            assert json.loads(request.content)["actions"][0]["action"] == "create"
            return httpx.Response(201, json={"id": "abc"})
        if request.url.path.endswith("/merge_requests"):
            return httpx.Response(201, json={"web_url": "https://gitlab.com/team/docs-sandbox/-/merge_requests/7",
                                             "iid": 7})
        return httpx.Response(500)

    out = export_gitlab_mr("job12345", "# md", _package(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    get_settings.cache_clear()
    assert out["mr_url"].endswith("/merge_requests/7")
    assert [c[0] for c in calls] == ["POST", "GET", "POST", "POST"]
    assert "team%2Fdocs-sandbox" in calls[0][1] or "team/docs-sandbox" in calls[0][1]


def test_crewai_wiring_builds_a_single_task_crew(monkeypatch):
    pytest.importorskip("crewai")
    monkeypatch.setenv("LLM_PROVIDER", "crewai")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    from backend.config import get_settings
    get_settings.cache_clear()
    import crewai
    from crewai.crews.crew_output import CrewOutput

    from ai.agents import base
    from ai.agents.base import AgentSpec, run_agent
    captured = {}
    expected = Draft(title="T", summary="S", sections=[Section(heading="Overview", body_markdown="x [S1].")])

    def fake_kickoff(self, inputs=None, **_):
        captured["tasks"] = self.tasks
        captured["inputs"] = inputs
        return CrewOutput(raw=expected.model_dump_json(), pydantic=expected, tasks_output=[])

    monkeypatch.setattr(crewai.Crew, "kickoff", fake_kickoff)
    spec = AgentSpec(name="tone_optimizer", stage="tone", output_model=Draft)
    result = run_agent(spec, {"target_channel": "docs", "tone_rules": "- neutral", "glossary_terms": "",
                              "draft_json": '{"a": {"b": 1}}', "instructions": "none"}, mock=lambda: None)
    get_settings.cache_clear()
    assert result.output == expected
    assert result.prompt.id == "tone_optimizer@v1"
    task = captured["tasks"][0]
    assert task.output_pydantic is Draft
    assert task.agent.max_iter == 1 and task.agent.max_retry_limit == 0  # one attempt = one request
    from crewai.hooks import get_before_llm_call_hooks
    assert base._pace_llm_call in get_before_llm_call_hooks()  # rate limiter sees every LLM request
    assert '{"a": {"b": 1}}' in task.description  # JSON braces survive (no input interpolation)
    assert captured["inputs"] is None
