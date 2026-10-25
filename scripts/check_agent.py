"""Manual demo of the FixFlow workflow with the REAL LLM and database.

  python -m scripts.check_agent start "Water is leaking under my kitchen sink"
  python -m scripts.check_agent resume <complaint_id>
  python -m scripts.check_agent status <complaint_id>
"""
import json
import sys

from app import services
from app.agent.runner import describe_workflow, resume_workflow, start_workflow
from app.database import SessionLocal


def show(result: dict) -> None:
    print("\nSTATUS:", result["status"])
    if "waiting_for" in result:
        print(json.dumps(result["waiting_for"], indent=2, default=str))
    if result["status"] == "completed":
        print("OUTCOME:", result["outcome"])
        print("SUMMARY:", result["summary"])
    if "error" in result:
        print("ERROR:", result["error"])


def start(text: str) -> None:
    with SessionLocal() as db:
        complaint = services.create_complaint(db, "Demo User", "Flat 101", text)
    print(f"Created complaint #{complaint.id}")
    result = start_workflow(complaint.id)
    show(result)
    if result["status"].startswith("waiting"):
        print(f"\nNow run:  python -m scripts.check_agent resume {complaint.id}")


def resume(complaint_id: int) -> None:
    result = describe_workflow(complaint_id)
    if result["status"] == "waiting_for_clarification":
        for question in result["waiting_for"]["questions"]:
            print("Question:", question)
        answer = input("Your answer: ")
        show(resume_workflow(complaint_id, {"answer": answer}))
    elif result["status"] == "waiting_for_approval":
        payload = result["waiting_for"]
        print(json.dumps(payload, indent=2, default=str))
        approve = input("\nApprove the recommended technician? (y/n): ").strip().lower() == "y"
        if not approve:
            notes = input("Reason: ")
            show(resume_workflow(complaint_id, {"approved": False, "notes": notes}))
            return
        name = input("Your name (approver): ")
        chosen = input(f"Technician ID (Enter = recommended {payload['recommended']['id']}): ").strip()
        response = {"approved": True, "approved_by": name}
        if chosen:
            response["technician_id"] = int(chosen)
        show(resume_workflow(complaint_id, response))
    else:
        show(result)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "start":
        start(" ".join(sys.argv[2:]))
    elif len(sys.argv) == 3 and sys.argv[1] == "resume":
        resume(int(sys.argv[2]))
    elif len(sys.argv) == 3 and sys.argv[1] == "status":
        show(describe_workflow(int(sys.argv[2])))
    else:
        print(__doc__)
