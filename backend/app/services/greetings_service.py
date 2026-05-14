"""Greetings use cases. Orchestrates repository calls; holds no FastAPI types."""
from sqlalchemy.orm import Session

from app.domain.greeting import Greeting
from app.repository import greetings_repository


class GreetingsService:
    """Use cases for the greetings feature."""

    def get_first(self, session: Session) -> Greeting:
        """Return the first seeded greeting."""
        return greetings_repository.get_first_greeting(session)
