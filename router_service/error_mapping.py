"""Error taxonomy mapping (GAP-005 POC).

Provides:
- Exception hierarchy with stable ErrorCode mapping.
- Marshal function to produce structured ErrorPayload.
- Metrics counters per error code.
"""

from __future__ import annotations

from dataclasses import dataclass

from metrics.registry import REGISTRY

from .errors import ErrorCode, ErrorPayload, error_response


@dataclass
class ATPError(Exception):
    code: ErrorCode
    detail: str = ""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.code.value}: {self.detail}" if self.detail else self.code.value


class PromptTooLargeError(ATPError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ErrorCode.PROMPT_TOO_LARGE, detail)


class NoModelsError(ATPError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ErrorCode.NO_MODELS, detail)


class RateLimitedError(ATPError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ErrorCode.RATE_LIMIT, detail)


class CancelledError(ATPError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ErrorCode.CANCELLED, detail)


class BackpressureError(ATPError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ErrorCode.BACKPRESSURE, detail)


class InternalError(ATPError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ErrorCode.INTERNAL, detail)


class AuthFailedError(ATPError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ErrorCode.AUTH_FAILED, detail)


class PermissionDeniedError(ATPError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ErrorCode.PERMISSION_DENIED, detail)


class InvalidRequestError(ATPError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ErrorCode.INVALID_REQUEST, detail)


class ModelNotFoundError(ATPError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ErrorCode.MODEL_NOT_FOUND, detail)


class ConfigurationError(ATPError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ErrorCode.CONFIGURATION_ERROR, detail)


class ExternalServiceError(ATPError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ErrorCode.EXTERNAL_SERVICE_ERROR, detail)


class ValidationError(ATPError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(ErrorCode.VALIDATION_ERROR, detail)


def marshal_exception(exc: Exception) -> ErrorPayload:
    """Map any exception to ErrorPayload and increment per-code metrics.

    Unknown exceptions map to INTERNAL.
    """
    if isinstance(exc, ATPError):
        code = exc.code
        detail = exc.detail
    else:
        code = ErrorCode.INTERNAL
        detail = str(exc)
    # metrics: maintain per-code counters like error_code_internal_error_total
    REGISTRY.counter(f"error_code_{code.value}_total").inc(1)
    return error_response(code, detail)
