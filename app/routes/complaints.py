"""Complaint endpoints. They validate input, call the service layer, and translate errors."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.deps import get_db
from app.models import Complaint
from app.schemas import (
    ComplaintCreate,
    ComplaintDetail,
    ComplaintOut,
    StatusName,
    StatusUpdate,
)

router = APIRouter(prefix="/complaints", tags=["Complaints"])


def to_http_error(error: services.ServiceError) -> HTTPException:
    """Turns a business-rule error into the right HTTP status code."""
    if isinstance(error, services.NotFoundError):
        status_code = 404
    elif isinstance(error, services.ConflictError):
        status_code = 409
    else:
        status_code = 400
    return HTTPException(status_code=status_code, detail=str(error))


@router.post("", response_model=ComplaintOut, status_code=201)
def create_complaint(data: ComplaintCreate, db: Session = Depends(get_db)):
    return services.create_complaint(db, data.reporter_name, data.location, data.description)


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
    try:
        return services.get_complaint_detail(db, complaint_id)
    except services.ServiceError as error:
        raise to_http_error(error)


@router.patch("/{complaint_id}/status", response_model=ComplaintDetail)
def update_status(complaint_id: int, data: StatusUpdate, db: Session = Depends(get_db)):
    try:
        services.update_status(db, complaint_id, data.new_status, data.note)
        return services.get_complaint_detail(db, complaint_id)
    except services.ServiceError as error:
        raise to_http_error(error)
