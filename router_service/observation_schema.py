"""Observation schema (v2) with JSON Schema style validation.
Adds bandit fields and optional sustainability metrics.
"""

from typing import Any

OBS_SCHEMA_VERSION = 2

OBS_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "RouterObservation",
    "type": "object",
    "required": [
        "ts",
        "prompt_hash",
        "cluster_hint",
        "model_plan",
        "primary_model",
        "latency_s",
        "tokens_in",
        "tokens_out",
        "cost_usd",
        "phase",
    ],
    "properties": {
        "ts": {"type": "number"},
        "prompt_hash": {"type": "string", "minLength": 4},
        "cluster_hint": {"type": ["string", "null"]},
        "task_type": {"type": ["string", "null"]},  # GAP-340: Task type for SLM training
        "model_plan": {"type": "array", "items": {"type": "string"}},
        "primary_model": {"type": "string"},
        "escalated": {"type": "boolean"},
        "latency_s": {"type": "number", "minimum": 0},
        "tokens_in": {"type": "integer", "minimum": 0},
        "tokens_out": {"type": "integer", "minimum": 0},
        "cost_usd": {"type": "number", "minimum": 0},
        "savings_pct": {"type": "number"},
        "quality_score": {"type": "number"},
        "energy_kwh": {"type": "number"},
        "co2e_grams": {"type": "number"},
        "tool_success": {"type": "boolean"},
        "format_ok": {"type": "boolean"},
        "safety_ok": {"type": "boolean"},  # GAP-205: Safety validation result
        "phase": {"type": "string"},
        "bandit_primary": {"type": ["string", "null"]},
        "bandit_strategy": {"type": ["string", "null"]},
        "schema_version": {"type": "integer"},
        # GAP-349: Carbon attribution fields
        "energy_savings_kwh": {"type": "number"},
        "carbon_savings_co2e_grams": {"type": "number"},
        "energy_efficiency_ratio": {"type": "number"},
        # GAP-212: Seasonal anomaly detection fields
        "latency_anomaly_detected": {"type": "boolean"},
        "latency_forecast_ms": {"type": "number"},
        "latency_error_ms": {"type": "number"},
        "latency_threshold_ms": {"type": "number"},
        # Shadow evaluation fields (GAP-209)
        "shadow_of": {"type": ["string", "null"]},
        "shadow_model": {"type": ["string", "null"]},
        "shadow_quality": {"type": "number"},
        "shadow_latency_s": {"type": "number"},
        "shadow_cost_usd": {"type": "number"},
        "mode": {"type": ["string", "null"]},
    },
}


def validate_observation(obs: dict[str, Any]) -> bool:
    # GAP-219: Enforce schema version matching
    if "schema_version" not in obs:
        return False
    if obs["schema_version"] != OBS_SCHEMA_VERSION:
        return False

    # Minimal JSON schema subset validation (avoid adding dependency)
    try:
        for req in OBS_JSON_SCHEMA["required"]:
            if req not in obs:
                return False
        props = OBS_JSON_SCHEMA["properties"]
        for k, spec in props.items():
            if k not in obs:
                continue
            v = obs[k]
            t = spec.get("type")
            if isinstance(t, list):
                # allow any of listed simple types
                if not any(_coerce_type_ok(v, tt) for tt in t):
                    return False
            else:
                if not _coerce_type_ok(v, t):
                    return False
            if "minimum" in spec and isinstance(v, (int, float)) and v < spec["minimum"]:
                return False
            if spec.get("minLength") and isinstance(v, str) and len(v) < spec["minLength"]:
                return False
        return True
    except Exception:
        return False


def _coerce_type_ok(value: Any, t: str) -> bool:
    if t == "string":
        return isinstance(value, str)
    if t == "number":
        return isinstance(value, (int, float))
    if t == "integer":
        return isinstance(value, int)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "array":
        return isinstance(value, list)
    if t == "null":
        return value is None
    if t == "object":
        return isinstance(value, dict)
    return True
