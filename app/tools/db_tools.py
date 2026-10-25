"""Database tools. Each one opens its own session and uses the service layer (app/services.py).

Tools never raise for expected problems. They return {"ok": False, "error": "..."}.
"""
import logging

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app import services
from app.database import SessionLocal
from app.schemas import CategoryName, StatusName, UrgencyName

logger = logging.getLogger("fixflow.tools")


def _run(action):
    """Runs a database action in its own session and turns failures into error results."""
    try:
        with SessionLocal() as db:
            return {"ok": True, **action(db)}
    except services.ServiceError as error:
        return {"ok": False, "error": str(error)}
    except SQLAlchemyError as error:
        logger.error("Database error in tool: %s", error)
        return {"ok": False, "error": "Database error. Please try again later."}


def _time(value):
    return value.isoformat() if value else None


def _complaint_to_dict(complaint) -> dict:
    return {
        "id": complaint.id,
        "reporter_name": complaint.reporter_name,
        "location": complaint.location,
        "description": complaint.description,
        "category": complaint.category,
        "urgency": complaint.urgency,
        "is_safety_critical": complaint.is_safety_critical,
        "status": complaint.status,
        "created_at": _time(complaint.created_at),
    }


def _technician_to_dict(technician) -> dict:
    return {
        "id": technician.id,
        "name": technician.name,
        "specialty": technician.specialty,
        "phone": technician.phone,
        "is_available": technician.is_available,
    }


class ComplaintIdInput(BaseModel):
    complaint_id: int = Field(gt=0)


class SaveTriageInput(BaseModel):
    complaint_id: int = Field(gt=0)
    category: CategoryName
    urgency: UrgencyName
    is_safety_critical: bool = False


class FindTechniciansInput(BaseModel):
    category: CategoryName
    limit: int = Field(default=3, ge=1, le=10)


class AssignmentInput(BaseModel):
    complaint_id: int = Field(gt=0)
    technician_id: int = Field(gt=0)
    approved_by: str = Field(min_length=2, max_length=100)
    notes: str | None = Field(default=None, max_length=500)


class UpdateStatusInput(BaseModel):
    complaint_id: int = Field(gt=0)
    new_status: StatusName
    note: str | None = Field(default=None, max_length=255)


@tool(args_schema=ComplaintIdInput)
def get_complaint_details(complaint_id: int) -> dict:
    """Get a complaint's details, status history, and assigned technician by complaint ID."""

    def action(db):
        complaint = services.get_complaint_detail(db, complaint_id)
        return {
            "complaint": _complaint_to_dict(complaint),
            "status_history": [
                {
                    "old_status": item.old_status,
                    "new_status": item.new_status,
                    "note": item.note,
                    "changed_at": _time(item.changed_at),
                }
                for item in complaint.status_history
            ],
            "assignments": [
                {
                    "technician_id": item.technician_id,
                    "technician_name": item.technician.name,
                    "approved_by": item.approved_by,
                    "assigned_at": _time(item.assigned_at),
                }
                for item in complaint.assignments
            ],
        }

    return _run(action)


@tool(args_schema=SaveTriageInput)
def save_triage_result(
    complaint_id: int, category: str, urgency: str, is_safety_critical: bool = False
) -> dict:
    """Save the category, urgency, and safety flag on a complaint that is still 'Reported'."""

    def action(db):
        complaint = services.save_triage(db, complaint_id, category, urgency, is_safety_critical)
        return {"complaint": _complaint_to_dict(complaint)}

    return _run(action)


@tool(args_schema=FindTechniciansInput)
def find_available_technicians(category: str, limit: int = 3) -> dict:
    """Find available technicians for a category. Falls back to general technicians
    if no specialist is free. Technicians with fewer past jobs are listed first."""

    def action(db):
        technicians, match_type = services.find_available_technicians(db, category, limit)
        return {
            "match_type": match_type,
            "technicians": [_technician_to_dict(t) for t in technicians],
        }

    return _run(action)


@tool(args_schema=AssignmentInput)
def record_approved_assignment(
    complaint_id: int, technician_id: int, approved_by: str, notes: str | None = None
) -> dict:
    """Record a technician assignment AFTER a human has approved it. Requires the approver's name.
    Only application code may call this, and only after approval."""

    def action(db):
        assignment = services.record_assignment(db, complaint_id, technician_id, approved_by, notes)
        return {
            "assignment_id": assignment.id,
            "complaint_id": assignment.complaint_id,
            "technician_id": assignment.technician_id,
            "approved_by": assignment.approved_by,
        }

    return _run(action)


@tool(args_schema=UpdateStatusInput)
def update_complaint_status(complaint_id: int, new_status: str, note: str | None = None) -> dict:
    """Move a complaint to 'In Progress' or 'Resolved'. Cannot set 'Assigned'."""

    def action(db):
        complaint = services.update_status(db, complaint_id, new_status, note)
        return {"complaint": _complaint_to_dict(complaint)}

    return _run(action)
