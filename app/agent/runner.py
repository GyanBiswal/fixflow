"""Starts, resumes and inspects FixFlow workflows. The FastAPI app calls these functions.

Each complaint gets its own workflow "thread" (thread_id = complaint-<id>). Checkpoints are stored
in a SQLite file, so a workflow that is waiting for approval survives a server restart.

A small per-complaint lock stops two requests (for example a double-clicked Approve button) from
running the same workflow at the same time. It works for a single server process, which is how
we deploy FixFlow. The database rules in app/services.py are the final safety net anyway.
"""
import logging
import sqlite3
import threading
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app.agent.graph import build_graph

logger = logging.getLogger("fixflow.agent")

CHECKPOINT_PATH = Path(__file__).resolve().parents[2] / "data" / "checkpoints.sqlite"

_graph = None
_graph_lock = threading.Lock()
_workflow_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def get_graph():
    """Builds the graph once, with a file-based checkpoint store."""
    global _graph
    with _graph_lock:
        if _graph is None:
            CHECKPOINT_PATH.parent.mkdir(exist_ok=True)
            connection = sqlite3.connect(str(CHECKPOINT_PATH), check_same_thread=False)
            _graph = build_graph(SqliteSaver(connection))
        return _graph


def _lock_for(complaint_id: int) -> threading.Lock:
    with _locks_guard:
        return _workflow_locks.setdefault(complaint_id, threading.Lock())


def _thread_id(complaint_id: int) -> str:
    return f"complaint-{complaint_id}"


def _config(complaint_id: int) -> dict:
    return {"configurable": {"thread_id": _thread_id(complaint_id)}}


def _has_interrupt(snapshot) -> bool:
    return any(task.interrupts for task in snapshot.tasks)


def _failed(complaint_id: int, error: Exception) -> dict:
    logger.exception("Workflow crashed for complaint %s", complaint_id)
    return {"status": "failed", "error": f"{type(error).__name__}: {str(error)[:200]}"}


def describe_workflow(complaint_id: int, graph=None) -> dict:
    """Says where a workflow is: waiting for input, in progress, completed, or not started."""
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
        # Not finished and not waiting for a human: it is running right now, or it crashed.
        return {"status": "in_progress", "state": values}
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

    with _lock_for(complaint_id):
        if not graph.get_state(config).values:  # only run if it was never started
            try:
                graph.invoke({"complaint_id": complaint_id}, config)
            except Exception as error:
                return _failed(complaint_id, error)
    return describe_workflow(complaint_id, graph)


def resume_workflow(complaint_id: int, response, graph=None) -> dict:
    """Gives a waiting workflow the human's answer and continues it."""
    graph = graph or get_graph()
    config = _config(complaint_id)

    with _lock_for(complaint_id):
        snapshot = graph.get_state(config)
        if not snapshot.next or not _has_interrupt(snapshot):
            return {"status": "error", "error": "No workflow is waiting for input for this complaint."}
        try:
            graph.invoke(Command(resume=response), config)
        except Exception as error:
            return _failed(complaint_id, error)
    return describe_workflow(complaint_id, graph)


def retry_workflow(complaint_id: int, graph=None) -> dict:
    """Continues a workflow that crashed part-way, from its last saved checkpoint."""
    graph = graph or get_graph()
    config = _config(complaint_id)

    with _lock_for(complaint_id):
        snapshot = graph.get_state(config)
        if not snapshot.next or _has_interrupt(snapshot):
            return {"status": "error", "error": "Nothing to retry for this complaint."}
        try:
            graph.invoke(None, config)  # None = continue from the saved checkpoint
        except Exception as error:
            return _failed(complaint_id, error)
    return describe_workflow(complaint_id, graph)


def restart_workflow(complaint_id: int, graph=None) -> dict:
    """Starts over after a finished workflow that did NOT assign anyone (rejected, no technician...)."""
    graph = graph or get_graph()
    config = _config(complaint_id)

    with _lock_for(complaint_id):
        snapshot = graph.get_state(config)
        values = snapshot.values or {}
        if not values:
            return {"status": "error", "error": "No earlier workflow exists for this complaint."}
        if snapshot.next:
            return {"status": "error", "error": "The workflow is still active. Finish or retry it first."}
        if values.get("outcome") == "assigned":
            return {"status": "error", "error": "This complaint was already assigned."}
        graph.checkpointer.delete_thread(_thread_id(complaint_id))  # forget the old run
    return start_workflow(complaint_id, graph)
