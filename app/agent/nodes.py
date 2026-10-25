"""The steps (nodes) of the FixFlow graph, plus the routing functions that choose the next step.

Rules for this file:
- Nodes call TOOLS. Tools call the service layer. Nodes never touch the database directly.
- Code BEFORE an interrupt() runs again when the workflow resumes, so we never write to the
  database before an interrupt().
"""
import logging

from langgraph.types import interrupt

from app.tools import (
    check_complaint_safety,
    classify_complaint,
    find_available_technicians,
    get_complaint_details,
    record_approved_assignment,
    save_triage_result,
)

logger = logging.getLogger("fixflow.agent")

MAX_LLM_ATTEMPTS = 2  # tries per classification round
MAX_MATCH_ATTEMPTS = 2  # times we look for a technician (a re-match happens if one was taken)
MAX_CLARIFICATION_ROUNDS = 1  # we ask follow-up questions at most once


# ---------------------------------------------------------------- helpers
def _call(tool, args: dict) -> dict:
    """Calls a tool. Retries once if it hit a temporary database error."""
    result = tool.invoke(args)
    if not result.get("ok") and "Database error" in str(result.get("error", "")):
        result = tool.invoke(args)
    return result


def _full_text(state) -> str:
    """The complaint text plus any extra information the reporter gave us."""
    text = state["description"]
    if state.get("clarification"):
        text += "\n\nAdditional information from the reporter:\n" + state["clarification"]
    return text


# ---------------------------------------------------------------- nodes
def load_complaint(state):
    result = _call(get_complaint_details, {"complaint_id": state["complaint_id"]})
    if not result["ok"]:
        return {"outcome": "error", "error": result["error"]}

    complaint = result["complaint"]
    if complaint["status"] != "Reported":
        return {
            "outcome": "invalid_state",
            "error": f"Complaint is already '{complaint['status']}'.",
        }

    return {
        "description": complaint["description"],
        "clarification": "",
        "clarification_rounds": 0,
        "llm_attempts": 0,
        "match_attempts": 0,
        "error": None,
    }


def safety_check(state):
    """Deterministic safety rules. Runs BEFORE the LLM so an LLM failure can never hide a danger."""
    result = check_complaint_safety.invoke({"description": _full_text(state)})
    return {
        "is_safety_critical": result["is_safety_critical"],
        "safety_concerns": result["concerns"],
        "immediate_actions": result["immediate_actions"],
    }


def classify(state):
    attempts = state.get("llm_attempts", 0) + 1
    result = classify_complaint.invoke({"description": _full_text(state)})
    if not result["ok"]:
        logger.warning("Classification attempt %s failed: %s", attempts, result["error"])
        return {"llm_attempts": attempts, "llm_failed": True, "llm_error": result["error"]}
    return {
        "llm_attempts": attempts,
        "llm_failed": False,
        "llm_error": None,
        "category": result["category"],
        "llm_urgency": result["urgency"],
        "missing_information": result["missing_information"],
    }


def ask_missing_info(state):
    """Pauses the workflow and asks the reporter follow-up questions."""
    answer = interrupt(
        {
            "type": "clarification",
            "complaint_id": state["complaint_id"],
            "questions": state["missing_information"],
        }
    )
    text = answer.get("answer") if isinstance(answer, dict) else answer
    text = str(text or "").strip()[:500]
    return {
        "clarification": text,
        "clarification_rounds": state.get("clarification_rounds", 0) + 1,
        "llm_attempts": 0,
        "missing_information": [],
    }


def fallback_triage(state):
    """Used when the LLM keeps failing. Safe defaults; the safety rules still apply."""
    return {
        "category": "general",
        "llm_urgency": None,
        "missing_information": [],
        "triage_note": "AI classification was unavailable. Category set to 'general' with default "
        "urgency. Please review before approving.",
    }


def save_triage(state):
    """Final urgency = the HIGHER of the LLM's urgency and the safety rules' minimum."""
    safety = check_complaint_safety.invoke(
        {"description": _full_text(state), "llm_urgency": state.get("llm_urgency")}
    )
    saved = _call(
        save_triage_result,
        {
            "complaint_id": state["complaint_id"],
            "category": state["category"],
            "urgency": safety["final_urgency"],
            "is_safety_critical": safety["is_safety_critical"],
        },
    )
    if not saved["ok"]:
        return {"outcome": "error", "error": saved["error"]}
    return {"urgency": safety["final_urgency"], "is_safety_critical": safety["is_safety_critical"]}


def escalate_emergency(state):
    """Emergency branch. In a real system this would page the on-call manager (SMS, call, email).
    Here we log it and show the notice on the approval screen. It is NOT a real notification."""
    concerns = ", ".join(state.get("safety_concerns", [])) or "safety concern"
    actions = " ".join(state.get("immediate_actions", []))
    notice = f"EMERGENCY on complaint #{state['complaint_id']}: {concerns}. {actions}".strip()
    logger.warning(notice)
    return {"escalation_notice": notice}


