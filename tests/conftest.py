"""Shared test setup: each test runs inside a transaction that is rolled back afterwards."""
import pytest
from sqlalchemy.orm import Session

from app.database import engine


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
