"""User-settings use cases: read and replace a user's workspace-wide display preferences.

The service owns the transaction boundary; the repository owns queries and flushes. Value
validation (allowed currency/language codes) lives in the request schema Literals, so this layer
assumes validated inputs and only enforces existence of the user row.
"""

import uuid

from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError
from app.domain.user import User
from app.repository import user_repository


class UserSettingsService:
    """Orchestrates reads and updates of a user's settings over a request-scoped session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_settings(self, user_id: uuid.UUID) -> User:
        """Return the user row carrying the current settings; raise `NotFoundError` when it is gone."""
        user = user_repository.get_by_id(self._session, user_id)
        if user is None:
            raise NotFoundError(f"User '{user_id}' not found.")
        return user

    def update_settings(self, user_id: uuid.UUID, default_currency: str, language: str) -> User:
        """Replace both settings fields, commit, and return the saved row.

        Wraps the mutate → commit in a try/except that rolls back before re-raising, so a failure
        never leaves the request-scoped session dirty (per the anti-pattern rule).
        """
        try:
            user = user_repository.update_settings(self._session, user_id, default_currency, language)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return user
