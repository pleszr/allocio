"""User-settings endpoint tests: read defaults, replace-and-persist, validation, and the auth gate."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.domain.user import User
from app.main import app

from tests.conftest import TEST_USER_ID


def test_get_settings_returns_seeded_defaults(client: TestClient) -> None:
    response = client.get("/api/users/me/settings")

    assert response.status_code == 200
    assert response.json() == {"default_currency": "HUF", "language": "en"}


def test_put_settings_updates_and_persists_both_fields(client: TestClient, db_session: Session) -> None:
    response = client.put("/api/users/me/settings", json={"default_currency": "EUR", "language": "hu"})

    assert response.status_code == 200
    assert response.json() == {"default_currency": "EUR", "language": "hu"}

    stored = db_session.scalars(select(User).where(User.id == TEST_USER_ID)).one()
    assert stored.default_currency == "EUR"
    assert stored.language == "hu"


def test_get_reflects_a_prior_put(client: TestClient) -> None:
    client.put("/api/users/me/settings", json={"default_currency": "USD", "language": "en_hu_alloc"})

    assert client.get("/api/users/me/settings").json() == {
        "default_currency": "USD",
        "language": "en_hu_alloc",
    }


def test_put_with_invalid_currency_is_422(client: TestClient, db_session: Session) -> None:
    response = client.put("/api/users/me/settings", json={"default_currency": "GBP", "language": "en"})

    assert response.status_code == 422
    stored = db_session.scalars(select(User).where(User.id == TEST_USER_ID)).one()
    assert stored.default_currency == "HUF"


def test_put_with_invalid_language_is_422(client: TestClient, db_session: Session) -> None:
    response = client.put("/api/users/me/settings", json={"default_currency": "EUR", "language": "de"})

    assert response.status_code == 422
    stored = db_session.scalars(select(User).where(User.id == TEST_USER_ID)).one()
    assert stored.language == "en"


@pytest.fixture
def unauthenticated_client(db_session: Session) -> Generator[TestClient, None, None]:
    """A `TestClient` bound to the transactional session but WITHOUT a user-id override.

    Exercises the real `get_current_user_id`/session seam so the 401 gate can be asserted.
    """

    def override_get_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def test_get_settings_unauthenticated_returns_401(
    monkeypatch: pytest.MonkeyPatch, unauthenticated_client: TestClient
) -> None:
    monkeypatch.setattr(settings, "auth_disabled", False)
    assert unauthenticated_client.get("/api/users/me/settings").status_code == 401


def test_put_settings_unauthenticated_returns_401(
    monkeypatch: pytest.MonkeyPatch, unauthenticated_client: TestClient
) -> None:
    monkeypatch.setattr(settings, "auth_disabled", False)
    response = unauthenticated_client.put(
        "/api/users/me/settings", json={"default_currency": "EUR", "language": "hu"}
    )
    assert response.status_code == 401
