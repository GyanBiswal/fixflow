"""Tests the database connection, a query, and a rolled-back write."""
from sqlalchemy import select, text

from app.config import DATABASE_URL
from app.constants import STATUS_REPORTED
from app.database import SessionLocal, engine
from app.models import Complaint, StatusHistory, Technician

print("Connecting to:", DATABASE_URL.render_as_string(hide_password=True))

with engine.connect() as connection:
    print("SELECT 1 ->", connection.execute(text("SELECT 1")).scalar())

with SessionLocal() as session:
    plumbers = session.scalars(
        select(Technician).where(
            Technician.specialty == "plumbing", Technician.is_available.is_(True)
        )
    ).all()
    print("Available plumbers:", [t.name for t in plumbers])

    # Write test: insert, read the new ID, then ROLLBACK so nothing is saved.
    complaint = Complaint(
        reporter_name="Test User",
        location="Flat 101",
        description="Test complaint (will be rolled back)",
        status=STATUS_REPORTED,
    )
    session.add(complaint)
    session.flush()
    session.add(StatusHistory(complaint_id=complaint.id, old_status=None, new_status=STATUS_REPORTED))
    session.flush()
    print("Inserted test complaint with id:", complaint.id)
    session.rollback()
    print("Rolled back. Nothing was saved.")

print("Database test passed.")
