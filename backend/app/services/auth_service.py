"""Authentication use case: persist the signed-in Google user and read it back.

Owns only the persist-user side of auth. The OAuth/network dance (token exchange, userinfo) is a
web concern and stays in the router; this service never sees Authlib types — the router hands it a
plain claims dict.
"""

import uuid

from sqlalchemy.orm import Session

from app.common.exceptions import ValidationError
from app.domain.user import User
from app.repository import user_repository


class AuthService:
    """Persists and reads the authenticated user over a request-scoped session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_from_google(self, claims: dict) -> User:
        """Upsert the user described by Google's OpenID claims and return the row.

        Extracts `sub`/`email`/`name` from the claims dict; a missing `sub` or `email` is a
        malformed token and raises `ValidationError`. Commits so the session persists the user.
        """
        google_sub = claims.get("sub")
        email = claims.get("email")
        if not google_sub or not email:
            raise ValidationError("Google claims are missing a subject id or email.")
        name = claims.get("name") or ""
        user = user_repository.upsert_by_google_sub(self._session, google_sub, email, name)
        self._session.commit()
        return user

    def get_user(self, user_id: uuid.UUID) -> User | None:
        """Return the user with this id, or None when the row is gone."""
        return user_repository.get_by_id(self._session, user_id)
