"""Domain exception hierarchy. Catch `AllocioException` to handle any app error."""


class AllocioException(Exception):
    """Base class for all Allocio domain exceptions."""


class NotFoundError(AllocioException):
    """Raised when a requested resource does not exist."""


class ValidationError(AllocioException):
    """Raised when domain invariants are violated."""


class AuthenticationError(AllocioException):
    """Raised when a request is not authenticated; surfaced as HTTP 401."""

    def __init__(self, message: str = "Not authenticated.") -> None:
        super().__init__(message)
