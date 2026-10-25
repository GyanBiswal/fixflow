"""All FixFlow tools, grouped by how dangerous they are."""
from app.tools.db_tools import (
    find_available_technicians,
    get_complaint_details,
    record_approved_assignment,
    save_triage_result,
    update_complaint_status,
)
from app.tools.triage_tools import check_complaint_safety, classify_complaint

# Safe to hand to an LLM: they only read or analyse.
READ_ONLY_TOOLS = [
    classify_complaint,
    check_complaint_safety,
    get_complaint_details,
    find_available_technicians,
]

# These change data. Only application code (LangGraph nodes) calls them,
# never the LLM directly, and assignment only happens after human approval.
ACTION_TOOLS = [
    save_triage_result,
    record_approved_assignment,
    update_complaint_status,
]

ALL_TOOLS = READ_ONLY_TOOLS + ACTION_TOOLS
