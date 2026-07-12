import sys
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import engine, get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.services.dependencies import get_current_user_id  # noqa: E402

TEST_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Yield a session bound to an outer transaction that is always rolled back.

    `join_transaction_mode="create_savepoint"` lets code under test call `commit()` (committing a
    savepoint) while the outer `transaction.rollback()` still discards everything, so every test
    runs against real Postgres but leaves no residue.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """A `TestClient` whose DB session is the transactional `db_session` and user id is fixed."""

    def override_get_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user_id] = lambda: TEST_USER_ID
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()
