"""Protocol Frame model (Python) mirroring Rust atp-schema Frame for convergence.
POC: poc_frame_validate_py
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from metrics.registry import REGISTRY


class Window(BaseModel):
    max_parallel: int = Field(ge=0, le=1_000)
    max_tokens: int = Field(ge=0, le=10_000_000)
    max_usd_micros: int = Field(ge=0, le=10_000_000_000)


class CostEst(BaseModel):
    in_tokens: int = Field(ge=0)
    out_tokens: int = Field(ge=0)
    usd_micros: int = Field(ge=0)


class Meta(BaseModel):
    task_type: str | None = None
    languages: list[str] | None = None
    risk: str | None = None
    data_scope: list[str] | None = None
    trace: Any | None = None
    tool_permissions: list[str] | None = None
    environment_id: str | None = None
    security_groups: list[str] | None = None


class Payload(BaseModel):
    type: str = Field(alias="type")  # keep same key when exporting
    content: Any
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    cost_est: CostEst | None = None
    checksum: str | None = None
    expiry_ms: int | None = Field(default=None, ge=0)

    # Parallel session fields (GAP-111)
    session_id: str | None = None
    persona_id: str | None = None
    clone_id: int | None = None
    seq: int | None = None


class Lane(BaseModel):
    """Lane abstraction for msg_seq isolation (GAP-118).

    A lane defines an independent sequencing context, typically
    scoped by (persona_id, stream_id) for parallel sessions.
    """

    persona_id: str
    stream_id: str

    def __hash__(self) -> int:
        return hash((self.persona_id, self.stream_id))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Lane):
            return False
        return (self.persona_id, self.stream_id) == (other.persona_id, other.stream_id)

    def to_key(self) -> str:
        """Convert to string key for storage/lookup."""
        return f"{self.persona_id}:{self.stream_id}"


class LaneSequencer:
    """Manages per-lane msg_seq counters for lane-based isolation (GAP-118)."""

    def __init__(self):
        self._counters: dict[str, int] = {}
        self._lanes_active = REGISTRY.gauge("lanes_active")
        self._update_metrics()

    def get_next_msg_seq(self, lane: Lane) -> int:
        """Get next msg_seq for the given lane."""
        key = lane.to_key()
        if key not in self._counters:
            self._counters[key] = 0
        self._counters[key] += 1
        self._update_metrics()
        return self._counters[key]

    def get_current_msg_seq(self, lane: Lane) -> int:
        """Get current msg_seq for the given lane."""
        key = lane.to_key()
        return self._counters.get(key, 0)

    def reset_lane(self, lane: Lane) -> None:
        """Reset msg_seq counter for the given lane."""
        key = lane.to_key()
        self._counters[key] = 0
        self._update_metrics()

    def get_active_lanes(self) -> list[str]:
        """Get list of active lane keys."""
        return list(self._counters.keys())

    def _update_metrics(self) -> None:
        """Update lanes_active metric."""
        self._lanes_active.set(len(self._counters))


class Frame(BaseModel):
    v: int = Field(ge=1, le=1)
    session_id: str
    stream_id: str
    msg_seq: int = Field(ge=0)
    frag_seq: int = Field(ge=0)
    flags: list[str] = Field(default_factory=list)
    qos: str
    ttl: int = Field(ge=0, le=255)
    window: Window
    meta: Meta
    payload: Payload
    sig: str | None = None

    @field_validator("flags")
    @classmethod
    def flags_nonempty(cls, v: list[str]) -> list[str]:
        if any(f.strip() == "" for f in v):
            raise ValueError("empty flag")
        return v

    @field_validator("qos")
    @classmethod
    def qos_allowed(cls, v: str) -> str:
        if v not in {"gold", "silver", "bronze"}:
            raise ValueError("invalid qos")
        return v

    def to_public_dict(self) -> dict[str, Any]:  # stable serialization
        return self.model_dump(by_alias=True)


# GAP-111: Parallel Session Message Types
class DispatchTarget(BaseModel):
    """Target persona/clone for dispatch."""

    persona_id: str
    clone_id: int


class DispatchPayload(BaseModel):
    """DISPATCH message payload for parallel sessions."""

    type: str = "agent.dispatch"
    session_id: str
    targets: list[DispatchTarget]
    budget: dict[str, Any]  # tokens, dollars, etc.


class StreamPayload(BaseModel):
    """STREAM message payload for parallel sessions."""

    type: str = "agent.stream"
    session_id: str
    persona_id: str
    clone_id: int
    seq: int
    data: str


class EndPayload(BaseModel):
    """END message payload for parallel sessions."""

    type: str = "agent.end"
    session_id: str
    persona_id: str
    clone_id: int
    stats: dict[str, Any]  # latency_ms, tokens, etc.


class CapabilityPayload(BaseModel):
    """CAPABILITY message payload for adapter registration and capability advertisement."""

    type: str = "adapter.capability"
    adapter_id: str
    adapter_type: str  # e.g., "ollama", "openai", "anthropic"
    capabilities: list[str]  # e.g., ["text-generation", "embedding", "vision"]
    models: list[str]  # e.g., ["llama2:7b", "codellama:13b"]
    max_tokens: int | None = None
    supported_languages: list[str] | None = None
    cost_per_token_micros: int | None = None
    health_endpoint: str | None = None
    version: str | None = None
    metadata: dict[str, Any] | None = None


class HealthPayload(BaseModel):
    """HEALTH message payload for adapter health status and telemetry reporting."""

    type: str = "adapter.health"
    adapter_id: str
    status: str  # "healthy", "degraded", "unhealthy"
    p95_latency_ms: float | None = None
    p50_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    requests_per_second: float | None = None
    error_rate: float | None = None  # percentage of failed requests
    queue_depth: int | None = None
    memory_usage_mb: float | None = None
    cpu_usage_percent: float | None = None
    uptime_seconds: int | None = None
    version: str | None = None
    last_health_check: float | None = None  # timestamp
    metadata: dict[str, Any] | None = None
