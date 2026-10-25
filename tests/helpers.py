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
