"""Starts, resumes and inspects FixFlow workflows. The FastAPI app (Phase 7) will call these.

Each complaint gets its own workflow "thread" (thread_id = complaint-<id>). Checkpoints are stored
in a SQLite file, so a workflow that is waiting for approval survives a server restart.
"""
import logging
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.agent.graph import build_graph

logger = logging.getLogger("fixflow.agent")

CHECKPOINT_PATH = Path(__file__).resolve().parents[2] / "data" / "checkpoints.sqlite"

_graph = None


def get_graph():
    """Builds the graph once, with a file-based checkpoint store."""
    global _graph
    if _graph is None:
        CHECKPOINT_PATH.parent.mkdir(exist_ok=True)
        connection = sqlite3.connect(str(CHECKPOINT_PATH), check_same_thread=False)
        _graph = build_graph(SqliteSaver(connection))
    return _graph


def _config(complaint_id: int) -> dict:
    return {"configurable": {"thread_id": f"complaint-{complaint_id}"}}


def describe_workflow(complaint_id: int, graph=None) -> dict:
    """Says where a workflow is: waiting for input, completed, or not started."""
    graph = graph or get_graph()
    snapshot = graph.get_state(_config(complaint_id))
    values = snapshot.values or {}

    interrupts = [item for task in snapshot.tasks for item in task.interrupts]
    if interrupts:
        payload = interrupts[0].value
        kind = payload.get("type") if isinstance(payload, dict) else None
        status = "waiting_for_approval" if kind == "approval" else "waiting_for_clarification"
        return {"status": status, "waiting_for": payload, "state": values}

    if snapshot.next:
        return {"status": "running", "state": values}
    if values:
        return {
            "status": "completed",
            "outcome": values.get("outcome"),
            "summary": values.get("summary"),
            "state": values,
        }
    return {"status": "not_started"}


def start_workflow(complaint_id: int, graph=None) -> dict:
    """Runs the workflow until it finishes or needs a human. Starting twice does nothing new."""
    graph = graph or get_graph()
    config = _config(complaint_id)

    if graph.get_state(config).values:  # already started: never run it twice
        return describe_workflow(complaint_id, graph)

    try:
        graph.invoke({"complaint_id": complaint_id}, config)
    except Exception as error:
        logger.exception("Workflow crashed for complaint %s", complaint_id)
        return {"status": "failed", "error": f"{type(error).__name__}: {str(error)[:200]}"}
    return describe_workflow(complaint_id, graph)


def resume_workflow(complaint_id: int, response, graph=None) -> dict:
    """Gives a waiting workflow the human's answer and continues it."""
    graph = graph or get_graph()
    config = _config(complaint_id)

    if not graph.get_state(config).next:
        return {"status": "error", "error": "No workflow is waiting for input for this complaint."}

    try:
        graph.invoke(Command(resume=response), config)
    except Exception as error:
        logger.exception("Workflow crashed while resuming complaint %s", complaint_id)
        return {"status": "failed", "error": f"{type(error).__name__}: {str(error)[:200]}"}
    return describe_workflow(complaint_id, graph)
