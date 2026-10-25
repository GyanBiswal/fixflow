"""Service layer: every database business rule lives here.

The API routes, the LangChain tools, and the LangGraph agent all call these
functions, so every path follows the same rules.

Locking order (prevents deadlocks): always lock the complaint first, then technicians.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.constants import (
    ALLOWED_STATUS_TRANSITIONS,
    CATEGORIES,
    STATUS_ASSIGNED,
    STATUS_REPORTED,
    STATUS_RESOLVED,
    STATUSES,
    URGENCY_LEVELS,
)
from app.models import Assignment, Complaint, StatusHistory, Technician


class ServiceError(Exception):
    """An expected business-rule problem (not a crash)."""


class NotFoundError(ServiceError):
    """The requested record does not exist."""


class ConflictError(ServiceError):
    """The request conflicts with the current state of the data."""


def _lock_complaint(db: Session, complaint_id: int) -> Complaint:
    """Loads a complaint and locks its row until the transaction ends."""
    query = (
        select(Complaint)
        .where(Complaint.id == complaint_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    complaint = db.scalars(query).first()
    if complaint is None:
        raise NotFoundError("Complaint not found")
    return complaint


def create_complaint(db: Session, reporter_name: str, location: str, description: str) -> Complaint:
    complaint = Complaint(
        reporter_name=reporter_name,
        location=location,
        description=description,
        status=STATUS_REPORTED,
    )
    db.add(complaint)
    db.flush()  # gives the complaint its ID without saving yet

    db.add(
        StatusHistory(
            complaint_id=complaint.id,
            old_status=None,
            new_status=STATUS_REPORTED,
            note="Complaint submitted",
        )
    )
    db.commit()  # complaint and first history row are saved together
    db.refresh(complaint)
    return complaint


def get_complaint_detail(db: Session, complaint_id: int) -> Complaint:
    """Loads a complaint with its status history and assignments (freshly from the database)."""
    query = (
        select(Complaint)
        .options(
            selectinload(Complaint.status_history),
            selectinload(Complaint.assignments).selectinload(Assignment.technician),
        )
        .where(Complaint.id == complaint_id)
        .execution_options(populate_existing=True)
    )
    complaint = db.scalars(query).first()
    if complaint is None:
        raise NotFoundError("Complaint not found")
    complaint.status_history.sort(key=lambda item: (item.changed_at, item.id))
    complaint.assignments.sort(key=lambda item: item.id)
    return complaint


def save_triage(
    db: Session,
    complaint_id: int,
    category: str,
    urgency: str,
    is_safety_critical: bool,
) -> Complaint:
    """Saves the classification result on a complaint that is still 'Reported'."""
    if category not in CATEGORIES:
        raise ServiceError(f"Invalid category '{category}'. Allowed: {', '.join(CATEGORIES)}.")
    if urgency not in URGENCY_LEVELS:
        raise ServiceError(f"Invalid urgency '{urgency}'. Allowed: {', '.join(URGENCY_LEVELS)}.")

    complaint = _lock_complaint(db, complaint_id)
    if complaint.status != STATUS_REPORTED:
        raise ConflictError("Triage can only be saved while the complaint is 'Reported'.")

    # A safety flag is sticky: once raised, it can never be switched off here.
    safety_flag = complaint.is_safety_critical or is_safety_critical
    if safety_flag and urgency != "emergency":
        raise ServiceError("A safety-critical complaint must have urgency 'emergency'.")

    complaint.category = category
    complaint.urgency = urgency
    complaint.is_safety_critical = safety_flag
    db.commit()
    db.refresh(complaint)
    return complaint


def find_available_technicians(
    db: Session, category: str, limit: int = 3
) -> tuple[list[Technician], str]:
    """Finds available technicians for a category.

    Returns (technicians, match_type) where match_type is
    'specialist', 'general_fallback', or 'none'.
    Technicians with fewer past assignments come first.
    """
    if category not in CATEGORIES:
        raise ServiceError(f"Invalid category '{category}'. Allowed: {', '.join(CATEGORIES)}.")

    workload = (
        select(func.count(Assignment.id))
        .where(Assignment.technician_id == Technician.id)
        .correlate(Technician)
        .scalar_subquery()
    )

    def search(specialty: str) -> list[Technician]:
        query = (
            select(Technician)
            .where(Technician.specialty == specialty, Technician.is_available.is_(True))
            .order_by(workload, Technician.id)
            .limit(limit)
        )
        return list(db.scalars(query).all())

    specialists = search(category)
    if specialists:
        return specialists, "specialist"

    if category != "general":
        generalists = search("general")
        if generalists:
            return generalists, "general_fallback"

    return [], "none"


def record_assignment(
    db: Session,
    complaint_id: int,
    technician_id: int,
    approved_by: str,
    notes: str | None = None,
) -> Assignment:
    """Records a human-approved assignment as ONE transaction.

    Callers must only use this AFTER a person has approved the assignment.
    """
    approved_by = (approved_by or "").strip()
    if len(approved_by) < 2:
        raise ServiceError("An approver name is required to assign a technician.")

    complaint = _lock_complaint(db, complaint_id)  # lock complaint first, then technician

    technician_query = (
        select(Technician)
        .where(Technician.id == technician_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    technician = db.scalars(technician_query).first()
    if technician is None:
        raise NotFoundError("Technician not found")

    if complaint.status != STATUS_REPORTED:
        raise ConflictError(
            f"Only a 'Reported' complaint can be assigned (current status: '{complaint.status}')."
        )
    if complaint.category is None:
        raise ConflictError("The complaint must be triaged (category set) before assignment.")
    if not technician.is_available:
        raise ConflictError(f"Technician {technician.name} is not available.")
    if technician.specialty not in (complaint.category, "general"):
        raise ConflictError(
            f"Technician {technician.name} ({technician.specialty}) does not match "
            f"the complaint category ({complaint.category})."
        )

    assignment = Assignment(
        complaint_id=complaint.id,
        technician_id=technician.id,
        approved_by=approved_by,
        notes=notes,
    )
    db.add(assignment)
    technician.is_available = False
    complaint.status = STATUS_ASSIGNED
    db.add(
        StatusHistory(
            complaint_id=complaint.id,
            old_status=STATUS_REPORTED,
            new_status=STATUS_ASSIGNED,
            note=f"Approved by {approved_by}; technician: {technician.name}",
        )
    )
    db.commit()  # everything above is saved together, or nothing is
    db.refresh(assignment)
    return assignment


def update_status(
    db: Session, complaint_id: int, new_status: str, note: str | None = None
) -> Complaint:
    """Moves a complaint forward (In Progress, then Resolved). Never sets 'Assigned'."""
    if new_status not in STATUSES:
        raise ServiceError(f"Unknown status '{new_status}'.")

    complaint = _lock_complaint(db, complaint_id)

    if new_status == STATUS_ASSIGNED:
        raise ConflictError(
            "Status 'Assigned' can only be set through the technician approval workflow."
        )

    allowed = ALLOWED_STATUS_TRANSITIONS.get(complaint.status, [])
    if new_status not in allowed:
        allowed_text = ", ".join(allowed) if allowed else "none"
        raise ConflictError(
            f"Cannot change status from '{complaint.status}' to "
            f"'{new_status}'. Allowed next status: {allowed_text}."
        )

    old_status = complaint.status
    complaint.status = new_status
    db.add(
        StatusHistory(
            complaint_id=complaint.id,
            old_status=old_status,
            new_status=new_status,
            note=note,
        )
    )

    if new_status == STATUS_RESOLVED:
        # The job is finished, so the technician becomes available again.
        technician_query = (
            select(Technician)
            .join(Assignment, Assignment.technician_id == Technician.id)
            .where(Assignment.complaint_id == complaint.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        for technician in db.scalars(technician_query).all():
            technician.is_available = True

    db.commit()
    db.refresh(complaint)
    return complaint
