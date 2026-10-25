"""Technician lookup endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import Technician
from app.schemas import CategoryName, TechnicianOut

router = APIRouter(prefix="/technicians", tags=["Technicians"])


@router.get("", response_model=list[TechnicianOut])
def list_technicians(
    specialty: CategoryName | None = None,
    available_only: bool = False,
    db: Session = Depends(get_db),
):
    query = select(Technician).order_by(Technician.id)
    if specialty:
        query = query.where(Technician.specialty == specialty)
    if available_only:
        query = query.where(Technician.is_available.is_(True))
    return db.scalars(query).all()


@router.get("/{technician_id}", response_model=TechnicianOut)
def get_technician(technician_id: int, db: Session = Depends(get_db)):
    technician = db.get(Technician, technician_id)
    if technician is None:
        raise HTTPException(status_code=404, detail="Technician not found")
    return technician
