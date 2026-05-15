"""Persistence access for greetings. Raises domain exceptions, not DB errors."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.exceptions import NotFoundError
from app.common.message_bundle import GREETING_NOT_FOUND
from app.domain.greeting import Greeting


def get_first_greeting(session: Session) -> Greeting:
    """Return the lowest-id greeting, or raise `NotFoundError` if none exist."""
    greeting = session.scalar(select(Greeting).order_by(Greeting.id).limit(1))
    if greeting is None:
        raise NotFoundError(GREETING_NOT_FOUND)
    return greeting
