"""Pydantic schemas for the workflow endpoints."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


class ClarificationAnswer(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    answer: str = Field(min_length=1, max_length=500)


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    approved: StrictBool  # must be a real true/false, not "yes"
    approved_by: str | None = Field(default=None, max_length=100)
    technician_id: int | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def approver_name_required_when_approving(self):
        if self.approved and (not self.approved_by or len(self.approved_by) < 2):
            raise ValueError("approved_by (the approver's name) is required when approving")
        return self


class WorkflowResponse(BaseModel):
    complaint_id: int
    status: Literal[
        "not_started",
        "waiting_for_clarification",
        "waiting_for_approval",
        "in_progress",
        "completed",
    ]
    waiting_for: dict[str, Any] | None = None
    outcome: str | None = None
    summary: str | None = None
