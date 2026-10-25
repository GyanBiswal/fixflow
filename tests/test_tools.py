"""Tests for the LangChain tools (no LLM calls)."""
import pytest
from langchain_core.tools.base import ToolException
from pydantic import ValidationError

from app.tools import (
    ACTION_TOOLS,
    READ_ONLY_TOOLS,
    check_complaint_safety,
    db_tools,
    find_available_technicians,
    get_complaint_details,
    record_approved_assignment,
    save_triage_result,
    update_complaint_status,
)
from tests.helpers import make_complaint, make_technician, make_unavailable


@pytest.fixture
def use_test_session(db_session, monkeypatch):
    """Makes the tools use the test session (which is rolled back) instead of a real one."""

    class _SessionContext:
        def __enter__(self):
            return db_session

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(db_tools, "SessionLocal", lambda: _SessionContext())
    return db_session


def test_safety_tool_overrides_low_llm_urgency():
    result = check_complaint_safety.invoke(
        {"description": "I can smell gas in the kitchen", "llm_urgency": "low"}
    )
    assert result["ok"] is True
    assert result["is_safety_critical"] is True
    assert result["final_urgency"] == "emergency"


def test_safety_tool_keeps_llm_urgency_for_normal_complaint():
    result = check_complaint_safety.invoke(
        {"description": "The hallway light bulb needs replacing", "llm_urgency": "low"}
    )
    assert result["is_safety_critical"] is False
    assert result["final_urgency"] == "low"


def test_get_details_for_unknown_complaint_returns_error(use_test_session):
    result = get_complaint_details.invoke({"complaint_id": 999999999})
    assert result == {"ok": False, "error": "Complaint not found"}


def test_assignment_tool_rejects_blank_approver():
    with pytest.raises((ValidationError, ToolException)):
        record_approved_assignment.invoke(
            {"complaint_id": 1, "technician_id": 1, "approved_by": ""}
        )


def test_full_tool_flow(use_test_session):
    db = use_test_session
    make_unavailable(db, "plumbing")
    plumber = make_technician(db, "Plumber A", "plumbing")
    complaint = make_complaint(db, "Water is leaking under my kitchen sink")

    saved = save_triage_result.invoke(
        {"complaint_id": complaint.id, "category": "plumbing", "urgency": "medium"}
    )
    assert saved["ok"] is True

    found = find_available_technicians.invoke({"category": "plumbing"})
    assert found["ok"] is True
    assert found["match_type"] == "specialist"
    assert found["technicians"][0]["name"] == "Plumber A"

    assigned = record_approved_assignment.invoke(
        {
            "complaint_id": complaint.id,
            "technician_id": plumber.id,
            "approved_by": "Manager Mina",
        }
    )
    assert assigned["ok"] is True

    details = get_complaint_details.invoke({"complaint_id": complaint.id})
    assert details["complaint"]["status"] == "Assigned"
    assert details["assignments"][0]["technician_name"] == "Plumber A"


def test_status_tool_cannot_assign(use_test_session):
    complaint = make_complaint(use_test_session)
    result = update_complaint_status.invoke(
        {"complaint_id": complaint.id, "new_status": "Assigned"}
    )
    assert result["ok"] is False
    assert "approval workflow" in result["error"]


def test_assignment_tool_is_not_given_to_the_llm():
    read_only_names = [tool.name for tool in READ_ONLY_TOOLS]
    action_names = [tool.name for tool in ACTION_TOOLS]
    assert "record_approved_assignment" not in read_only_names
    assert "record_approved_assignment" in action_names
