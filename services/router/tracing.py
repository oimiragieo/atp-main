"""Tracing bootstrap with optional OpenTelemetry dependency (fully typed).

If OpenTelemetry isn't installed or tracing disabled, a lightweight in-process
recorder is used that still exposes a compatible start_as_current_span context
manager interface. This keeps application code simple and mypy-clean.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from contextlib import AbstractContextManager
from types import ModuleType, TracebackType
from typing import Any, Protocol, cast, runtime_checkable

from .config import settings as _settings_module

logger = logging.getLogger(__name__)

SPAN_RECORDS: list[dict[str, Any]] = []


class _SpanLocal(threading.local):
    current: SpanLike | None  # set dynamically by context manager


_SPAN_LOCAL = _SpanLocal()
_TRACER: TracerLike | None = None  # concrete tracer (real or dummy)


@runtime_checkable
class SpanLike(Protocol):
    def set_attribute(self, key: str, value: Any) -> object: ...


class _DummySpan:
    __slots__ = ("name", "attributes", "parent_name")

    def __init__(self, name: str, parent_name: str | None = None):
        self.name = name
        self.attributes: dict[str, Any] = {}
        self.parent_name = parent_name

    def set_attribute(self, key: str, value: Any) -> object:  # mimic OTEL Span
        self.attributes[key] = value
        return None


class _DummySpanCM(AbstractContextManager[_DummySpan]):
    def __init__(self, name: str):
        # capture current span as parent (if any)
        parent = getattr(_SPAN_LOCAL, "current", None)
        parent_name = getattr(parent, "name", None) if parent else None
        self._span = _DummySpan(name, parent_name)
        self._active = False

    def __enter__(self) -> _DummySpan:  # noqa: D401
        _SPAN_LOCAL.current = self._span
        self._active = True
        return self._span

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:  # noqa: D401
        if self._active:
            attrs = dict(self._span.attributes)
            if self._span.parent_name:
                # capture parent span name for simple parent-child assertions in tests
                attrs.setdefault("parent", self._span.parent_name)
            SPAN_RECORDS.append({"name": self._span.name, "attributes": attrs})
            self._active = False
        if getattr(_SPAN_LOCAL, "current", None) is self._span:
            _SPAN_LOCAL.current = None
        return None


@runtime_checkable
class TracerLike(Protocol):
    def start_as_current_span(self, name: str) -> AbstractContextManager[SpanLike]: ...


class _DummyTracer:
    def start_as_current_span(self, name: str) -> _DummySpanCM:  # noqa: D401
        return _DummySpanCM(name)


def _parse_qos_sampling() -> dict[str, float]:
    import os

    raw = os.getenv("ROUTER_SAMPLING_QOS", "")
    out: dict[str, float] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            k, v = part.split(":", 1)
            try:
                out[k.strip().lower()] = max(0.0, min(1.0, float(v)))
            except Exception as e:
                logger.warning(f"Invalid sampling rate value '{v}' for key '{k}', skipping: {e}")
                continue
    return out


class _NoopCM(AbstractContextManager[_DummySpan]):
    def __enter__(self) -> _DummySpan:  # type: ignore[override]
        return _DummySpan("noop")

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None


def start_sampled_span(
    name: str, qos: str | None = None, default_rate: float = 1.0, tenant_id: str | None = None
) -> AbstractContextManager[SpanLike]:
    """Return a span context manager sampled by QoS ratios in ROUTER_SAMPLING_QOS.

    Example: ROUTER_SAMPLING_QOS="gold:1.0,silver:0.5,bronze:0.1"

    Enhanced with error-budget aware tail sampling (GAP-365) and per-tenant policies (GAP-366).
    """
    tracer = get_tracer()
    if not tracer:
        return _NoopCM()
    try:
        import random

        # Get QoS-based rate
        ratios = _parse_qos_sampling()
        qos_rate = ratios.get((qos or "").lower(), default_rate)

        # Check per-tenant sampling if tenant_id provided
        tenant_sample = False
        if tenant_id:
            try:
                from .per_tenant_sampling import should_sample_for_tenant
                tenant_sample = should_sample_for_tenant(tenant_id)
            except ImportError:
                tenant_sample = False

        # Check error-budget aware tail sampling (global fallback)
        try:
            from .error_budget_tail_sampler import should_sample_trace
            tail_sample = should_sample_trace()
        except ImportError:
            tail_sample = False

        # Determine effective sampling rate
        effective_rate = qos_rate

        if tenant_sample and qos_rate < 1.0:
            # Per-tenant sampling overrides QoS rate
            effective_rate = 1.0
        elif tail_sample and qos_rate < 1.0:
            # Global tail sampling overrides QoS rate
            effective_rate = 1.0

        if random.random() <= effective_rate:
            return tracer.start_as_current_span(name)
        return _NoopCM()
    except Exception:  # noqa: S112 - sampling parse fallback
        return tracer.start_as_current_span(name)


def _install_stub_modules() -> None:
    """Install extremely small opentelemetry stubs so 'import opentelemetry.trace' succeeds.

    Only the APIs we rely on are provided. This avoids broad try/except blocks in callers.
    """
    if "opentelemetry.trace" in sys.modules:
        return
    ot_root = ModuleType("opentelemetry")
    trace_mod: Any = ModuleType("opentelemetry.trace")

    def get_current_span() -> SpanLike:
        span = getattr(_SPAN_LOCAL, "current", None)
        return span if span is not None else _DummySpan("noop")

    trace_mod.get_current_span = get_current_span

    class _NoopProvider:  # pragma: no cover - simple stub
        def get_tracer(self, _name: str) -> TracerLike:
            return _TRACER or _DummyTracer()

    trace_mod.get_tracer_provider = lambda: _NoopProvider()
    trace_mod.set_tracer_provider = lambda _provider: None
    sys.modules["opentelemetry"] = ot_root
    sys.modules["opentelemetry.trace"] = trace_mod


def init_tracing() -> TracerLike | None:
    global _TRACER
    # Always allow re-init in test dummy mode to ensure deterministic fresh tracer
    force_dummy = os.getenv("ROUTER_TEST_TRACING_MODE", "").lower() == "dummy"
    # Re-evaluate env-based enable flag each call (settings is frozen dataclass; fetch fresh value)
    enable = _settings_module.enable_tracing or force_dummy
    if _TRACER is not None and not force_dummy:
        return _TRACER  # already initialized (non-test)
    if not enable:
        return None
    if force_dummy:
        _install_stub_modules()
        # fresh records for each init in test mode
        try:
            SPAN_RECORDS.clear()
        except Exception:  # pragma: no cover  # noqa: S110
            pass
        _TRACER = _DummyTracer()
        return _TRACER
    try:  # real OTEL path
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        disable_otlp = os.getenv("ROUTER_DISABLE_OTLP_EXPORT", "0") == "1"
        provider: Any = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": "atp-router",
                    "service.version": _settings_module.service_version,
                }
            )
        )
        if not disable_otlp:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter: Any = OTLPSpanExporter(endpoint=_settings_module.otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        # Add lightweight recording hook (monkey-patch via provider's add_span_processor is simpler than subclassing)
        try:

            class _RecordingProcessor:
                def on_start(self, span: Any, parent: Any) -> None:  # pragma: no cover - simple hook
                    return None

                def on_end(self, span: Any) -> None:  # pragma: no cover
                    try:
                        SPAN_RECORDS.append({"name": span.name, "attributes": dict(getattr(span, "attributes", {}))})
                    except Exception:  # noqa: S110
                        pass

                def shutdown(self) -> None:  # pragma: no cover
                    return None

                def force_flush(self, timeout_millis: int = 30000) -> bool:  # pragma: no cover
                    return True

            provider.add_span_processor(_RecordingProcessor())
        except Exception:  # pragma: no cover - recording hook failure is non-fatal  # noqa: S110
            pass
        trace.set_tracer_provider(provider)
        _TRACER = cast(TracerLike, trace.get_tracer("atp-router"))
        return _TRACER
    except Exception:  # graceful fallback
        _install_stub_modules()
        _TRACER = _DummyTracer()
        return _TRACER


def get_tracer() -> TracerLike | None:
    # Lazy-init so callers that import get_tracer before init_tracing still obtain a tracer
    if _TRACER is None and (
        _settings_module.enable_tracing or os.getenv("ROUTER_TEST_TRACING_MODE", "").lower() == "dummy"
    ):
        # If tracing is enabled but not initialized explicitly, initialize (covers tests invoking feedback directly)
        try:
            init_tracing()
        except Exception:  # pragma: no cover - defensive
            return None
    return _TRACER
