"""Persistence for the user entity. Owns inserts and flushes, never the transaction."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError
from app.domain.user import User


def upsert_by_google_sub(session: Session, google_sub: str, email: str, name: str) -> User:
    """Insert the user for `google_sub`, or update its email/name when they changed; return the row.

    Flushes so a freshly inserted row has its server-generated `id` before return. No commit — the
    caller owns the transaction boundary.
    """
    user = session.scalar(select(User).where(User.google_sub == google_sub))
    if user is None:
        user = User(google_sub=google_sub, email=email, name=name)
        session.add(user)
        session.flush()
        return user
    if user.email != email or user.name != name:
        user.email = email
        user.name = name
        session.flush()
    return user


def get_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    """Return the user with this id, or None when no such row exists."""
    return session.get(User, user_id)


def update_settings(session: Session, user_id: uuid.UUID, default_currency: str, language: str) -> User:
    """Set the user's display-currency and language preferences and return the updated row.

    Raises `NotFoundError` when the user row is gone. Flushes the mutation but does not commit —
    the caller owns the transaction boundary, consistent with the rest of this module.
    """
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError(f"User '{user_id}' not found.")
    user.default_currency = default_currency
    user.language = language
    session.flush()
    return user


def ensure_dev_user(session: Session, user_id: uuid.UUID) -> None:
    """Idempotently insert the fixed dev user so the asset FK is satisfiable under `AUTH_DISABLED`.

    A dev-only convenience used by the startup hook; not a migration seed. Does nothing when the
    row already exists.
    """
    if session.get(User, user_id) is not None:
        return
    session.add(User(id=user_id, google_sub="dev-user", email="dev@allocio.local", name="Dev User"))
    session.flush()
