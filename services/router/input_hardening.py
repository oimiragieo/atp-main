"""POC: Input hardening pipeline (GAP-048).

Provides minimal MIME sniffing and schema validation before dispatch.
"""

from __future__ import annotations

from typing import Any

from metrics.registry import REGISTRY
from router_service.event_emitter import RejectionReason, emit_rejection_event

_CTR_INPUT_REJECT = REGISTRY.counter("input_reject_total")


def sniff_mime(data: bytes) -> str:
    """Very lightweight sniff: distinguishes text/plain vs application/octet-stream.

    Returns MIME string.
    """
    if not data:
        return "text/plain"
    # Heuristic: reject if contains NUL or many non-printable bytes
    non_print = sum(1 for b in data if b == 0 or b < 9 or (13 < b < 32))
    ratio = non_print / max(1, len(data))
    return "application/octet-stream" if ratio > 0.05 else "text/plain"


def validate_schema(obj: Any, required_keys: list[str]) -> bool:
    """Minimal schema: require keys at top level and basic types.

    Returns True if all keys exist; False otherwise.
    """
    if not isinstance(obj, dict):
        return False
    for k in required_keys:
        if k not in obj:
            return False
    return True


def check_input(payload: Any, required_keys: list[str] | None = None, request_id: str | None = None) -> tuple[bool, str | None]:
    """Validate payload type and required keys. Increments input_reject_total on failure."""
    if isinstance(payload, (bytes, bytearray)):
        mime = sniff_mime(bytes(payload))
        if mime != "text/plain":
            _CTR_INPUT_REJECT.inc(1)
            emit_rejection_event(
                RejectionReason.INPUT_VALIDATION,
                "input_hardening",
                request_id,
                {"reason": "invalid_mime", "detected_mime": mime}
            )
            return False, "invalid_mime"
        return True, None
    if required_keys and not validate_schema(payload, required_keys):
        _CTR_INPUT_REJECT.inc(1)
        emit_rejection_event(
            RejectionReason.SCHEMA_MISMATCH,
            "input_hardening",
            request_id,
            {"reason": "schema_invalid", "required_keys": required_keys}
        )
        return False, "schema_invalid"
    return True, None
