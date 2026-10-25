"""Small helpers for building test data."""
from sqlalchemy import update

from app import services
from app.models import Technician


def make_technician(db, name, specialty, available=True):
    technician = Technician(name=name, specialty=specialty, phone="555-9999", is_available=available)
    db.add(technician)
    db.flush()
    return technician


def make_unavailable(db, specialty):
    """Marks every technician of a specialty as unavailable (rolled back after the test)."""
    db.execute(
        update(Technician).where(Technician.specialty == specialty).values(is_available=False)
    )


def make_complaint(db, description="Kitchen sink is leaking slowly", category=None, urgency="medium"):
    complaint = services.create_complaint(db, "Test User", "Flat 101", description)
    if category:
        services.save_triage(db, complaint.id, category, urgency, False)
    return complaint


def classified(**changes):
    """A fake successful result from the classification tool."""
    result = {
        "ok": True,
        "category": "plumbing",
        "urgency": "medium",
        "missing_information": [],
        "reasoning": "test",
    }
    result.update(changes)
    return result


class FakeClassifier:
    """Stands in for the LLM tool: returns prepared results in order (the last one repeats)."""

    def __init__(self, *results):
        self.results = results
        self.calls = 0

    def invoke(self, args):
        result = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return result


class FlakyClassifier(FakeClassifier):
    """Crashes on the first call, then behaves normally."""

    def invoke(self, args):
        if self.calls == 0:
            self.calls += 1
            raise RuntimeError("simulated crash")
        return super().invoke(args)
