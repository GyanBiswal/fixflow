"""Workflow endpoints: start the AI workflow and answer its questions."""
from fastapi import APIRouter, HTTPException

from app.agent import runner
from app.database import SessionLocal
from app.models import Complaint
from app.workflow_schemas import ApprovalDecision, ClarificationAnswer, WorkflowResponse

router = APIRouter(prefix="/complaints/{complaint_id}/workflow", tags=["Workflow"])


def _require_complaint(complaint_id: int) -> None:
    with SessionLocal() as db:
        if db.get(Complaint, complaint_id) is None:
            raise HTTPException(status_code=404, detail="Complaint not found")


def _respond(complaint_id: int, result: dict) -> WorkflowResponse:
    """Turns a runner result into an API response or a clear HTTP error."""
    if result["status"] == "failed":
        raise HTTPException(
            status_code=500,
            detail="The workflow failed unexpectedly. You can try again with POST .../workflow/retry.",
        )
    if result["status"] == "error":
        raise HTTPException(status_code=409, detail=result["error"])
    return WorkflowResponse(
        complaint_id=complaint_id,
        status=result["status"],
        waiting_for=result.get("waiting_for"),
        outcome=result.get("outcome"),
        summary=result.get("summary"),
    )


def _require_status(complaint_id: int, expected: str) -> None:
    current = runner.describe_workflow(complaint_id)["status"]
    if current != expected:
        raise HTTPException(
            status_code=409,
            detail=f"The workflow is not waiting for this input (current status: {current}).",
        )


@router.post("/start", response_model=WorkflowResponse)
def start_workflow(complaint_id: int):
    """Runs the AI workflow. Safe to call twice: it never runs a second copy."""
    _require_complaint(complaint_id)
    return _respond(complaint_id, runner.start_workflow(complaint_id))


@router.get("", response_model=WorkflowResponse)
def get_workflow(complaint_id: int):
    _require_complaint(complaint_id)
    return _respond(complaint_id, runner.describe_workflow(complaint_id))


@router.post("/clarification", response_model=WorkflowResponse)
def answer_clarification(complaint_id: int, data: ClarificationAnswer):
    """Answers the AI's follow-up questions."""
    _require_complaint(complaint_id)
    _require_status(complaint_id, "waiting_for_clarification")
    return _respond(complaint_id, runner.resume_workflow(complaint_id, {"answer": data.answer}))


@router.post("/approval", response_model=WorkflowResponse)
def decide_approval(complaint_id: int, data: ApprovalDecision):
    """The manager approves (or rejects) the recommended technician."""
    _require_complaint(complaint_id)
    _require_status(complaint_id, "waiting_for_approval")

    decision: dict = {"approved": data.approved, "notes": data.notes}
    if data.approved:
        decision["approved_by"] = data.approved_by
        if data.technician_id is not None:
            decision["technician_id"] = data.technician_id
    return _respond(complaint_id, runner.resume_workflow(complaint_id, decision))


@router.post("/retry", response_model=WorkflowResponse)
def retry_workflow(complaint_id: int):
    """Continues a workflow that crashed part-way, from its last saved step."""
    _require_complaint(complaint_id)
    return _respond(complaint_id, runner.retry_workflow(complaint_id))


@router.post("/restart", response_model=WorkflowResponse)
def restart_workflow(complaint_id: int):
    """Starts over after a finished workflow that did not assign anyone."""
    _require_complaint(complaint_id)
    return _respond(complaint_id, runner.restart_workflow(complaint_id))
