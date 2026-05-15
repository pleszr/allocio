"""FastAPI `Depends` providers for service classes. Override these in tests."""
from app.services.greetings_service import GreetingsService


def get_greetings_service() -> GreetingsService:
    """Provide a `GreetingsService` instance for request handlers."""
    return GreetingsService()
