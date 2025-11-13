#!/usr/bin/env python3
"""
Test for improved error handling patterns.
"""

from unittest.mock import patch

import pytest

from router_service.error_handling import (
    ErrorHandler,
    async_error_context,
    error_context,
    retry_async_with_backoff,
    retry_with_backoff,
    validate_range,
    validate_required,
)
from router_service.error_mapping import (
    InternalError,
    InvalidRequestError,
    ValidationError,
)
from router_service.errors import ErrorCode


class TestErrorHandler:
    """Test the ErrorHandler utility class."""

    def test_handle_with_fallback_success(self):
        """Test successful operation with fallback."""
        def operation():
            return "success"

        result = ErrorHandler.handle_with_fallback(operation, fallback_value="fallback")
        assert result == "success"

    def test_handle_with_fallback_failure(self):
        """Test failed operation with fallback."""
        def failing_operation():
            raise ValueError("test error")

        with patch('router_service.error_handling._logger') as mock_logger:
            result = ErrorHandler.handle_with_fallback(
                failing_operation,
                fallback_value="fallback",
                context="test context"
            )

        assert result == "fallback"
        # Check that warning was logged (may be called through different code path)
        assert mock_logger.log.called or mock_logger.warning.called

    def test_wrap_exceptions(self):
        """Test exception wrapping decorator."""
        @ErrorHandler.wrap_exceptions(ValueError, "wrapped error", ErrorCode.INVALID_REQUEST)
        def failing_function():
            raise ValueError("original error")

        with pytest.raises(InvalidRequestError) as exc_info:
            failing_function()

        assert "wrapped error" in str(exc_info.value)
        assert "original error" in str(exc_info.value)

    def test_wrap_exceptions_default(self):
        """Test exception wrapping with default error type."""
        @ErrorHandler.wrap_exceptions(ValueError, "test error")
        def failing_function():
            raise ValueError("original error")

        with pytest.raises(InternalError) as exc_info:
            failing_function()

        assert "test error" in str(exc_info.value)


class TestErrorContext:
    """Test error context managers."""

    def test_error_context_success(self):
        """Test error context with successful operation."""
        with error_context("test context"):
            pass  # No exception

    def test_error_context_atp_error(self):
        """Test error context re-raises ATP errors."""
        with pytest.raises(ValidationError):
            with error_context("test context"):
                raise ValidationError("test error")

    def test_error_context_generic_error(self):
        """Test error context wraps generic errors."""
        with patch('router_service.error_handling._logger') as mock_logger:
            with pytest.raises(InternalError):
                with error_context("test context", reraise=True):
                    raise ValueError("generic error")

        # Check that error was logged
        assert mock_logger.log.called or mock_logger.error.called


@pytest.mark.asyncio
class TestAsyncErrorContext:
    """Test async error context manager."""

    async def test_async_error_context_success(self):
        """Test async error context with successful operation."""
        async with async_error_context("test context"):
            pass  # No exception

    async def test_async_error_context_atp_error(self):
        """Test async error context re-raises ATP errors."""
        with pytest.raises(ValidationError):
            async with async_error_context("test context"):
                raise ValidationError("test error")

    async def test_async_error_context_generic_error(self):
        """Test async error context wraps generic errors."""
        with patch('router_service.error_handling._logger') as mock_logger:
            with pytest.raises(InternalError):
                async with async_error_context("test context", reraise=True):
                    raise ValueError("generic error")

        # Check that error was logged
        assert mock_logger.log.called or mock_logger.error.called


class TestRetryDecorators:
    """Test retry decorators."""

    def test_retry_with_backoff_success(self):
        """Test retry decorator with successful operation."""
        call_count = 0

        @retry_with_backoff(max_attempts=3)
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("temporary failure")
            return "success"

        result = operation()
        assert result == "success"
        assert call_count == 2

    def test_retry_with_backoff_exhaustion(self):
        """Test retry decorator exhausts attempts."""
        @retry_with_backoff(max_attempts=2)
        def failing_operation():
            raise ValueError("persistent failure")

        with pytest.raises(ValueError):
            failing_operation()

    def test_retry_async_with_backoff_success(self):
        """Test async retry decorator with successful operation."""
        call_count = 0

        @retry_async_with_backoff(max_attempts=3)
        async def async_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("temporary failure")
            return "success"

        import asyncio
        result = asyncio.run(async_operation())
        assert result == "success"
        assert call_count == 2


class TestValidationFunctions:
    """Test validation utility functions."""

    def test_validate_required_success(self):
        """Test successful required field validation."""
        validate_required("test", "field_name")
        validate_required([1, 2, 3], "list_field")
        validate_required({"key": "value"}, "dict_field")

    def test_validate_required_failure(self):
        """Test required field validation failures."""
        with pytest.raises(ValidationError, match="Required field 'empty_string' is empty"):
            validate_required("", "empty_string")

        with pytest.raises(ValidationError, match="Required field 'empty_list' is empty"):
            validate_required([], "empty_list")

        with pytest.raises(ValidationError, match="Required field 'none_value' is missing"):
            validate_required(None, "none_value")

    def test_validate_range_success(self):
        """Test successful range validation."""
        validate_range(5, "test_field", min_val=0, max_val=10)
        validate_range(0, "test_field", min_val=0)
        validate_range(10, "test_field", max_val=10)

    def test_validate_range_failure(self):
        """Test range validation failures."""
        with pytest.raises(ValidationError, match="must be >= 5"):
            validate_range(3, "test_field", min_val=5)

        with pytest.raises(ValidationError, match="must be <= 10"):
            validate_range(15, "test_field", max_val=10)


class TestErrorMapping:
    """Test error mapping functionality."""

    def test_marshal_exception_atp_error(self):
        """Test marshaling ATP errors."""
        from router_service.error_mapping import marshal_exception

        error = ValidationError("test validation error")
        payload = marshal_exception(error)

        assert payload["error"] == "validation_error"
        assert payload["detail"] == "test validation error"

    def test_marshal_exception_generic_error(self):
        """Test marshaling generic exceptions."""
        from router_service.error_mapping import marshal_exception

        error = ValueError("generic error")
        payload = marshal_exception(error)

        assert payload["error"] == "internal_error"
        assert "generic error" in payload["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
