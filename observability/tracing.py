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
Enhanced Distributed Tracing for ATP Platform
This module provides comprehensive distributed tracing with OpenTelemetry,
trace correlation, performance analysis, and sampling strategies.
"""

import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

try:
    from opentelemetry import baggage, context, trace
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.trace import Span, TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ALWAYS_ON, ParentBased, TraceIdRatioBased
    from opentelemetry.semantic_conventions.trace import SpanAttributes
    from opentelemetry.trace.status import Status, StatusCode
except ImportError:
    # Fallback for when OpenTelemetry is not available
    trace = None
    logging.warning("OpenTelemetry not available. Tracing will be disabled.")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SamplingStrategy(Enum):
    """Trace sampling strategies."""

    ALWAYS_ON = "always_on"
    ALWAYS_OFF = "always_off"
    RATIO_BASED = "ratio_based"
    PARENT_BASED = "parent_based"
    ADAPTIVE = "adaptive"
    COST_AWARE = "cost_aware"


class TraceLevel(Enum):
    """Trace detail levels."""

    MINIMAL = "minimal"  # Only critical spans
    STANDARD = "standard"  # Standard application spans
    DETAILED = "detailed"  # Detailed spans with attributes
    DEBUG = "debug"  # All spans including debug info


@dataclass
class TracingConfig:
    """Tracing configuration."""

    service_name: str = "atp-platform"
    service_version: str = "1.0.0"
    environment: str = "production"

    # Exporters
    jaeger_endpoint: str | None = None
    otlp_endpoint: str | None = None
    console_export: bool = False

    # Sampling
    sampling_strategy: SamplingStrategy = SamplingStrategy.PARENT_BASED
    sampling_ratio: float = 0.1  # 10% sampling

    # Performance
    max_queue_size: int = 2048
    max_export_batch_size: int = 512
    export_timeout_ms: int = 30000

    # Features
    trace_level: TraceLevel = TraceLevel.STANDARD
    enable_correlation: bool = True
    enable_baggage: bool = True
    enable_performance_analysis: bool = True

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["sampling_strategy"] = self.sampling_strategy.value
        result["trace_level"] = self.trace_level.value
        return result


@dataclass
class TraceCorrelation:
    """Trace correlation information."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    correlation_id: str
    user_id: str | None = None
    session_id: str | None = None
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PerformanceMetrics:
    """Performance metrics from traces."""

    operation_name: str
    duration_ms: float
    start_time: float
    end_time: float
    status: str
    error_message: str | None = None
    attributes: dict[str, Any] = None

    def __post_init__(self):
        if self.attributes is None:
            self.attributes = {}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdaptiveSampler:
    """Adaptive sampling based on system load and error rates."""

    def __init__(self, base_ratio: float = 0.1, max_ratio: float = 1.0):
        self.base_ratio = base_ratio
        self.max_ratio = max_ratio
        self.current_ratio = base_ratio
        self.error_count = 0
        self.total_count = 0
        self.last_adjustment = time.time()
        self._lock = threading.Lock()

    def should_sample(self, trace_id: int) -> bool:
        """Determine if a trace should be sampled."""
        with self._lock:
            self.total_count += 1

            # Adjust sampling ratio based on error rate
            if time.time() - self.last_adjustment > 60:  # Adjust every minute
                self._adjust_sampling_ratio()
                self.last_adjustment = time.time()

            # Use trace ID for consistent sampling decision
            return (trace_id % 1000000) < (self.current_ratio * 1000000)

    def record_error(self):
        """Record an error for sampling adjustment."""
        with self._lock:
            self.error_count += 1

    def _adjust_sampling_ratio(self):
        """Adjust sampling ratio based on error rate."""
        if self.total_count == 0:
            return

        error_rate = self.error_count / self.total_count

        if error_rate > 0.05:  # High error rate, increase sampling
            self.current_ratio = min(self.max_ratio, self.current_ratio * 1.5)
        elif error_rate < 0.01:  # Low error rate, decrease sampling
            self.current_ratio = max(self.base_ratio, self.current_ratio * 0.8)

        # Reset counters
        self.error_count = 0
        self.total_count = 0

        logger.debug(f"Adjusted sampling ratio to {self.current_ratio:.3f}")


