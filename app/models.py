"""Database tables, written as Python classes."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import STATUS_REPORTED
from app.database import Base


class Technician(Base):
    __tablename__ = "technicians"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    specialty: Mapped[str] = mapped_column(String(30), index=True)
    phone: Mapped[str] = mapped_column(String(30))
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_name: Mapped[str] = mapped_column(String(100))
    location: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_safety_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default=STATUS_REPORTED, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    assignments: Mapped[list["Assignment"]] = relationship(back_populates="complaint")
    status_history: Mapped[list["StatusHistory"]] = relationship(back_populates="complaint")


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), index=True)
    technician_id: Mapped[int] = mapped_column(ForeignKey("technicians.id"), index=True)
    approved_by: Mapped[str] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    complaint: Mapped["Complaint"] = relationship(back_populates="assignments")
    technician: Mapped["Technician"] = relationship()


class StatusHistory(Base):
    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), index=True)
    old_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    complaint: Mapped["Complaint"] = relationship(back_populates="status_history")
