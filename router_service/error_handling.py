"""Error handling utilities for consistent exception management.

This module provides:
- Consistent error handling patterns
- Proper error logging and propagation
- Context-aware error wrapping
- Retry mechanisms with exponential backoff
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any, TypeVar

from .error_mapping import (
    ATPError,
    AuthFailedError,
    ConfigurationError,
    ExternalServiceError,
    InternalError,
    InvalidRequestError,
    ModelNotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from .errors import ErrorCode

_logger = logging.getLogger(__name__)

T = TypeVar('T')


class ErrorHandler:
    """Centralized error handling with consistent patterns."""

    @staticmethod
    def handle_with_fallback(
        operation: callable,
        fallback_value: Any = None,
        log_level: int = logging.WARNING,
        context: str = ""
    ) -> Any:
        """Execute operation with fallback on failure."""
        try:
            return operation()
        except Exception as e:
            message = f"{context}: {e}" if context else str(e)
            _logger.log(log_level, message)
            return fallback_value

    @staticmethod
    async def handle_async_with_fallback(
        operation: callable,
        fallback_value: Any = None,
        log_level: int = logging.WARNING,
        context: str = ""
    ) -> Any:
        """Execute async operation with fallback on failure."""
        try:
            return await operation()
        except Exception as e:
            message = f"{context}: {e}" if context else str(e)
            _logger.log(log_level, message)
            return fallback_value

    @staticmethod
    def wrap_exceptions(
        exc_type: type[Exception] = Exception,
        message: str = "",
        error_code: ErrorCode | None = None
    ):
        """Decorator to wrap exceptions with ATPError types."""
        def decorator(func):
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except exc_type as e:
                    if error_code:
                        error_class = _get_error_class(error_code)
                        raise error_class(f"{message}: {e}" if message else str(e)) from e
                    else:
                        raise InternalError(f"{message}: {e}" if message else str(e)) from e
            return wrapper
        return decorator

    @staticmethod
    def wrap_async_exceptions(
        exc_type: type[Exception] = Exception,
        message: str = "",
        error_code: ErrorCode | None = None
    ):
        """Decorator to wrap async exceptions with ATPError types."""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except exc_type as e:
                    if error_code:
                        error_class = _get_error_class(error_code)
                        raise error_class(f"{message}: {e}" if message else str(e)) from e
                    else:
                        raise InternalError(f"{message}: {e}" if message else str(e)) from e
            return wrapper
        return decorator


def _get_error_class(error_code: ErrorCode) -> type[ATPError]:
    """Map ErrorCode to ATPError subclass."""
    mapping = {
        ErrorCode.AUTH_FAILED: AuthFailedError,
        ErrorCode.PERMISSION_DENIED: PermissionDeniedError,
        ErrorCode.INVALID_REQUEST: InvalidRequestError,
        ErrorCode.MODEL_NOT_FOUND: ModelNotFoundError,
        ErrorCode.CONFIGURATION_ERROR: ConfigurationError,
        ErrorCode.EXTERNAL_SERVICE_ERROR: ExternalServiceError,
        ErrorCode.VALIDATION_ERROR: ValidationError,
        ErrorCode.INTERNAL: InternalError,
    }
    return mapping.get(error_code, InternalError)


@contextmanager
def error_context(
    context: str = "",
    log_level: int = logging.ERROR,
    reraise: bool = True
) -> Iterator[None]:
    """Context manager for consistent error handling."""
    try:
        yield
    except ATPError:
        # Re-raise ATP errors as-is
        raise
    except Exception as e:
        message = f"{context}: {e}" if context else str(e)
        _logger.log(log_level, message)
        if reraise:
            raise InternalError(message) from e


@asynccontextmanager
async def async_error_context(
    context: str = "",
    log_level: int = logging.ERROR,
    reraise: bool = True
) -> AsyncIterator[None]:
    """Async context manager for consistent error handling."""
    try:
        yield
    except ATPError:
        # Re-raise ATP errors as-is
        raise
    except Exception as e:
        message = f"{context}: {e}" if context else str(e)
        _logger.log(log_level, message)
        if reraise:
            raise InternalError(message) from e


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,)
) -> callable:
    """Decorator for retry logic with exponential backoff."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts - 1:
                        break

                    _logger.warning(
                        f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {e}"
                    )
                    # Note: In sync context, we can't await, so we use time.sleep as fallback
                    import time
                    time.sleep(min(delay, 1.0))  # Cap at 1 second for sync context
                    delay = min(delay * backoff_factor, max_delay)

            raise last_exception or InternalError(f"All {max_attempts} attempts failed")

        return wrapper

    return decorator


def retry_async_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,)
) -> callable:
    """Decorator for async retry logic with exponential backoff."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            delay = base_delay
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts - 1:
                        break

                    _logger.warning(
                        f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {e}"
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)

            raise last_exception or InternalError(f"All {max_attempts} attempts failed")

        return wrapper
    return decorator


def validate_required(value: Any, field_name: str) -> None:
    """Validate that a required field is present and not empty."""
    if value is None:
        raise ValidationError(f"Required field '{field_name}' is missing")
    if isinstance(value, str) and not value.strip():
        raise ValidationError(f"Required field '{field_name}' is empty")
    if isinstance(value, (list, dict)) and len(value) == 0:
        raise ValidationError(f"Required field '{field_name}' is empty")


def validate_range(
    value: int | float,
    field_name: str,
    min_val: int | float | None = None,
    max_val: int | float | None = None
) -> None:
    """Validate that a numeric value is within acceptable range."""
    if min_val is not None and value < min_val:
        raise ValidationError(f"Field '{field_name}' must be >= {min_val}, got {value}")
    if max_val is not None and value > max_val:
        raise ValidationError(f"Field '{field_name}' must be <= {max_val}, got {value}")
