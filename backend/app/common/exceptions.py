"""Domain exception hierarchy. Catch `AllocioException` to handle any app error."""


class AllocioException(Exception):
    """Base class for all Allocio domain exceptions."""


class NotFoundError(AllocioException):
    """Raised when a requested resource does not exist."""


class ValidationError(AllocioException):
    """Raised when domain invariants are violated."""
