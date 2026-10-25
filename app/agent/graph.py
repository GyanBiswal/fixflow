"""Wires the nodes together into the FixFlow graph."""
from langgraph.graph import END, START, StateGraph

from app.agent import nodes
from app.agent.state import FixFlowState


def build_graph(checkpointer):
    builder = StateGraph(FixFlowState)

    builder.add_node("load_complaint", nodes.load_complaint)
    builder.add_node("safety_check", nodes.safety_check)
    builder.add_node("classify", nodes.classify)
    builder.add_node("ask_missing_info", nodes.ask_missing_info)
    builder.add_node("fallback_triage", nodes.fallback_triage)
    builder.add_node("save_triage", nodes.save_triage)
    builder.add_node("escalate_emergency", nodes.escalate_emergency)
    builder.add_node("find_technicians", nodes.find_technicians)
    builder.add_node("request_approval", nodes.request_approval)
    builder.add_node("assign", nodes.assign)
    builder.add_node("complete", nodes.complete)

    builder.add_edge(START, "load_complaint")
    builder.add_conditional_edges(
        "load_complaint",
        nodes.route_after_load,
        {"safety_check": "safety_check", "complete": "complete"},
    )
    builder.add_edge("safety_check", "classify")
    builder.add_conditional_edges(
        "classify",
        nodes.route_after_classify,
        {
            "classify": "classify",
            "fallback_triage": "fallback_triage",
            "ask_missing_info": "ask_missing_info",
            "save_triage": "save_triage",
        },
    )
    builder.add_edge("ask_missing_info", "safety_check")  # answers may reveal a danger: re-check
    builder.add_edge("fallback_triage", "save_triage")
    builder.add_conditional_edges(
        "save_triage",
        nodes.route_after_save,
        {
            "complete": "complete",
            "escalate_emergency": "escalate_emergency",
            "find_technicians": "find_technicians",
        },
    )
    builder.add_edge("escalate_emergency", "find_technicians")
    builder.add_conditional_edges(
        "find_technicians",
        nodes.route_after_match,
        {"complete": "complete", "request_approval": "request_approval"},
    )
    builder.add_conditional_edges(
        "request_approval",
        nodes.route_after_approval,
        {"assign": "assign", "complete": "complete"},
    )
    builder.add_conditional_edges(
        "assign",
        nodes.route_after_assign,
        {"complete": "complete", "find_technicians": "find_technicians"},
    )
    builder.add_edge("complete", END)

    return builder.compile(checkpointer=checkpointer)
