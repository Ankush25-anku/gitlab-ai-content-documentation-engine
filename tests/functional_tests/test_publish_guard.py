"""POST /api/publish/prepare must not start a second Publishing Coordinator run while one is in flight."""
import pytest

from tests.conftest import auth, create_and_run


def _approved(client) -> tuple[str, str]:
    job = create_and_run(client)
    did = job["latest_draft"]["id"]
    r = client.post(f"/api/drafts/{did}/review", json={"action": "approve"}, headers=auth("tech_reviewer"))
    assert r.status_code == 200, r.text
    return job["id"], did


def _publish_runs(job_id: str) -> int:
    from sqlalchemy import func, select

    from backend.database.models import AgentRun
    from backend.database.session import new_session
    with new_session() as s:
        return s.scalar(select(func.count()).select_from(AgentRun)
                        .where(AgentRun.job_id == job_id, AgentRun.stage == "publish_prep"))


def test_prepare_while_preparing_returns_409(client):
    from backend.database.models import ContentJob
    from backend.database.session import new_session
    job_id, did = _approved(client)
    with new_session() as s:  # a first prepare is still running
        s.get(ContentJob, job_id).status = "PUBLISH_PREPARING"
        s.commit()
    r = client.post("/api/publish/prepare", json={"draft_id": did}, headers=auth("publisher"))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "INVALID_STATE"
    assert "already being prepared" in r.json()["error"]["message"]
    assert _publish_runs(job_id) == 0


def test_second_prepare_after_success_reuses_the_package(client):
    job_id, did = _approved(client)
    first = client.post("/api/publish/prepare", json={"draft_id": did}, headers=auth("publisher"))
    second = client.post("/api/publish/prepare", json={"draft_id": did}, headers=auth("publisher"))
    assert first.status_code == second.status_code == 200
    assert first.json()["package"] == second.json()["package"]
    assert _publish_runs(job_id) == 1


def test_only_one_of_two_racing_requests_claims_the_job(client):
    """Both requests read APPROVED before either writes: the compare-and-set lets exactly one through."""
    from backend.database.models import ContentJob
    from backend.database.session import new_session
    from backend.orchestration import runner
    from backend.services.errors import AppError
    job_id, _ = _approved(client)
    with new_session() as first, new_session() as second:
        job_a, job_b = first.get(ContentJob, job_id), second.get(ContentJob, job_id)
        assert job_a.status == job_b.status == "APPROVED"
        runner.set_status(first, job_a, "PUBLISH_PREPARING", stage="publish_prep", exclusive=True)
        with pytest.raises(AppError) as err:
            runner.set_status(second, job_b, "PUBLISH_PREPARING", stage="publish_prep", exclusive=True)
        assert err.value.code == "INVALID_STATE"
    with new_session() as s:
        assert s.get(ContentJob, job_id).status == "PUBLISH_PREPARING"
