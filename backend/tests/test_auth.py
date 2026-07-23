"""Auth seam tests: the 401 gate, the dev bypass, upsert idempotency, and session logout.

The live Google redirect/token exchange is an external dependency and is not tested; the callback's
claims resolution is stubbed so the persist-user + session seam can be exercised end to end.
"""

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import auth as auth_module
from app.config import settings
from app.db import get_session
from app.main import app
from app.repository import user_repository

from tests.conftest import TEST_USER_ID


@pytest.fixture
def unauthenticated_client(db_session: Session) -> Generator[TestClient, None, None]:
    """A `TestClient` bound to the transactional session but WITHOUT a user-id override.

    Unlike the shared `client` fixture, it exercises the real `get_current_user_id`/session seam.
    """

    def override_get_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def test_protected_route_requires_auth(monkeypatch: pytest.MonkeyPatch, unauthenticated_client: TestClient) -> None:
    monkeypatch.setattr(settings, "auth_disabled", False)
    assert unauthenticated_client.get("/api/assets").status_code == 401


def test_me_unauthenticated_returns_401(monkeypatch: pytest.MonkeyPatch, unauthenticated_client: TestClient) -> None:
    monkeypatch.setattr(settings, "auth_disabled", False)
    assert unauthenticated_client.get("/api/auth/me").status_code == 401


def test_me_under_auth_disabled_returns_dev_user(
    monkeypatch: pytest.MonkeyPatch, unauthenticated_client: TestClient
) -> None:
    monkeypatch.setattr(settings, "auth_disabled", True)
    response = unauthenticated_client.get("/api/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "dev@allocio.local"
    assert body["name"] == "Dev User"
    assert uuid.UUID(body["id"]) == uuid.UUID("00000000-0000-0000-0000-000000000001")


def test_upsert_by_google_sub_is_idempotent(db_session: Session) -> None:
    first = user_repository.upsert_by_google_sub(db_session, "sub-123", "a@example.com", "Ada")
    again = user_repository.upsert_by_google_sub(db_session, "sub-123", "ada@example.com", "Ada Lovelace")
    assert first.id == again.id
    assert again.email == "ada@example.com"
    assert again.name == "Ada Lovelace"
    matches = [u for u in db_session.query(user_repository.User).all() if u.google_sub == "sub-123"]
    assert len(matches) == 1


def test_logout_clears_session(
    monkeypatch: pytest.MonkeyPatch, unauthenticated_client: TestClient, db_session: Session
) -> None:
    monkeypatch.setattr(settings, "auth_disabled", False)

    async def fake_claims(_request: object) -> dict:
        return {"sub": "sub-login", "email": "login@example.com", "name": "Logged In"}

    monkeypatch.setattr(auth_module, "_resolve_google_claims", fake_claims)

    # Sign in via the callback (claims stubbed), which sets the session cookie on the 302.
    callback = unauthenticated_client.get("/api/auth/callback", follow_redirects=False)
    assert callback.status_code == 302
    assert unauthenticated_client.get("/api/auth/me").json()["email"] == "login@example.com"

    assert unauthenticated_client.post("/api/auth/logout").status_code == 204
    assert unauthenticated_client.get("/api/auth/me").status_code == 401
