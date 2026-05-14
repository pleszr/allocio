"""Thin wrapper over stdlib logging so callers depend on `app.common.logger` only."""
import logging

_logger = logging.getLogger("allocio")


def debug(msg: str, *args: object, **kwargs: object) -> None:
    """Log at DEBUG."""
    _logger.debug(msg, *args, **kwargs)


def info(msg: str, *args: object, **kwargs: object) -> None:
    """Log at INFO."""
    _logger.info(msg, *args, **kwargs)


def warning(msg: str, *args: object, **kwargs: object) -> None:
    """Log at WARNING."""
    _logger.warning(msg, *args, **kwargs)


def error(msg: str, *args: object, **kwargs: object) -> None:
    """Log at ERROR."""
    _logger.error(msg, *args, **kwargs)


def exception(msg: str, *args: object, **kwargs: object) -> None:
    """Log at ERROR with traceback. Use inside `except` blocks."""
    _logger.exception(msg, *args, **kwargs)


def critical(msg: str, *args: object, **kwargs: object) -> None:
    """Log at CRITICAL."""
    _logger.critical(msg, *args, **kwargs)
