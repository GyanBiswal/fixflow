"""Tests for the API endpoints, including the workflow endpoints."""
import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.agent import nodes, runner
from app.agent.graph import build_graph
from app.deps import get_db
from app.main import app
from app.routes import workflow
from tests.helpers import (
    FakeClassifier,
    FlakyClassifier,
    classified,
    make_technician,
    make_unavailable,
)

COMPLAINT = {
    "reporter_name": "Test Reporter",
    "location": "Flat 204",
    "description": "Automated test: water is leaking under the kitchen sink.",
}


@pytest.fixture
def api(use_test_session, monkeypatch):
    """Returns (client, db, use_llm). Uses a fake LLM and an in-memory checkpoint store."""
    db = use_test_session
    monkeypatch.setattr(runner, "_graph", build_graph(InMemorySaver()))

    class _SessionContext:
        def __enter__(self):
            return db

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(workflow, "SessionLocal", lambda: _SessionContext())
    app.dependency_overrides[get_db] = lambda: db

    def use_llm(*results, flaky=False):
        fake = (FlakyClassifier if flaky else FakeClassifier)(*results)
        monkeypatch.setattr(nodes, "classify_complaint", fake)
        return fake

    try:
        yield TestClient(app), db, use_llm
    finally:
        app.dependency_overrides.clear()


def create_complaint(client) -> int:
    response = client.post("/complaints", json=COMPLAINT)
    assert response.status_code == 201
    return response.json()["id"]


def workflow_url(complaint_id: int, action: str = "") -> str:
    return f"/complaints/{complaint_id}/workflow{action}"


APPROVE = {"approved": True, "approved_by": "Manager Mina"}


def test_full_flow_through_the_api(api):
    client, db, use_llm = api
    use_llm(classified())
    make_unavailable(db, "plumbing")
    plumber = make_technician(db, "Plumber A", "plumbing")
    complaint_id = create_complaint(client)

    started = client.post(workflow_url(complaint_id, "/start"))
    assert started.status_code == 200
    assert started.json()["status"] == "waiting_for_approval"
    assert started.json()["waiting_for"]["recommended"]["id"] == plumber.id
    # Nobody is assigned before approval.
    assert client.get(f"/complaints/{complaint_id}").json()["status"] == "Reported"

    approved = client.post(workflow_url(complaint_id, "/approval"), json=APPROVE)
    assert approved.status_code == 200
    assert approved.json()["outcome"] == "assigned"

    detail = client.get(f"/complaints/{complaint_id}").json()
    assert detail["status"] == "Assigned"
    assert [item["new_status"] for item in detail["status_history"]] == ["Reported", "Assigned"]


def test_duplicate_complaint_returns_the_existing_one(api):
    client, _, _ = api
    first = client.post("/complaints", json=COMPLAINT)
    second = client.post("/complaints", json=COMPLAINT)
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]

    other_place = client.post("/complaints", json={**COMPLAINT, "location": "Flat 999"})
    assert other_place.status_code == 201
    assert other_place.json()["id"] != first.json()["id"]


def test_starting_the_workflow_twice_runs_it_once(api):
    client, _, use_llm = api
    fake = use_llm(classified())
    complaint_id = create_complaint(client)
    client.post(workflow_url(complaint_id, "/start"))
    second = client.post(workflow_url(complaint_id, "/start"))
    assert second.status_code == 200
    assert fake.calls == 1


def test_approving_twice_is_refused(api):
    client, db, use_llm = api
    use_llm(classified())
    make_unavailable(db, "plumbing")
    make_technician(db, "Plumber A", "plumbing")
    complaint_id = create_complaint(client)
    client.post(workflow_url(complaint_id, "/start"))

    assert client.post(workflow_url(complaint_id, "/approval"), json=APPROVE).status_code == 200
    assert client.post(workflow_url(complaint_id, "/approval"), json=APPROVE).status_code == 409


def test_approval_needs_the_approvers_name(api):
    client, _, use_llm = api
    use_llm(classified())
    complaint_id = create_complaint(client)
    client.post(workflow_url(complaint_id, "/start"))
    response = client.post(workflow_url(complaint_id, "/approval"), json={"approved": True})
    assert response.status_code == 422


def test_approval_must_be_a_real_boolean(api):
    client, _, use_llm = api
    use_llm(classified())
    complaint_id = create_complaint(client)
    client.post(workflow_url(complaint_id, "/start"))
    response = client.post(
        workflow_url(complaint_id, "/approval"),
        json={"approved": "yes", "approved_by": "Manager Mina"},
    )
    assert response.status_code == 422


def test_unknown_complaint_returns_404(api):
    client, _, _ = api
    assert client.post(workflow_url(999999999, "/start")).status_code == 404
    assert client.get(workflow_url(999999999)).status_code == 404


def test_approval_before_the_workflow_started_is_refused(api):
    client, _, _ = api
    complaint_id = create_complaint(client)
    response = client.post(workflow_url(complaint_id, "/approval"), json=APPROVE)
    assert response.status_code == 409


def test_clarification_flow_through_the_api(api):
    client, _, use_llm = api
    use_llm(classified(missing_information=["Which room?"]), classified())
    complaint_id = create_complaint(client)

    started = client.post(workflow_url(complaint_id, "/start"))
    assert started.json()["status"] == "waiting_for_clarification"
    assert started.json()["waiting_for"]["questions"] == ["Which room?"]

    answered = client.post(workflow_url(complaint_id, "/clarification"), json={"answer": "The kitchen"})
    assert answered.status_code == 200
    assert answered.json()["status"] == "waiting_for_approval"


def test_restart_after_rejection(api):
    client, db, use_llm = api
    use_llm(classified())
    make_unavailable(db, "plumbing")
    make_technician(db, "Plumber A", "plumbing")
    complaint_id = create_complaint(client)
    client.post(workflow_url(complaint_id, "/start"))

    rejected = client.post(
        workflow_url(complaint_id, "/approval"), json={"approved": False, "notes": "Not today"}
    )
    assert rejected.json()["outcome"] == "rejected"

    restarted = client.post(workflow_url(complaint_id, "/restart"))
    assert restarted.status_code == 200
    assert restarted.json()["status"] == "waiting_for_approval"

    assigned = client.post(workflow_url(complaint_id, "/approval"), json=APPROVE)
    assert assigned.json()["outcome"] == "assigned"


def test_restart_is_refused_while_the_workflow_is_waiting(api):
    client, _, use_llm = api
    use_llm(classified())
    complaint_id = create_complaint(client)
    client.post(workflow_url(complaint_id, "/start"))
    assert client.post(workflow_url(complaint_id, "/restart")).status_code == 409


def test_retry_continues_after_a_crash(api):
    client, _, use_llm = api
    use_llm(classified(), flaky=True)
    complaint_id = create_complaint(client)

    crashed = client.post(workflow_url(complaint_id, "/start"))
    assert crashed.status_code == 500
    assert client.get(workflow_url(complaint_id)).json()["status"] == "in_progress"

    retried = client.post(workflow_url(complaint_id, "/retry"))
    assert retried.status_code == 200
    assert retried.json()["status"] == "waiting_for_approval"
