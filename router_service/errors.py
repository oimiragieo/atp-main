"""Structured error codes for router service."""

from enum import Enum
from typing import TypedDict


class ErrorCode(str, Enum):
    PROMPT_TOO_LARGE = "prompt_too_large"
    NO_MODELS = "no_models_available"
    RATE_LIMIT = "rate_limited"
    INTERNAL = "internal_error"
    CANCELLED = "request_cancelled"
    BACKPRESSURE = "backpressure"
    ESEQ_RETRY = "eseq_retry"
    AUTH_FAILED = "authentication_failed"
    PERMISSION_DENIED = "permission_denied"
    INVALID_REQUEST = "invalid_request"
    MODEL_NOT_FOUND = "model_not_found"
    CONFIGURATION_ERROR = "configuration_error"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    VALIDATION_ERROR = "validation_error"


class ErrorPayload(TypedDict):
    error: str
    detail: str


def error_response(code: ErrorCode, detail: str = "") -> ErrorPayload:
    return {"error": code.value, "detail": detail}
