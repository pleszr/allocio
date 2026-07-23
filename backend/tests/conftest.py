import os
import sys
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Default the auth bypass on before importing app config, so the fail-loud validator (which requires
# Google/session creds when auth is enabled) never aborts test collection regardless of a local .env
# or cwd. Individual auth tests monkeypatch `settings.auth_disabled` to exercise the enabled path.
os.environ.setdefault("AUTH_DISABLED", "true")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import engine, get_session  # noqa: E402
from app.domain.user import User  # noqa: E402
from app.main import app  # noqa: E402
from app.services.dependencies import get_current_user_id  # noqa: E402

TEST_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
# A second fixed user, referenced by ownership-isolation tests (e.g. "other user's assets are absent").
OTHER_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Yield a session bound to an outer transaction that is always rolled back.

    `join_transaction_mode="create_savepoint"` lets code under test call `commit()` (committing a
    savepoint) while the outer `transaction.rollback()` still discards everything, so every test
    runs against real Postgres but leaves no residue. The test user is seeded here so the
    `assets.user_id` FK holds for every asset-creating test; it is rolled back with the rest.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, join_transaction_mode="create_savepoint")
    try:
        session.add_all(
            [
                User(id=TEST_USER_ID, google_sub="test-user", email="test@allocio.local", name="Test User"),
                User(id=OTHER_USER_ID, google_sub="other-user", email="other@allocio.local", name="Other User"),
            ]
        )
        session.flush()
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
