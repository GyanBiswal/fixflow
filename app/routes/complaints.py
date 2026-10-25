"""Complaint endpoints: create, list, retrieve, and update status."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.constants import ALLOWED_STATUS_TRANSITIONS, STATUS_ASSIGNED, STATUS_REPORTED
from app.deps import get_db
from app.models import Complaint, StatusHistory
from app.schemas import (
    ComplaintCreate,
    ComplaintDetail,
    ComplaintOut,
    StatusName,
    StatusUpdate,
)

router = APIRouter(prefix="/complaints", tags=["Complaints"])


def load_complaint_detail(db: Session, complaint_id: int) -> Complaint | None:
    """Loads a complaint together with its status history (freshly from the database)."""
    query = (
        select(Complaint)
        .options(selectinload(Complaint.status_history))
        .where(Complaint.id == complaint_id)
        .execution_options(populate_existing=True)
    )
    complaint = db.scalars(query).first()
    if complaint is not None:
        complaint.status_history.sort(key=lambda item: (item.changed_at, item.id))
    return complaint


@router.post("", response_model=ComplaintOut, status_code=201)
def create_complaint(data: ComplaintCreate, db: Session = Depends(get_db)):
    complaint = Complaint(
        reporter_name=data.reporter_name,
        location=data.location,
        description=data.description,
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
    db.commit()  # complaint and its first history row are saved together
    db.refresh(complaint)
    return complaint


@router.get("", response_model=list[ComplaintOut])
def list_complaints(
    status: StatusName | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = select(Complaint).order_by(Complaint.created_at.desc(), Complaint.id.desc())
    if status:
        query = query.where(Complaint.status == status)
    return db.scalars(query.limit(limit).offset(offset)).all()


@router.get("/{complaint_id}", response_model=ComplaintDetail)
def get_complaint(complaint_id: int, db: Session = Depends(get_db)):
    complaint = load_complaint_detail(db, complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint


@router.patch("/{complaint_id}/status", response_model=ComplaintDetail)
def update_status(complaint_id: int, data: StatusUpdate, db: Session = Depends(get_db)):
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")

    if data.new_status == STATUS_ASSIGNED:
        raise HTTPException(
            status_code=409,
            detail="Status 'Assigned' can only be set through the technician approval workflow.",
        )

    allowed = ALLOWED_STATUS_TRANSITIONS.get(complaint.status, [])
    if data.new_status not in allowed:
        allowed_text = ", ".join(allowed) if allowed else "none"
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot change status from '{complaint.status}' to "
                f"'{data.new_status}'. Allowed next status: {allowed_text}."
            ),
        )

    old_status = complaint.status
    complaint.status = data.new_status
    db.add(
        StatusHistory(
            complaint_id=complaint.id,
            old_status=old_status,
            new_status=data.new_status,
            note=data.note,
        )
    )
    db.commit()  # status change and history row are saved together
    return load_complaint_detail(db, complaint_id)
