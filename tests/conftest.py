"""Shared test setup: each test runs inside a transaction that is rolled back afterwards."""
import pytest
from sqlalchemy.orm import Session

from app.database import engine
from app.tools import db_tools


@pytest.fixture
def db_session():
    connection = engine.connect()
    outer_transaction = connection.begin()
    # "create_savepoint": commits inside our code only release a savepoint,
    # so the outer transaction can still be rolled back at the end.
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def use_test_session(db_session, monkeypatch):
    """Makes the database tools use the test session (rolled back) instead of a real one."""

    class _SessionContext:
        def __enter__(self):
            return db_session

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(db_tools, "SessionLocal", lambda: _SessionContext())
    return db_session
