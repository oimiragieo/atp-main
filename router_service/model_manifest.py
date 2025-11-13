"""Model manifest utilities: computes pseudo hash & provides safety/policy checks.
In production, would load actual weight digests and signed attestations.
"""

import hashlib
import json
import os
from typing import Any

from metrics.registry import REGISTRY

_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "model_registry.json")

# Metrics for GAP-343
_models_registered_total = REGISTRY.gauge("atp_models_registered_total")

# Import audit log for GAP-348 model custody
try:
    # Add memory-gateway to path for audit_log import
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "memory-gateway"))
    import audit_log as audit_log_module

    _AUDIT_AVAILABLE = True
except ImportError:
    audit_log_module = None
    _AUDIT_AVAILABLE = False

# Model custody configuration
_CUSTODY_LOG_PATH = os.path.join(os.path.dirname(__file__), "model_custody.log")
_CUSTODY_SECRET = b"model-custody-secret-key"  # In production, use proper key management
_LAST_CUSTODY_HASH: str | None = None

# Metrics for GAP-348
_model_custody_events_total = REGISTRY.counter("model_custody_events_total")


def load_registry() -> dict[str, dict[str, Any]]:
    with open(_REGISTRY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # augment with pseudo hash (deterministic on record)
    for rec in data:
        h = hashlib.sha256(json.dumps(rec, sort_keys=True).encode()).hexdigest()[:16]
        rec["manifest_hash"] = h
    registry = {rec["model"]: rec for rec in data}

    # Update metrics for GAP-343
    _models_registered_total.set(len(registry))

    return registry


def save_registry(registry: dict[str, dict[str, Any]]) -> None:
    # remove manifest_hash before writing then recompute implicitly on next load
    out: list[dict[str, Any]] = []
    for _m, rec in registry.items():
        r = {k: v for k, v in rec.items() if k != "manifest_hash"}
        out.append(r)
    # stable ordering
    out = sorted(out, key=lambda r: r["model"])
    tmp_path = _REGISTRY_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, sort_keys=False)
    os.replace(tmp_path, _REGISTRY_PATH)

    # Log custody event for registry update
    log_model_custody_event(
        "registry_update", "model_registry", {"models_count": len(registry), "models": list(registry.keys())}
    )


def policy_permit(model_rec: dict[str, Any], required_safety: str) -> bool:
    ordering: dict[str, int] = {"A": 4, "B": 3, "C": 2, "D": 1}
    current = ordering.get(str(model_rec.get("safety_grade", "D")), 0)
    required = ordering.get(required_safety, 0)
    return current >= required


def verify_manifest_signature(model_rec: dict[str, Any]) -> bool:
    """Verify manifest signature for GAP-343.

    In production, this would verify actual cryptographic signatures.
    For now, we verify the manifest hash is consistent.
    """
    # Remove manifest_hash from record for verification
    rec_without_hash = {k: v for k, v in model_rec.items() if k != "manifest_hash"}

    # Compute expected hash
    expected_hash = hashlib.sha256(json.dumps(rec_without_hash, sort_keys=True).encode()).hexdigest()[:16]

    # Check if stored hash matches
    stored_hash = model_rec.get("manifest_hash")
    return stored_hash == expected_hash


def log_model_custody_event(event_type: str, model_id: str, details: dict[str, Any] | None = None) -> bool:
    """Log a model custody event to the audit chain for GAP-348.

    Args:
        event_type: Type of custody event (build, scan, sign, deploy, etc.)
        model_id: Identifier of the model
        details: Additional event details

    Returns:
        True if logged successfully, False otherwise
    """
    global _LAST_CUSTODY_HASH

    if not _AUDIT_AVAILABLE:
        return False

    event = {
        "event_type": event_type,
        "model_id": model_id,
        "timestamp": int(os.times()[4])
        if hasattr(os.times(), "__len__") and len(os.times()) > 4
        else int(os.times().elapsed),
        "details": details or {},
    }

    try:
        # Ensure custody log directory exists
        os.makedirs(os.path.dirname(_CUSTODY_LOG_PATH), exist_ok=True)

        # Append event to custody log
        _LAST_CUSTODY_HASH = audit_log_module.append_event(
            _CUSTODY_LOG_PATH, event, _CUSTODY_SECRET, _LAST_CUSTODY_HASH
        )

        # Update metrics
        _model_custody_events_total.inc()

        return True
    except Exception:
        # Log failure but don't crash
        return False


def verify_model_custody_log() -> bool:
    """Verify the integrity of the model custody log for GAP-348.

    Returns:
        True if log is intact, False if tampered with
    """
    if not _AUDIT_AVAILABLE or not os.path.exists(_CUSTODY_LOG_PATH):
        return True  # No log means no tampering

    try:
        return audit_log_module.verify_log(_CUSTODY_LOG_PATH, _CUSTODY_SECRET)
    except Exception:
        return False


def get_custody_events(model_id: str | None = None) -> list[dict[str, Any]]:
    """Get custody events, optionally filtered by model_id.

    Args:
        model_id: Filter events for specific model, or None for all

    Returns:
        List of custody events
    """
    if not _AUDIT_AVAILABLE or not os.path.exists(_CUSTODY_LOG_PATH):
        return []

    events = []
    try:
        with open(_CUSTODY_LOG_PATH) as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    event = record.get("event", {})
                    if model_id is None or event.get("model_id") == model_id:
                        events.append(event)
    except Exception as e:
        # Log error but don't crash - custody events are not critical
        import logging

        logging.getLogger(__name__).warning("Failed to read custody log: %s", e)

    return events


# Integration functions for model lifecycle events
def log_model_build(model_id: str, build_config: dict[str, Any]) -> bool:
    """Log model build event."""
    return log_model_custody_event("build", model_id, {"build_config": build_config})


def log_model_scan(model_id: str, scan_results: dict[str, Any]) -> bool:
    """Log model scan event."""
    return log_model_custody_event("scan", model_id, {"scan_results": scan_results})


def log_model_sign(model_id: str, signature_info: dict[str, Any]) -> bool:
    """Log model signing event."""
    return log_model_custody_event("sign", model_id, {"signature_info": signature_info})


def log_model_deploy(model_id: str, deploy_target: str) -> bool:
    """Log model deployment event."""
    return log_model_custody_event("deploy", model_id, {"deploy_target": deploy_target})


def log_model_promotion(model_id: str, from_status: str, to_status: str) -> bool:
    """Log model promotion/demotion event."""
    return log_model_custody_event("promote", model_id, {"from_status": from_status, "to_status": to_status})
