"""Adds mock technicians. Skips if technicians already exist."""
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Technician

MOCK_TECHNICIANS = [
    ("Ravi Kumar", "plumbing", "555-0101", True),
    ("Anita Sharma", "plumbing", "555-0102", True),
    ("Suresh Patel", "plumbing", "555-0103", False),
    ("Meera Nair", "electrical", "555-0104", True),
    ("Arjun Singh", "electrical", "555-0105", True),
    ("Kavita Rao", "cleaning", "555-0106", True),
    ("Imran Khan", "carpentry", "555-0107", True),
    ("Deepak Joshi", "general", "555-0108", True),
]

with SessionLocal() as session:
    existing = session.scalar(select(func.count()).select_from(Technician))
    if existing:
        print(f"Skipped: {existing} technicians already exist.")
    else:
        for name, specialty, phone, available in MOCK_TECHNICIANS:
            session.add(
                Technician(name=name, specialty=specialty, phone=phone, is_available=available)
            )
        session.commit()
        print(f"Added {len(MOCK_TECHNICIANS)} mock technicians.")
