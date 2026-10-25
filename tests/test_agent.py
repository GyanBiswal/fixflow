"""Tests for the LangGraph workflow.

The LLM classifier is replaced by a scripted fake. The database is real but rolled back.
"""
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import update

from app import services
from app.agent import nodes
from app.agent.graph import build_graph
from app.agent.runner import resume_workflow, start_workflow
from app.models import Technician
from tests.helpers import make_complaint, make_technician, make_unavailable


def classified(**changes):
    result = {
        "ok": True,
        "category": "plumbing",
        "urgency": "medium",
        "missing_information": [],
        "reasoning": "test",
    }
    result.update(changes)
    return result


class FakeClassifier:
    """Stands in for the LLM tool: returns prepared results in order (the last one repeats)."""

    def __init__(self, *results):
        self.results = results
        self.calls = 0

    def invoke(self, args):
        result = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return result


@pytest.fixture
def setup(use_test_session, monkeypatch):
    graph = build_graph(InMemorySaver())

    def use_llm(*results):
        fake = FakeClassifier(*results)
        monkeypatch.setattr(nodes, "classify_complaint", fake)
        return fake

    return use_test_session, graph, use_llm


def test_routine_flow_assigns_only_after_approval(setup):
    db, graph, use_llm = setup
    use_llm(classified())
    make_unavailable(db, "plumbing")
    plumber = make_technician(db, "Plumber A", "plumbing")
    complaint = make_complaint(db, "Water is leaking under my kitchen sink")

    result = start_workflow(complaint.id, graph)
    assert result["status"] == "waiting_for_approval"
    assert result["waiting_for"]["recommended"]["id"] == plumber.id
    # Nothing has been assigned yet: approval is still pending.
    assert services.get_complaint_detail(db, complaint.id).status == "Reported"
    db.refresh(plumber)
    assert plumber.is_available is True

    result = resume_workflow(complaint.id, {"approved": True, "approved_by": "Manager Mina"}, graph)
    assert result["status"] == "completed"
    assert result["outcome"] == "assigned"
    assert services.get_complaint_detail(db, complaint.id).status == "Assigned"
    db.refresh(plumber)
    assert plumber.is_available is False


def test_rejection_assigns_nobody(setup):
    db, graph, use_llm = setup
    use_llm(classified())
    make_unavailable(db, "plumbing")
    plumber = make_technician(db, "Plumber A", "plumbing")
    complaint = make_complaint(db)

    start_workflow(complaint.id, graph)
    result = resume_workflow(complaint.id, {"approved": False, "notes": "Wait until Monday"}, graph)
    assert result["outcome"] == "rejected"
    assert services.get_complaint_detail(db, complaint.id).status == "Reported"
    db.refresh(plumber)
    assert plumber.is_available is True


def test_emergency_skips_questions_and_cannot_be_downgraded(setup):
    db, graph, use_llm = setup
    # The "LLM" wrongly says low urgency and asks a question.
    use_llm(classified(category="general", urgency="low", missing_information=["Where exactly?"]))
    make_technician(db, "Test General", "general")
    complaint = make_complaint(db, "I can smell gas in the kitchen")

    result = start_workflow(complaint.id, graph)
    assert result["status"] == "waiting_for_approval"  # no clarification step was used
    payload = result["waiting_for"]
    assert payload["urgency"] == "emergency"
    assert payload["is_safety_critical"] is True
    assert payload["escalation_notice"]
    assert payload["immediate_actions"]

    saved = services.get_complaint_detail(db, complaint.id)
    assert saved.urgency == "emergency"
    assert saved.is_safety_critical is True


def test_follow_up_questions_are_asked_once(setup):
    db, graph, use_llm = setup
    use_llm(classified(missing_information=["Which room?"]), classified())
    complaint = make_complaint(db, "Something is leaking")

    result = start_workflow(complaint.id, graph)
    assert result["status"] == "waiting_for_clarification"
    assert result["waiting_for"]["questions"] == ["Which room?"]

    result = resume_workflow(complaint.id, {"answer": "The kitchen"}, graph)
    assert result["status"] == "waiting_for_approval"