def find_technicians(state):
    attempts = state.get("match_attempts", 0) + 1
    result = _call(find_available_technicians, {"category": state["category"], "limit": 3})
    if not result["ok"]:
        return {"match_attempts": attempts, "outcome": "error", "error": result["error"]}

    technicians = result["technicians"]
    if not technicians:
        return {
            "match_attempts": attempts,
            "technicians": [],
            "match_type": "none",
            "outcome": "no_technician",
        }
    return {
        "match_attempts": attempts,
        "technicians": technicians,
        "match_type": result["match_type"],
        "recommended": technicians[0],
        "error": None,
    }


def request_approval(state):
    """Pauses the workflow until a manager approves or rejects. NOTHING is written before this."""
    decision = interrupt(
        {
            "type": "approval",
            "complaint_id": state["complaint_id"],
            "description": state["description"],
            "category": state["category"],
            "urgency": state["urgency"],
            "is_safety_critical": state.get("is_safety_critical", False),
            "safety_concerns": state.get("safety_concerns", []),
            "immediate_actions": state.get("immediate_actions", []),
            "escalation_notice": state.get("escalation_notice"),
            "triage_note": state.get("triage_note"),
            "match_type": state["match_type"],
            "recommended": state["recommended"],
            "alternatives": state["technicians"],
        }
    )
    return _read_decision(state, decision)


def _read_decision(state, decision) -> dict:
    """Checks the manager's answer. Anything unclear counts as NOT approved."""
    if not isinstance(decision, dict) or decision.get("approved") is not True:
        notes = decision.get("notes") if isinstance(decision, dict) else None
        return {"approved": False, "approval_notes": str(notes or "Not approved by manager.")[:500]}

    approver = str(decision.get("approved_by") or "").strip()
    if len(approver) < 2:
        return {
            "approved": False,
            "approval_notes": "Approval ignored: the approver's name is missing.",
        }

    chosen = decision.get("technician_id", state["recommended"]["id"])
    offered_ids = {technician["id"] for technician in state["technicians"]}
    if isinstance(chosen, bool) or not isinstance(chosen, int) or chosen not in offered_ids:
        return {
            "approved": False,
            "approval_notes": "Approval ignored: that technician was not in the offered list.",
        }

    return {
        "approved": True,
        "approved_by": approver,
        "chosen_technician_id": chosen,
        "approval_notes": str(decision.get("notes") or "")[:500],
    }


def assign(state):
    """Runs only AFTER a manager approved."""
    result = _call(
        record_approved_assignment,
        {
            "complaint_id": state["complaint_id"],
            "technician_id": state["chosen_technician_id"],
            "approved_by": state["approved_by"],
            "notes": state.get("approval_notes") or None,
        },
    )
    if result["ok"]:
        return {"outcome": "assigned", "assign_error": None}
    return {"assign_error": result["error"]}


def complete(state):
    """Last step: works out the final outcome and a plain-English summary."""
    outcome = state.get("outcome")
    if not outcome:
        if state.get("assign_error"):
            outcome = "assignment_failed"
        elif state.get("approved") is False:
            outcome = "rejected"
        else:
            outcome = "error"

    complaint_id = state.get("complaint_id")
    if outcome == "assigned":
        name = next(
            (t["name"] for t in state.get("technicians", []) if t["id"] == state.get("chosen_technician_id")),
            "the technician",
        )
        summary = f"Complaint #{complaint_id} assigned to {name} (approved by {state['approved_by']})."
    elif outcome == "rejected":
        summary = f"Assignment not approved: {state.get('approval_notes', '')} Complaint #{complaint_id} stays 'Reported'."
    elif outcome == "no_technician":
        summary = f"No available technician for '{state.get('category')}'. Complaint #{complaint_id} stays 'Reported'."
        if state.get("is_safety_critical"):
            summary += " This is a safety emergency: contact the on-call manager or emergency services."
    elif outcome == "assignment_failed":
        summary = f"Could not assign: {state.get('assign_error')} Complaint #{complaint_id} stays 'Reported'."
    else:
        summary = f"Workflow stopped: {state.get('error') or 'unknown problem'}"

    return {"outcome": outcome, "summary": summary}


# ---------------------------------------------------------------- routing (conditional edges)
def route_after_load(state) -> str:
    return "complete" if state.get("outcome") else "safety_check"


def route_after_classify(state) -> str:
    if state.get("llm_failed"):
        if state.get("llm_attempts", 0) < MAX_LLM_ATTEMPTS:
            return "classify"  # try again (bounded)
        return "fallback_triage"

    needs_questions = (
        bool(state.get("missing_information"))
        and not state.get("is_safety_critical")  # emergencies are never delayed by questions
        and state.get("clarification_rounds", 0) < MAX_CLARIFICATION_ROUNDS
    )
    return "ask_missing_info" if needs_questions else "save_triage"


def route_after_save(state) -> str:
    if state.get("outcome"):
        return "complete"
    return "escalate_emergency" if state.get("is_safety_critical") else "find_technicians"


def route_after_match(state) -> str:
    return "complete" if state.get("outcome") else "request_approval"


def route_after_approval(state) -> str:
    return "assign" if state.get("approved") else "complete"


def route_after_assign(state) -> str:
    if state.get("outcome") == "assigned":
        return "complete"
    if state.get("match_attempts", 0) < MAX_MATCH_ATTEMPTS:
        return "find_technicians"  # the technician was probably taken: look again (bounded)
    return "complete"