class CostAwareSampler:
    """Cost-aware sampling to manage tracing costs."""

    def __init__(self, budget_per_hour: float = 10.0, cost_per_span: float = 0.0001):
        self.budget_per_hour = budget_per_hour
        self.cost_per_span = cost_per_span
        self.max_spans_per_hour = int(budget_per_hour / cost_per_span)
        self.spans_this_hour = 0
        self.hour_start = time.time()
        self._lock = threading.Lock()

    def should_sample(self, trace_id: int) -> bool:
        """Determine if sampling is within budget."""
        with self._lock:
            current_time = time.time()

            # Reset counter every hour
            if current_time - self.hour_start > 3600:
                self.spans_this_hour = 0
                self.hour_start = current_time

            # Check if within budget
            if self.spans_this_hour >= self.max_spans_per_hour:
                return False

            self.spans_this_hour += 1
            return True


class EnhancedTracer:
    """Enhanced tracer with ATP-specific functionality."""

    def __init__(self, config: TracingConfig):
        self.config = config
        self.tracer = None
        self.adaptive_sampler = AdaptiveSampler()
        self.cost_aware_sampler = CostAwareSampler()
        self.performance_metrics: list[PerformanceMetrics] = []
        self.correlation_store: dict[str, TraceCorrelation] = {}
        self._lock = threading.Lock()

        if trace:
            self._initialize_tracing()

    def _initialize_tracing(self):
        """Initialize OpenTelemetry tracing."""
        # Create tracer provider
        tracer_provider = TracerProvider(sampler=self._create_sampler(), resource=self._create_resource())

        # Add span processors
        self._add_span_processors(tracer_provider)

        # Set global tracer provider
        trace.set_tracer_provider(tracer_provider)

        # Get tracer
        self.tracer = trace.get_tracer(self.config.service_name, self.config.service_version)

        # Initialize instrumentations
        self._initialize_instrumentations()

        logger.info(f"Initialized tracing for {self.config.service_name}")

    def _create_sampler(self):
        """Create appropriate sampler based on configuration."""
        if self.config.sampling_strategy == SamplingStrategy.ALWAYS_ON:
            return ALWAYS_ON
        elif self.config.sampling_strategy == SamplingStrategy.ALWAYS_OFF:
            return ALWAYS_OFF
        elif self.config.sampling_strategy == SamplingStrategy.RATIO_BASED:
            return TraceIdRatioBased(self.config.sampling_ratio)
        elif self.config.sampling_strategy == SamplingStrategy.PARENT_BASED:
            return ParentBased(root=TraceIdRatioBased(self.config.sampling_ratio))
        else:
            # Default to parent-based
            return ParentBased(root=TraceIdRatioBased(self.config.sampling_ratio))

    def _create_resource(self):
        """Create resource information."""
        from opentelemetry.sdk.resources import Resource

        return Resource.create(
            {
                "service.name": self.config.service_name,
                "service.version": self.config.service_version,
                "deployment.environment": self.config.environment,
                "service.instance.id": str(uuid.uuid4()),
            }
        )

    def _add_span_processors(self, tracer_provider):
        """Add span processors for different exporters."""
        # Console exporter for debugging
        if self.config.console_export:
            console_processor = BatchSpanProcessor(ConsoleSpanExporter())
            tracer_provider.add_span_processor(console_processor)

        # Jaeger exporter
        if self.config.jaeger_endpoint:
            jaeger_exporter = JaegerExporter(
                agent_host_name="localhost", agent_port=14268, collector_endpoint=self.config.jaeger_endpoint
            )
            jaeger_processor = BatchSpanProcessor(
                jaeger_exporter,
                max_queue_size=self.config.max_queue_size,
                max_export_batch_size=self.config.max_export_batch_size,
                export_timeout_millis=self.config.export_timeout_ms,
            )
            tracer_provider.add_span_processor(jaeger_processor)

        # OTLP exporter
        if self.config.otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(endpoint=self.config.otlp_endpoint, insecure=True)
            otlp_processor = BatchSpanProcessor(
                otlp_exporter,
                max_queue_size=self.config.max_queue_size,
                max_export_batch_size=self.config.max_export_batch_size,
                export_timeout_millis=self.config.export_timeout_ms,
            )
            tracer_provider.add_span_processor(otlp_processor)

    def _initialize_instrumentations(self):
        """Initialize automatic instrumentations."""
        try:
            # FastAPI instrumentation
            FastAPIInstrumentor().instrument()

            # HTTP client instrumentations
            RequestsInstrumentor().instrument()
            AioHttpClientInstrumentor().instrument()

            # Database instrumentations
            RedisInstrumentor().instrument()
            SQLAlchemyInstrumentor().instrument()

            logger.info("Initialized automatic instrumentations")
        except Exception as e:
            logger.warning(f"Failed to initialize some instrumentations: {e}")

    @contextmanager
    def start_span(self, name: str, kind: str | None = None, attributes: dict[str, Any] | None = None):
        """Start a new span with context management."""
        if not self.tracer:
            yield None
            return

        span_kind = getattr(trace.SpanKind, kind.upper(), trace.SpanKind.INTERNAL) if kind else trace.SpanKind.INTERNAL

        with self.tracer.start_as_current_span(name, kind=span_kind) as span:
            start_time = time.time()

            try:
                # Add attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                # Add correlation information
                if self.config.enable_correlation:
                    self._add_correlation_info(span)

                yield span

                # Record successful completion
                span.set_status(Status(StatusCode.OK))

            except Exception as e:
                # Record error
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)

                # Update adaptive sampler
                self.adaptive_sampler.record_error()

                raise

            finally:
                # Record performance metrics
                if self.config.enable_performance_analysis:
                    end_time = time.time()
                    duration_ms = (end_time - start_time) * 1000

                    metrics = PerformanceMetrics(
                        operation_name=name,
                        duration_ms=duration_ms,
                        start_time=start_time,
                        end_time=end_time,
                        status="ok" if span.get_span_context().is_valid else "error",
                        attributes=attributes or {},
                    )

                    self._record_performance_metrics(metrics)

    @asynccontextmanager
    async def start_async_span(self, name: str, kind: str | None = None, attributes: dict[str, Any] | None = None):
        """Start a new async span with context management."""
        if not self.tracer:
            yield None
            return

        span_kind = getattr(trace.SpanKind, kind.upper(), trace.SpanKind.INTERNAL) if kind else trace.SpanKind.INTERNAL

        with self.tracer.start_as_current_span(name, kind=span_kind) as span:
            start_time = time.time()

            try:
                # Add attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                # Add correlation information
                if self.config.enable_correlation:
                    self._add_correlation_info(span)

                yield span

                # Record successful completion
                span.set_status(Status(StatusCode.OK))

            except Exception as e:
                # Record error
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)

                # Update adaptive sampler
                self.adaptive_sampler.record_error()

                raise

            finally:
                # Record performance metrics
                if self.config.enable_performance_analysis:
                    end_time = time.time()
                    duration_ms = (end_time - start_time) * 1000

                    metrics = PerformanceMetrics(
                        operation_name=name,
                        duration_ms=duration_ms,
                        start_time=start_time,
                        end_time=end_time,
                        status="ok" if span.get_span_context().is_valid else "error",
                        attributes=attributes or {},
                    )

                    self._record_performance_metrics(metrics)

    def _add_correlation_info(self, span: Span):
        """Add correlation information to span."""
        span_context = span.get_span_context()

        correlation = TraceCorrelation(
            trace_id=format(span_context.trace_id, "032x"),
            span_id=format(span_context.span_id, "016x"),
            parent_span_id=None,  # Would be set if parent exists
            correlation_id=str(uuid.uuid4()),
        )

        # Add to correlation store
        with self._lock:
            self.correlation_store[correlation.trace_id] = correlation

        # Add as span attributes
        span.set_attribute("atp.correlation_id", correlation.correlation_id)
        span.set_attribute("atp.trace_id", correlation.trace_id)

        # Add to baggage if enabled
        if self.config.enable_baggage:
            baggage.set_baggage("correlation_id", correlation.correlation_id)

    def _record_performance_metrics(self, metrics: PerformanceMetrics):
        """Record performance metrics."""
        with self._lock:
            self.performance_metrics.append(metrics)

            # Keep only recent metrics (last 1000)
            if len(self.performance_metrics) > 1000:
                self.performance_metrics = self.performance_metrics[-1000:]

    def get_current_trace_id(self) -> str | None:
        """Get current trace ID."""
        if not trace:
            return None

        current_span = trace.get_current_span()
        if current_span and current_span.get_span_context().is_valid:
            return format(current_span.get_span_context().trace_id, "032x")

        return None

    def get_current_span_id(self) -> str | None:
        """Get current span ID."""
        if not trace:
            return None

        current_span = trace.get_current_span()
        if current_span and current_span.get_span_context().is_valid:
            return format(current_span.get_span_context().span_id, "016x")

        return None

    def get_correlation_info(self, trace_id: str) -> TraceCorrelation | None:
        """Get correlation information for a trace."""
        with self._lock:
            return self.correlation_store.get(trace_id)

    def add_baggage(self, key: str, value: str):
        """Add baggage to current context."""
        if self.config.enable_baggage and trace:
            baggage.set_baggage(key, value)

    def get_baggage(self, key: str) -> str | None:
        """Get baggage from current context."""
        if self.config.enable_baggage and trace:
            return baggage.get_baggage(key)
        return None

    def analyze_performance(
        self,
        operation_name: str | None = None,
        time_window: int = 3600,  # 1 hour
    ) -> dict[str, Any]:
        """Analyze performance metrics."""
        current_time = time.time()
        cutoff_time = current_time - time_window

        # Filter metrics
        with self._lock:
            filtered_metrics = [
                m
                for m in self.performance_metrics
                if m.start_time >= cutoff_time and (operation_name is None or m.operation_name == operation_name)
            ]

        if not filtered_metrics:
            return {"message": "No metrics found"}

        # Calculate statistics
        durations = [m.duration_ms for m in filtered_metrics]
        error_count = sum(1 for m in filtered_metrics if m.status == "error")

        durations.sort()
        count = len(durations)

        analysis = {
            "operation_name": operation_name or "all",
            "time_window_seconds": time_window,
            "total_operations": count,
            "error_count": error_count,
            "error_rate": error_count / count if count > 0 else 0,
            "duration_stats": {
                "min_ms": min(durations) if durations else 0,
                "max_ms": max(durations) if durations else 0,
                "mean_ms": sum(durations) / count if count > 0 else 0,
                "p50_ms": durations[count // 2] if durations else 0,
                "p95_ms": durations[int(count * 0.95)] if durations else 0,
                "p99_ms": durations[int(count * 0.99)] if durations else 0,
            },
            "slowest_operations": [
                {
                    "operation": m.operation_name,
                    "duration_ms": m.duration_ms,
                    "start_time": m.start_time,
                    "attributes": m.attributes,
                }
                for m in sorted(filtered_metrics, key=lambda x: x.duration_ms, reverse=True)[:10]
            ],
        }

        return analysis

    def get_trace_summary(self) -> dict[str, Any]:
        """Get tracing system summary."""
        with self._lock:
            recent_metrics = [
                m
                for m in self.performance_metrics
                if time.time() - m.start_time < 3600  # Last hour
            ]

        return {
            "config": self.config.to_dict(),
            "active_traces": len(self.correlation_store),
            "recent_operations": len(recent_metrics),
            "sampling_ratio": self.adaptive_sampler.current_ratio,
            "cost_aware_spans_this_hour": self.cost_aware_sampler.spans_this_hour,
            "performance_analysis": self.analyze_performance(),
        }


# Global tracer instance
_tracer: EnhancedTracer | None = None


def initialize_tracing(config: TracingConfig) -> EnhancedTracer:
    """Initialize global tracing."""
    global _tracer
    _tracer = EnhancedTracer(config)
    return _tracer


def get_tracer() -> EnhancedTracer | None:
    """Get global tracer instance."""
    return _tracer


# Convenience functions
def start_span(name: str, **kwargs):
    """Start a span using global tracer."""
    if _tracer:
        return _tracer.start_span(name, **kwargs)
    else:
        return contextmanager(lambda: (yield None))()


def start_async_span(name: str, **kwargs):
    """Start an async span using global tracer."""
    if _tracer:
        return _tracer.start_async_span(name, **kwargs)
    else:
        return asynccontextmanager(lambda: (yield None))()


def get_current_trace_id() -> str | None:
    """Get current trace ID."""
    if _tracer:
        return _tracer.get_current_trace_id()
    return None


def add_baggage(key: str, value: str):
    """Add baggage to current context."""
    if _tracer:
        _tracer.add_baggage(key, value)


def get_baggage(key: str) -> str | None:
    """Get baggage from current context."""
    if _tracer:
        return _tracer.get_baggage(key)
    return None