def test_answer_that_reveals_danger_triggers_the_safety_rules(setup):
    db, graph, use_llm = setup
    use_llm(classified(missing_information=["Which room?"]), classified())
    complaint = make_complaint(db, "Something smells strange in my flat")

    start_workflow(complaint.id, graph)
    result = resume_workflow(complaint.id, {"answer": "There is a gas smell in the kitchen"}, graph)
    assert result["status"] == "waiting_for_approval"
    assert result["waiting_for"]["is_safety_critical"] is True
    assert result["waiting_for"]["urgency"] == "emergency"


def test_llm_failure_is_retried_then_falls_back(setup):
    db, graph, use_llm = setup
    fake = use_llm({"ok": False, "error": "boom"})
    make_technician(db, "Test General", "general")
    complaint = make_complaint(db, "The door handle fell off")

    result = start_workflow(complaint.id, graph)
    assert fake.calls == nodes.MAX_LLM_ATTEMPTS  # bounded retries
    assert result["status"] == "waiting_for_approval"
    assert result["waiting_for"]["category"] == "general"
    assert result["waiting_for"]["triage_note"]


def test_no_technician_available_ends_cleanly(setup):
    db, graph, use_llm = setup
    use_llm(classified())
    make_unavailable(db, "plumbing")
    make_unavailable(db, "general")
    complaint = make_complaint(db)

    result = start_workflow(complaint.id, graph)
    assert result["status"] == "completed"
    assert result["outcome"] == "no_technician"
    assert services.get_complaint_detail(db, complaint.id).status == "Reported"


@pytest.mark.parametrize(
    "response",
    [
        {"approved": True, "approved_by": ""},
        {"approved": True, "approved_by": "Manager Mina", "technician_id": 999999999},
        {"approved": "yes", "approved_by": "Manager Mina"},
        "garbage",
    ],
)
def test_unclear_or_invalid_approval_assigns_nobody(setup, response):
    db, graph, use_llm = setup
    use_llm(classified())
    make_unavailable(db, "plumbing")
    make_technician(db, "Plumber A", "plumbing")
    complaint = make_complaint(db)

    start_workflow(complaint.id, graph)
    result = resume_workflow(complaint.id, response, graph)
    assert result["outcome"] == "rejected"
    assert services.get_complaint_detail(db, complaint.id).status == "Reported"


def test_starting_twice_does_not_run_the_workflow_again(setup):
    db, graph, use_llm = setup
    fake = use_llm(classified())
    complaint = make_complaint(db)

    start_workflow(complaint.id, graph)
    start_workflow(complaint.id, graph)
    assert fake.calls == 1


def test_technician_taken_before_approval_triggers_a_re_match(setup):
    db, graph, use_llm = setup
    use_llm(classified())
    make_unavailable(db, "plumbing")
    first = make_technician(db, "Plumber A", "plumbing")
    second = make_technician(db, "Plumber B", "plumbing")
    complaint = make_complaint(db)

    result = start_workflow(complaint.id, graph)
    assert result["waiting_for"]["recommended"]["id"] == first.id

    # Someone else takes Plumber A before the manager answers.
    db.execute(update(Technician).where(Technician.id == first.id).values(is_available=False))

    result = resume_workflow(
        complaint.id,
        {"approved": True, "approved_by": "Manager Mina", "technician_id": first.id},
        graph,
    )
    assert result["status"] == "waiting_for_approval"  # asked again with a new recommendation
    assert result["waiting_for"]["recommended"]["id"] == second.id

    result = resume_workflow(complaint.id, {"approved": True, "approved_by": "Manager Mina"}, graph)
    assert result["outcome"] == "assigned"
    detail = services.get_complaint_detail(db, complaint.id)
    assert detail.assignments[0].technician_id == second.id
