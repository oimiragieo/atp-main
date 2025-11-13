# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
ATP SDK Exceptions

Custom exception classes for the ATP SDK.
"""

from typing import Any


class ATPError(Exception):
    """Base exception for ATP SDK errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self):
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class AuthenticationError(ATPError):
    """Raised when authentication fails."""

    pass


class AuthorizationError(ATPError):
    """Raised when authorization fails."""

    pass


class RateLimitError(ATPError):
    """Raised when rate limits are exceeded."""

    def __init__(self, message: str, retry_after: int | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.retry_after = retry_after


class ModelNotFoundError(ATPError):
    """Raised when a requested model is not found."""

    pass


class ProviderError(ATPError):
    """Raised when a provider encounters an error."""

    def __init__(self, message: str, provider: str, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.provider = provider


class InsufficientCreditsError(ATPError):
    """Raised when there are insufficient credits for a request."""

    def __init__(
        self,
        message: str,
        required_credits: float | None = None,
        available_credits: float | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.required_credits = required_credits
        self.available_credits = available_credits


class ValidationError(ATPError):
    """Raised when request validation fails."""

    def __init__(self, message: str, field: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.field = field


class TimeoutError(ATPError):
    """Raised when a request times out."""

    def __init__(self, message: str, timeout: float | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.timeout = timeout


class NetworkError(ATPError):
    """Raised when network connectivity issues occur."""

    pass


class ServerError(ATPError):
    """Raised when the server encounters an internal error."""

    def __init__(self, message: str, status_code: int | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.status_code = status_code


class PolicyViolationError(ATPError):
    """Raised when a request violates a policy."""

    def __init__(
        self,
        message: str,
        policy_id: str | None = None,
        violation_type: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.policy_id = policy_id
        self.violation_type = violation_type


class CostLimitExceededError(ATPError):
    """Raised when a request would exceed cost limits."""

    def __init__(
        self,
        message: str,
        cost_limit: float | None = None,
        estimated_cost: float | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.cost_limit = cost_limit
        self.estimated_cost = estimated_cost


class ConfigurationError(ATPError):
    """Raised when there are configuration issues."""

    pass


class StreamingError(ATPError):
    """Raised when streaming encounters an error."""

    pass
