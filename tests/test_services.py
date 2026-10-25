"""Tests for the service layer (business rules)."""
import pytest

from app import services
from app.models import Assignment
from app.services import ConflictError, NotFoundError, ServiceError
from tests.helpers import make_complaint, make_technician, make_unavailable


def test_create_complaint_starts_reported_with_history(db_session):
    complaint = make_complaint(db_session)
    detail = services.get_complaint_detail(db_session, complaint.id)
    assert detail.status == "Reported"
    assert [h.new_status for h in detail.status_history] == ["Reported"]


def test_save_triage_sets_fields(db_session):
    complaint = make_complaint(db_session)
    saved = services.save_triage(db_session, complaint.id, "plumbing", "medium", False)
    assert saved.category == "plumbing"
    assert saved.urgency == "medium"
    assert saved.is_safety_critical is False


def test_save_triage_rejects_invalid_values(db_session):
    complaint = make_complaint(db_session)
    with pytest.raises(ServiceError):
        services.save_triage(db_session, complaint.id, "magic", "medium", False)
    with pytest.raises(ServiceError):
        services.save_triage(db_session, complaint.id, "plumbing", "whenever", False)


def test_safety_flag_is_sticky(db_session):
    complaint = make_complaint(db_session)
    services.save_triage(db_session, complaint.id, "general", "emergency", True)
    again = services.save_triage(db_session, complaint.id, "general", "emergency", False)
    assert again.is_safety_critical is True


def test_safety_critical_requires_emergency_urgency(db_session):
    complaint = make_complaint(db_session)
    with pytest.raises(ServiceError):
        services.save_triage(db_session, complaint.id, "general", "low", True)


def test_find_technicians_returns_available_specialists(db_session):
    technicians, match_type = services.find_available_technicians(db_session, "plumbing")
    assert match_type == "specialist"
    assert technicians
    assert all(t.specialty == "plumbing" and t.is_available for t in technicians)


def test_find_technicians_orders_by_workload(db_session):
    make_unavailable(db_session, "plumbing")
    busy = make_technician(db_session, "Plumber A", "plumbing")
    free = make_technician(db_session, "Plumber B", "plumbing")
    old = make_complaint(db_session)
    db_session.add(Assignment(complaint_id=old.id, technician_id=busy.id, approved_by="Manager"))
    db_session.flush()

    technicians, _ = services.find_available_technicians(db_session, "plumbing")
    assert [t.name for t in technicians] == [free.name, busy.name]


def test_find_technicians_falls_back_to_general(db_session):
    make_unavailable(db_session, "plumbing")
    make_technician(db_session, "Test General", "general")
    technicians, match_type = services.find_available_technicians(db_session, "plumbing")
    assert match_type == "general_fallback"
    assert "Test General" in [t.name for t in technicians]


def test_find_technicians_returns_none_when_nobody_available(db_session):
    make_unavailable(db_session, "plumbing")
    make_unavailable(db_session, "general")
    technicians, match_type = services.find_available_technicians(db_session, "plumbing")
    assert technicians == []
    assert match_type == "none"


def test_record_assignment_happy_path(db_session):
    technician = make_technician(db_session, "Plumber A", "plumbing")
    complaint = make_complaint(db_session, category="plumbing")

    assignment = services.record_assignment(
        db_session, complaint.id, technician.id, "Manager Mina", "Please come today"
    )
    assert assignment.approved_by == "Manager Mina"

    detail = services.get_complaint_detail(db_session, complaint.id)
    assert detail.status == "Assigned"
    assert [h.new_status for h in detail.status_history] == ["Reported", "Assigned"]
    assert len(detail.assignments) == 1
    db_session.refresh(technician)
    assert technician.is_available is False


def test_general_technician_can_cover_any_category(db_session):
    technician = make_technician(db_session, "Test General", "general")
    complaint = make_complaint(db_session, category="plumbing")
    services.record_assignment(db_session, complaint.id, technician.id, "Manager Mina")
    assert services.get_complaint_detail(db_session, complaint.id).status == "Assigned"


