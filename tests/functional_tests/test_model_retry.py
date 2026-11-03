"""Busy-model handling: 503/429 retries with backoff, fallback model, and the job's "AI service busy" notice."""
import httpx
import pytest

from ai.agents import base
from ai.retrieval import embeddings
from ai.schemas import Draft, Section
from tests.conftest import auth, create_and_run


class FakeGeminiError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


def _result(model: str) -> base.AgentResult:
    draft = Draft(title="T", summary="S", sections=[Section(heading="Overview", body_markdown="x [S1].")])
    return base.AgentResult(output=draft, model=model, prompt=None)


@pytest.fixture()
def sleeps(monkeypatch):
    waited: list[float] = []
    monkeypatch.setattr(base.time, "sleep", waited.append)
    return waited


def test_busy_errors_are_recognised():
    assert base._is_busy(FakeGeminiError("503 UNAVAILABLE. The model is experiencing high demand."))
    assert base._is_busy(FakeGeminiError("quota", code=429))
    wrapped = RuntimeError("call_llm_and_parse failed")
    wrapped.__cause__ = FakeGeminiError("RESOURCE_EXHAUSTED")
    assert base._is_busy(wrapped)
    assert not base._is_busy(ValueError("Invalid JSON: expected '}'"))


def test_busy_model_is_retried_with_backoff(sleeps):
    calls, notices = [], []

    def attempt(model):
        calls.append(model)
        if len(calls) < 3:
            raise FakeGeminiError("503 UNAVAILABLE", code=503)
        return _result(model)

    with base.busy_notifications(notices.append):
        result = base._call_with_retries("documentation_writer", ["gemini/main"], attempt, max_retries=2)
    assert result.model == "gemini/main" and result.attempts == 3
    assert sleeps == [2, 4]
    assert notices[0].startswith("AI service busy, retrying in 2s (retry 1 of 4)")


def test_falls_back_to_second_model_after_four_retries(sleeps):
    calls, notices = [], []

    def attempt(model):
        calls.append(model)
        if model == "gemini/main":
            raise FakeGeminiError("429 Too Many Requests", code=429)
        return _result(model)

    with base.busy_notifications(notices.append):
        result = base._call_with_retries("tone_optimizer", ["gemini/main", "gemini/lite"], attempt, max_retries=2)
    assert calls == ["gemini/main"] * 5 + ["gemini/lite"]
    assert sleeps == [2, 4, 8, 16]
    assert result.model == "gemini/lite" and result.attempts == 6
    assert "switching to backup model gemini/lite" in notices[-1]


def test_fails_clearly_when_every_model_is_busy(sleeps):
    def attempt(model):
        raise FakeGeminiError("503 UNAVAILABLE", code=503)

    with pytest.raises(base.AgentError, match="AI service busy"):
        base._call_with_retries("tone_optimizer", ["gemini/main", "gemini/lite"], attempt, max_retries=2)
    assert sleeps == [2, 4, 8, 16] * 2


def test_other_errors_keep_normal_retries_and_skip_fallback(sleeps):
    calls = []

    def attempt(model):
        calls.append(model)
        raise ValueError("Invalid JSON")

    with pytest.raises(base.AgentError, match="failed after retries"):
        base._call_with_retries("tone_optimizer", ["gemini/main", "gemini/lite"], attempt, max_retries=2)
    assert calls == ["gemini/main"] * 3


def test_fallback_model_name_gets_provider_prefix():
    assert base._with_provider("gemini-2.5-flash-lite") == "gemini/gemini-2.5-flash-lite"
    assert base._with_provider("gemini/gemini-2.5-flash-lite") == "gemini/gemini-2.5-flash-lite"


def test_job_shows_busy_notice_while_retrying_then_completes(client, monkeypatch):
    from backend.database.models import ContentJob
    from backend.database.session import new_session
    from backend.orchestration import runner
    seen = {}
    original = runner.documentation_writer.run

    def busy_then_ok(pack, sources, jd, prompt_version=None):
        base._notify_busy("AI service busy, retrying in 2s (retry 1 of 4)…")
        with new_session() as s:
            seen["last_error"] = s.get(ContentJob, jd["id"]).last_error
        return original(pack, sources, jd, prompt_version=prompt_version)

    monkeypatch.setattr(runner.documentation_writer, "run", busy_then_ok)
    job = create_and_run(client)
    assert seen["last_error"]["code"] == "MODEL_BUSY" and seen["last_error"]["stage"] == "draft"
    assert seen["last_error"]["message"].startswith("AI service busy, retrying")
    assert job["status"] == "IN_REVIEW" and job["last_error"] is None
    events = [e["event"] for e in client.get(f"/api/audit-logs?job_id={job['id']}", headers=auth("doc_lead")).json()]
    assert "workflow.model_busy" in events


# ---------------------------------------------------------------- embeddings
@pytest.fixture()
def gemini_embeddings(monkeypatch):
    """Point embeddings at a fake Gemini endpoint; returns the list of status codes it will answer with."""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("EMBEDDING_DIM", "3")
    from backend.config import get_settings
    get_settings.cache_clear()
    statuses: list[int] = []

    def fake_post(url, json, headers, timeout):
        status = statuses.pop(0) if statuses else 200
        body = {"embeddings": [{"values": [3.0, 4.0, 0.0]} for _ in json["requests"]]} if status == 200 else {}
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(embeddings.httpx, "post", fake_post)
    yield statuses
    get_settings.cache_clear()


def test_embeddings_retry_on_rate_limit(gemini_embeddings, sleeps):
    gemini_embeddings.extend([429, 503])
    assert embeddings.embed_query("cache stats") == [0.6, 0.8, 0.0]
    assert sleeps == [2, 4]


def test_embeddings_give_up_after_four_retries(gemini_embeddings, sleeps):
    gemini_embeddings.extend([429] * 5)
    with pytest.raises(httpx.HTTPStatusError):
        embeddings.embed_documents(["a", "b"])
    assert sleeps == [2, 4, 8, 16]


def test_embeddings_do_not_retry_other_errors(gemini_embeddings, sleeps):
    gemini_embeddings.append(400)
    with pytest.raises(httpx.HTTPStatusError):
        embeddings.embed_query("x")
    assert sleeps == []


@pytest.fixture()
def failing_ingest(monkeypatch):
    def busy(db):
        request = httpx.Request("POST", "https://generativelanguage.googleapis.com/")
        raise httpx.HTTPStatusError("429 Too Many Requests", request=request,
                                    response=httpx.Response(429, request=request))
    monkeypatch.setattr("ai.retrieval.ingest.ingest_all", busy)


def test_server_starts_when_startup_ingest_fails(failing_ingest, client):
    assert client.get("/health").json()["status"] == "ok"
