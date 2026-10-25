"""Creates all tables in the fixflow database (safe to run more than once)."""
from app import models  # noqa: F401  (importing registers the tables)
from app.database import Base, engine

Base.metadata.create_all(engine)
print("Tables ready:", ", ".join(Base.metadata.tables.keys()))