def test_record_assignment_requires_approver_name(db_session):
    technician = make_technician(db_session, "Plumber A", "plumbing")
    complaint = make_complaint(db_session, category="plumbing")
    with pytest.raises(ServiceError):
        services.record_assignment(db_session, complaint.id, technician.id, "  ")
    assert services.get_complaint_detail(db_session, complaint.id).status == "Reported"


def test_record_assignment_requires_triage(db_session):
    technician = make_technician(db_session, "Plumber A", "plumbing")
    complaint = make_complaint(db_session)  # no category yet
    with pytest.raises(ConflictError):
        services.record_assignment(db_session, complaint.id, technician.id, "Manager Mina")


def test_record_assignment_rejects_wrong_specialty(db_session):
    electrician = make_technician(db_session, "Electrician A", "electrical")
    complaint = make_complaint(db_session, category="plumbing")
    with pytest.raises(ConflictError):
        services.record_assignment(db_session, complaint.id, electrician.id, "Manager Mina")


def test_record_assignment_rejects_unavailable_technician(db_session):
    technician = make_technician(db_session, "Plumber A", "plumbing", available=False)
    complaint = make_complaint(db_session, category="plumbing")
    with pytest.raises(ConflictError):
        services.record_assignment(db_session, complaint.id, technician.id, "Manager Mina")


def test_cannot_assign_the_same_complaint_twice(db_session):
    first = make_technician(db_session, "Plumber A", "plumbing")
    second = make_technician(db_session, "Plumber B", "plumbing")
    complaint = make_complaint(db_session, category="plumbing")
    services.record_assignment(db_session, complaint.id, first.id, "Manager Mina")
    with pytest.raises(ConflictError):
        services.record_assignment(db_session, complaint.id, second.id, "Manager Mina")


def test_technician_cannot_take_two_complaints(db_session):
    technician = make_technician(db_session, "Plumber A", "plumbing")
    first = make_complaint(db_session, category="plumbing")
    second = make_complaint(db_session, category="plumbing")
    services.record_assignment(db_session, first.id, technician.id, "Manager Mina")
    with pytest.raises(ConflictError):
        services.record_assignment(db_session, second.id, technician.id, "Manager Mina")


def test_update_status_cannot_set_assigned(db_session):
    complaint = make_complaint(db_session)
    with pytest.raises(ConflictError):
        services.update_status(db_session, complaint.id, "Assigned")


def test_update_status_full_flow_releases_technician(db_session):
    technician = make_technician(db_session, "Plumber A", "plumbing")
    complaint = make_complaint(db_session, category="plumbing")
    services.record_assignment(db_session, complaint.id, technician.id, "Manager Mina")

    services.update_status(db_session, complaint.id, "In Progress", "On site")
    db_session.refresh(technician)
    assert technician.is_available is False

    services.update_status(db_session, complaint.id, "Resolved", "Fixed")
    db_session.refresh(technician)
    assert technician.is_available is True

    history = services.get_complaint_detail(db_session, complaint.id).status_history
    assert [h.new_status for h in history] == ["Reported", "Assigned", "In Progress", "Resolved"]


def test_update_status_rejects_skipping_steps(db_session):
    complaint = make_complaint(db_session)
    with pytest.raises(ConflictError):
        services.update_status(db_session, complaint.id, "Resolved")


def test_update_status_rejects_unknown_status(db_session):
    complaint = make_complaint(db_session)
    with pytest.raises(ServiceError):
        services.update_status(db_session, complaint.id, "Banana")


def test_unknown_complaint_raises_not_found(db_session):
    with pytest.raises(NotFoundError):
        services.get_complaint_detail(db_session, 999999999)
    with pytest.raises(NotFoundError):
        services.update_status(db_session, 999999999, "In Progress")
