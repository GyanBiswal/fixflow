"""Pydantic schemas: the shape of JSON going into and out of the API."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CategoryName = Literal["plumbing", "electrical", "cleaning", "carpentry", "general"]
StatusName = Literal["Reported", "Assigned", "In Progress", "Resolved"]


class ComplaintCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reporter_name: str = Field(min_length=2, max_length=100)
    location: str = Field(min_length=2, max_length=150)
    description: str = Field(min_length=10, max_length=2000)


class StatusUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    new_status: StatusName
    note: str | None = Field(default=None, max_length=255)


class TechnicianOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    specialty: str
    phone: str
    is_available: bool


class StatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    old_status: str | None
    new_status: str
    note: str | None
    changed_at: datetime


class ComplaintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reporter_name: str
    location: str
    description: str
    category: str | None
    urgency: str | None
    is_safety_critical: bool
    status: str
    created_at: datetime
    updated_at: datetime


class ComplaintDetail(ComplaintOut):
    status_history: list[StatusHistoryOut]

UrgencyName = Literal["low", "medium", "high", "emergency"]
