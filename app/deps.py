"""Shared FastAPI dependencies."""
from app.database import SessionLocal


def get_db():
    """Gives each request its own database session and always closes it.
    Anything not committed is rolled back automatically."""
    with SessionLocal() as db:
        yield db
