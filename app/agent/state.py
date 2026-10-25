"""The shared notebook (state) that every node in the graph reads and writes.

Each node returns only the keys it wants to change; LangGraph merges them in.
"""
from typing import TypedDict


class FixFlowState(TypedDict, total=False):
    # Input
    complaint_id: int
    description: str  # the original complaint text
    clarification: str  # the reporter's answers to follow-up questions
    clarification_rounds: int

    # Safety (deterministic rules)
    is_safety_critical: bool
    safety_concerns: list[str]
    immediate_actions: list[str]
    escalation_notice: str

    # Classification (LLM)
    category: str
    llm_urgency: str | None
    urgency: str  # final urgency = higher of LLM and safety rules
    missing_information: list[str]
    llm_attempts: int
    llm_failed: bool
    llm_error: str | None
    triage_note: str

    # Technician matching
    technicians: list[dict]
    match_type: str
    match_attempts: int
    recommended: dict

    # Human approval
    approved: bool
    approved_by: str
    approval_notes: str
    chosen_technician_id: int
    assign_error: str | None

    # Result
    error: str | None
    outcome: str
    summary: str
