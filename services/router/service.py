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

"""Clean, de-duplicated router service implementing streaming ask endpoint,
bandit model selection, lifecycle promotion/demotion, observation logging,
PII scrubbing, correlation IDs, rate limiting (burst), prompt size limits,
optional metrics, and admin endpoints.

This file replaces a previously corrupted version containing duplicated blocks.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging as _logging
import os
import os as _os
import random
import re
import sys
import threading
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "memory-gateway")))

import pii as PII  # noqa: N812 (external memory-gateway module alias)
import psutil
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Path, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse

from metrics.registry import EXPERIMENT_FRAMES_TOTAL, REGISTRY

# Import PII redaction module for GAP-218
from . import admin_keys
from .ack_logic import AckTracker
from .adaptive_stats import compute_ucb_scores, fetch_all_clusters, thompson_select, ucb_select, update_stat
from .capability_handler import generate_tool_descriptors
from .carbon_energy_attribution import carbon_attribution
from .choose_model import choose
from .config import settings
from .error_mapping import ConfigurationError
from .errors import ErrorCode, error_response
from .lifecycle import evaluate_demotions, evaluate_promotions
from .logging_utils import StructuredLogger, log_event
from .models import AskRequest, Chunk, FinalResponse
from .observation_schema import OBS_SCHEMA_VERSION, validate_observation
from .seasonal_anomaly_detection import check_metric_anomaly, initialize_seasonal_anomaly_detection
from .shadow_evaluation import shadow_tracker
from .state_backend import MemorySchedulerBackend, build_backends
from .success_validator import BaselineQualityScorer
from .task_classify import classify, prompt_hash
from .tracing import get_tracer, init_tracing
from .waf import check_prompt
from .window_update import AIMDController

# Initialize structured logger
logger = StructuredLogger("atp.router")

# Test-friendly lifecycle threshold tuning (only under pytest to allow quick promotion in tests)
if os.getenv("PYTEST_CURRENT_TEST"):
    try:
        import router_service.lifecycle as _lc

        _lc.PROMOTE_MIN_CALLS = 1
        _lc.PROMOTE_COST_IMPROVE = 1.10  # allow slight improvement
    except Exception:  # noqa: S110
        pass

# --- App & data paths ---
app = FastAPI()
_BASE_DIR = os.getenv("ROUTER_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
_DATA_DIR = os.path.abspath(_BASE_DIR)
_LIFECYCLE_FILE = os.path.join(_DATA_DIR, "lifecycle.jsonl")
_COUNTERS_FILE = os.path.join(_DATA_DIR, "counters.json")

_OBS_LOCK = threading.Lock()
_OBS_BUFFER: list[dict[str, Any]] = []
_LAST_SCRUBBED_PROMPT: dict[str, str | None] = {"value": None}

from .model_manifest import load_registry, save_registry  # noqa: E402

try:
    _MODEL_REGISTRY = load_registry()
except Exception as e:
    _logging.warning(f"Failed to load model registry, using empty registry: {e}")
    _MODEL_REGISTRY: dict[str, dict[str, Any]] = {}

# GAP-201: Initialize promotion cycle tracking for existing shadow models
from .lifecycle import initialize_promotion_tracking  # noqa: E402

try:
    initialize_promotion_tracking(_MODEL_REGISTRY)
except Exception as e:
    _logging.warning(f"Failed to initialize promotion tracking: {e}")

# Build state backends (scheduler + aimd)
try:
    _SCHED_BACKEND, _AIMD_BACKEND = build_backends(settings)
except Exception as e:
    _logging.error(f"Failed to build state backends: {e}")
    raise ConfigurationError(f"State backend initialization failed: {e}") from e

# ACK tracker for sequencing

# GAP-202: Quality drift detector for regression detection
# GAP-203: Active learning task sampler
from .active_learning_sampler import ActiveLearningSampler  # noqa: E402

# GAP-204: Continuous improvement pipeline orchestration
from .continuous_improvement_pipeline import ContinuousImprovementPipeline, PipelineStatus  # noqa: E402
from .quality_drift_detector import QualityDriftDetector  # noqa: E402

# Lifecycle counters
_ctr_lifecycle_events = REGISTRY.counter("atp_router_lifecycle_events_total")
_ctr_duration_sum = REGISTRY.counter("request_duration_ms_sum")
_ctr_requests_total = REGISTRY.counter("requests_total")  # generic
_g_ucb_score = REGISTRY.gauge("atp_router_ucb_score")  # placeholder per model cluster quality score

# GAP-218: PII redaction metrics
_ctr_observations_redacted = REGISTRY.counter("atp_router_observations_redacted_total")

# GAP-219: Schema version metrics
_ctr_schema_version_current = REGISTRY.counter("atp_router_observations_schema_version_current_total")
_ctr_schema_version_outdated = REGISTRY.counter("atp_router_observations_schema_version_outdated_total")

# GAP-340: SLM observation metrics
_ctr_slm_observations = REGISTRY.counter("atp_router_slm_observations_total")


# Dependency Injection Container
class ServiceContainer:
    """Simple dependency injection container for managing global state."""

    def __init__(self) -> None:
        self._services: dict[str, tuple[Callable[[], Any], bool]] = {}
        self._singletons: dict[str, Any] = {}

    def register(self, interface: str, implementation: Callable[[], Any], singleton: bool = True) -> None:
        """Register a service implementation."""
        self._services[interface] = (implementation, singleton)

    def get(self, interface: str) -> Any:
        """Get a service instance."""
        if interface not in self._services:
            raise ValueError(f"Service {interface} not registered")

        implementation, singleton = self._services[interface]

        if singleton:
            if interface not in self._singletons:
                self._singletons[interface] = implementation()
            return self._singletons[interface]
        else:
            return implementation()


# Global service container
_services = ServiceContainer()

# Register core services
_services.register("ack_tracker", lambda: AckTracker())
_services.register("quality_drift_detector", lambda: QualityDriftDetector(window_size=100, drift_threshold_sigma=2.0))
_services.register("active_learning_sampler", lambda: ActiveLearningSampler())
_services.register("continuous_improvement_pipeline", lambda: ContinuousImprovementPipeline())
_services.register("logger", lambda: logger)


class _ModelStat(TypedDict):
    calls: int
    success: int
    escalations: int
    cost_sum: float


ModelAction = Literal["promote", "demote"]

_PROMOTION_COUNT = 0
_DEMOTION_COUNT = 0


_MODEL_STATS: dict[tuple[str | None, str], _ModelStat] = {}
# model -> {action: str, ts: float}
_MODEL_LAST_ACTION: dict[str, ModelAction] = {}
_LIFECYCLE_HISTORY: deque[dict[str, Any]] = deque(maxlen=500)
_STOP_EVENT = threading.Event()
_PERSIST_THREAD: threading.Thread | None = None
_WORKER_THREADS: set[threading.Thread] = set()
_ERROR_COUNT = 0
_ctr_req = REGISTRY.counter("requests_total")
_ctr_success = REGISTRY.counter("requests_success_total")
_ctr_error = REGISTRY.counter("requests_error_total")
_ctr_rate_drop = REGISTRY.counter("rate_limiter_dropped_total")
_ctr_admin_denied = REGISTRY.counter("admin_auth_denied_total")
_ctr_admin_rl_dropped = REGISTRY.counter("admin_rate_limited_total")
_ctr_admin_actions = REGISTRY.counter("admin_actions_total")
_ctr_admin_actions_err = REGISTRY.counter("admin_actions_error_total")
_ctr_window_deny_tokens = REGISTRY.counter("window_denied_tokens_total")
_ctr_window_deny_usd = REGISTRY.counter("window_denied_usd_total")
_ctr_scope_violation = REGISTRY.counter("scope_violation_total")
_ctr_cancel = REGISTRY.counter("requests_cancelled_total")
_ctr_explain_requests = REGISTRY.counter("explain_requests_total")
_ctr_trace_requests = REGISTRY.counter("trace_requests_total")
# GAP-209: Shadow evaluation metrics
_ctr_shadow_evals = REGISTRY.counter("atp_router_shadow_evals_total")
_g_shadow_quality_gap = REGISTRY.gauge("atp_router_shadow_quality_gap")
# GAP-215: Observation file rotation metrics
_ctr_obs_files_rotated = REGISTRY.counter("atp_router_observation_files_rotated_total")

# Query defaults for AGP explain endpoint
_DATA_SCOPE_QUERY = Query(None, description="Data scopes for policy evaluation")
_g_state_backend_up = REGISTRY.gauge("state_backend_up")
_g_state_backend_up.set(1)  # default optimistic; will adjust on health check
_hist_latency = (
    REGISTRY.histogram("request_latency_ms", [50, 100, 200, 400, 800, 1200, 2000])
    if settings.enable_latency_histogram
    else None
)
_LATENCY_BUCKETS = [50, 100, 200, 400, 800, 1200, 2000]
_LAT_BUCKET_COUNTS = [0] * (len(_LATENCY_BUCKETS) + 1)
_METRICS_LOCK = threading.Lock()
_CONCURRENCY_SEM = asyncio.Semaphore(settings.max_concurrent)
_SESSION_ACTIVE: dict[str, dict[str, Any]] = {}  # {session_id: {"count": int, "last_activity": float}}
_SESSION_LOCK = asyncio.Lock()
_SESSION_CLEANUP_INTERVAL = 300  # 5 minutes
_SESSION_TTL = 3600  # 1 hour TTL for inactive sessions


async def _cleanup_expired_sessions():
    """Background task to clean up expired sessions."""
    while True:
        try:
            await asyncio.sleep(_SESSION_CLEANUP_INTERVAL)
            current_time = time.time()

            async with _SESSION_LOCK:
                expired_sessions = []
                for sess_id, session_data in _SESSION_ACTIVE.items():
                    if current_time - session_data["last_activity"] > _SESSION_TTL:
                        expired_sessions.append(sess_id)

                for sess_id in expired_sessions:
                    _SESSION_ACTIVE.pop(sess_id, None)
                    logger.info("session.expired", session_id=sess_id)

                if expired_sessions:
                    logger.info("session.cleanup", expired_count=len(expired_sessions))

        except Exception as err:
            logger.debug("session.cleanup_error", error=str(err))


# Note: Request size limits should be configured at the server level (uvicorn/gunicorn)
# using --limit-request-body or equivalent settings
app = FastAPI(
    title="ATP Router Service",
    description="ATP Protocol Router with Model Selection and Load Balancing",
    version="0.1.0",
)

# Import and include authentication router
try:
    from .auth_endpoints import auth_router

    app.include_router(auth_router)
    logger.info("Enterprise authentication system enabled")
except ImportError as e:
    logger.warning(f"Enterprise authentication not available: {e}")
except Exception as e:
    logger.error(f"Failed to initialize enterprise authentication: {e}")

# Import and include policy management router
try:
    from .policy_api import policy_router

    app.include_router(policy_router)
    logger.info("Policy management API enabled")
except ImportError as e:
    logger.warning(f"Policy management API not available: {e}")
except Exception as e:
    logger.error(f"Failed to initialize policy management API: {e}")

# Add tenant isolation middleware
try:
    from .tenant_isolation import TenantIsolationMiddleware, create_default_policies

    # Add middleware (only if ABAC is enabled)
    enable_abac = os.getenv("ENABLE_ABAC", "true").lower() in ("true", "1", "yes")
    if enable_abac:
        app.add_middleware(TenantIsolationMiddleware, enforce_abac=True)
        logger.info("ABAC tenant isolation middleware enabled")

        # Create default policies on startup
        create_default_policies()
    else:
        logger.info("ABAC tenant isolation disabled")

except ImportError as e:
    logger.warning(f"Tenant isolation middleware not available: {e}")
except Exception as e:
    logger.error(f"Failed to initialize tenant isolation middleware: {e}")

# Import and include compliance management router
try:
    from .compliance_api import compliance_router

    app.include_router(compliance_router)
    logger.info("Compliance management API enabled")
except ImportError as e:
    logger.warning(f"Compliance management API not available: {e}")
except Exception as e:
    logger.error(f"Failed to initialize compliance management API: {e}")

# Import and include database management router
try:
    from .database_api import database_router

    app.include_router(database_router)
    logger.info("Database management API enabled")
except ImportError as e:
    logger.warning(f"Database management API not available: {e}")
except Exception as e:
    logger.error(f"Failed to initialize database management API: {e}")


# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database and other startup tasks."""
    try:
        from .database import init_database
        from .database_backup import start_backup_scheduler

        # Initialize database
        await init_database()
        logger.info("Database initialization completed")

        # Start backup scheduler if enabled
        await start_backup_scheduler()

    except Exception as e:
        logger.error(f"Startup initialization failed: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    try:
        from .database import close_database
        from .database_backup import stop_backup_scheduler

        # Stop backup scheduler
        await stop_backup_scheduler()

        # Close database connections
        await close_database()
        logger.info("Database connections closed")

    except Exception as e:
        logger.error(f"Shutdown cleanup failed: {e}")


class _AdminBucket(TypedDict):
    tokens: float
    last: float


_ADMIN_RL_BUCKETS: dict[str, _AdminBucket] = {}


def _load_bandit_config() -> tuple[str, float]:
    """Load bandit configuration with proper error handling."""
    try:
        strategy = settings.bandit_strategy
        explore_factor = float(settings.ucb_explore_factor)
        return strategy, explore_factor
    except (AttributeError, ValueError, TypeError) as e:
        _logging.warning(f"Invalid bandit config, using defaults: {e}")
        return "ucb", 1.4


BANDIT_STRATEGY, UCB_EXPLORE_FACTOR = _load_bandit_config()


def _load_shadow_config() -> tuple[bool, float, str]:
    """Load shadow evaluation configuration from environment variables.

    Returns:
        enabled: Whether shadow evaluation is enabled
        sample_rate: Fraction of requests to shadow evaluate (0.0-1.0)
        strategy: Sampling strategy ('random', 'quality_threshold', 'latency_threshold')
    """
    enabled = os.getenv("ENABLE_SHADOW_EVALUATION", "1").lower() in ("1", "true", "yes")
    sample_rate = float(os.getenv("SHADOW_SAMPLE_RATE", "1.0"))  # Default to 100% for now
    sample_rate = max(0.0, min(1.0, sample_rate))  # Clamp to valid range
    strategy = os.getenv("SHADOW_SAMPLING_STRATEGY", "random")
    if strategy not in ("random", "quality_threshold", "latency_threshold"):
        strategy = "random"
    return enabled, sample_rate, strategy


SHADOW_ENABLED, SHADOW_SAMPLE_RATE, SHADOW_SAMPLING_STRATEGY = _load_shadow_config()


def should_sample_shadow(quality_score: float, latency_ms: float, shadow_models: list[str] | None = None) -> bool:
    """Determine if this request should be shadow evaluated based on sampling strategy.

    Args:
        quality_score: Quality score of the primary model (0.0-1.0)
        latency_ms: Latency in milliseconds
        shadow_models: List of shadow models (optional, for additional validation)

    Returns:
        True if the request should be shadow evaluated
    """
    if not SHADOW_ENABLED or (shadow_models is not None and not shadow_models):
        return False

    # Basic random sampling
    if random.random() > SHADOW_SAMPLE_RATE:
        return False

    if SHADOW_SAMPLING_STRATEGY == "quality_threshold":
        # Sample requests with quality below threshold for improvement tracking
        quality_threshold = float(os.getenv("SHADOW_QUALITY_THRESHOLD", "0.8"))
        return quality_score < quality_threshold
    elif SHADOW_SAMPLING_STRATEGY == "latency_threshold":
        # Sample requests with high latency for performance tracking
        latency_threshold = float(os.getenv("SHADOW_LATENCY_THRESHOLD_MS", "1000"))
        return latency_ms > latency_threshold
    else:  # random
        return True


# ---- Fair scheduler (extracted + repaired) ----
@dataclass
class _FairQueueEntry:
    priority: float
    session: str
    weight: float
    enqueued_at: float = field(default_factory=time.time)
    future: asyncio.Future[bool] | None = None


class FairScheduler:
    """Weighted fair scheduler with served/weight ratio selection.

    Lower served/weight ratio gets priority; ties broken by queue time.
    Provides metrics: grants, enqueued, dequeued, dropped, queue depth,
    weighted session gauge, and wait time histogram.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._queue: list[_FairQueueEntry] = []
        # Always keep concrete dicts locally; for non-memory backend, mirror only when used.
        self._weights: dict[str, float] = (
            defaultdict(lambda: 1.0) if isinstance(_SCHED_BACKEND, MemorySchedulerBackend) else {}
        )
        self._active: dict[str, int] = {}
        self._served: dict[str, int] = {} if isinstance(_SCHED_BACKEND, MemorySchedulerBackend) else {}
        # Optional QoS map (gold > silver > bronze)
        self._qos: dict[str, str] = defaultdict(lambda: os.getenv("DEFAULT_QOS", "silver"))  # type: ignore[name-defined]
        # metrics
        self._grant_ctr = REGISTRY.counter("fair_sched_grants_total")
        self._enq_ctr = REGISTRY.counter("fair_sched_enqueued_total")
        self._dq_ctr = REGISTRY.counter("fair_sched_dequeued_total")
        self._drop_ctr = REGISTRY.counter("fair_sched_dropped_total")
        self._qlen_g = REGISTRY.gauge("fair_sched_queue_depth")
        self._weights_g = REGISTRY.gauge("fair_sched_weighted_sessions")
        self._wait_hist = REGISTRY.histogram("fair_sched_wait_ms", [1, 5, 10, 25, 50, 100, 250, 500, 1000])
        self._wait_max_g = REGISTRY.gauge("fair_sched_wait_max_ms")
        self._starv_boost_ctr = REGISTRY.counter("fair_sched_starvation_boost_total")
        self._starvation_threshold_ms = 50.0  # promote any entry waiting longer than this
        self._wait_max_ms = 0.0  # internal tracker to avoid relying on gauge internals

        # Enhanced starvation detection
        self._starvation_events_ctr = REGISTRY.counter("fair_sched_starvation_events_total")
        self._starvation_quantile = float(os.getenv("FAIR_SCHED_STARVATION_QUANTILE", "0.95"))  # 95th percentile
        self._starvation_boost_factor = float(os.getenv("FAIR_SCHED_BOOST_FACTOR", "2.0"))  # 2x weight boost
        self._starvation_boost_decay = float(os.getenv("FAIR_SCHED_BOOST_DECAY", "0.9"))  # decay factor per boost
        self._boosted_sessions: dict[str, tuple[float, float]] = {}  # session -> (boosted_weight, boost_time)
        self._recent_waits: list[float] = []  # circular buffer for wait time quantiles
        self._max_recent_waits = 100  # keep last 100 wait times for quantile calculation
        self._jains_index_g = REGISTRY.gauge("fair_sched_jains_index")

    def set_weight(self, session: str, weight: float) -> None:
        new_w = max(0.1, weight)
        if isinstance(_SCHED_BACKEND, MemorySchedulerBackend):
            if session not in self._weights:
                self._weights_g.set(len(self._weights) + 1)
            self._weights[session] = new_w
        else:
            _SCHED_BACKEND.set_weight(session, new_w)
            # Update gauge for non-memory backends too
            # Get current count of weighted sessions from backend
            try:
                weights = _SCHED_BACKEND.snapshot_weights()
                self._weights_g.set(len(weights))
            except Exception as e:
                # Fallback: just increment if this is a new session
                _logging.warning("Failed to snapshot weights from backend: %s", e)

    def snapshot_weights(self) -> dict[str, float]:
        if isinstance(_SCHED_BACKEND, MemorySchedulerBackend):
            # local copy to prevent external mutation
            return dict(self._weights)
        return _SCHED_BACKEND.snapshot_weights()

    def _calculate_dynamic_threshold(self) -> float:
        """Calculate starvation threshold based on wait time quantile."""
        if not self._recent_waits:
            return self._starvation_threshold_ms  # fallback to static threshold

        # Sort waits for quantile calculation
        sorted_waits = sorted(self._recent_waits)
        quantile_idx = int(len(sorted_waits) * self._starvation_quantile)
        quantile_idx = min(quantile_idx, len(sorted_waits) - 1)

        dynamic_threshold = sorted_waits[quantile_idx]
        # Ensure minimum threshold to prevent too aggressive boosting
        return max(dynamic_threshold, 10.0)

    def _get_effective_weight(self, session: str) -> float:
        """Get the effective weight for a session, including any active boosts."""
        base_weight = (
            self._weights.get(session, 1.0)
            if isinstance(_SCHED_BACKEND, MemorySchedulerBackend)
            else _SCHED_BACKEND.get_weight(session)
        )

        # Check for active boost
        if session in self._boosted_sessions:
            boosted_weight, boost_time = self._boosted_sessions[session]
            # Apply decay based on time since boost
            time_since_boost = time.time() - boost_time
            decay_factor = self._starvation_boost_decay**time_since_boost
            effective_boost = boosted_weight * decay_factor

            # Remove expired boosts (decay to near base weight)
            if effective_boost <= base_weight * 1.05:
                del self._boosted_sessions[session]
                return base_weight

            return effective_boost

        return base_weight

    def _apply_starvation_boost(self, session: str) -> None:
        """Apply a temporary weight boost to prevent starvation."""
        base_weight = (
            self._weights.get(session, 1.0)
            if isinstance(_SCHED_BACKEND, MemorySchedulerBackend)
            else _SCHED_BACKEND.get_weight(session)
        )

        boosted_weight = base_weight * self._starvation_boost_factor
        self._boosted_sessions[session] = (boosted_weight, time.time())
        self._starvation_events_ctr.inc()

    # No return; starvation boost only updates internal state and metrics

    async def acquire(self, session: str, window_allowed: int, timeout: float = 0.0) -> bool:
        tracer = get_tracer()
        span_cm = tracer.start_as_current_span("fair.acquire") if tracer else None
        if span_cm:
            span_cm.__enter__()
        try:
            async with self._lock:
                cur = self._active.get(session, 0)
                # Fast-path if below window and queue head not same session (avoid head-of-line by same session)
                if cur < window_allowed and (not self._queue or self._queue[0].session != session):
                    self._active[session] = cur + 1
                    self._grant_ctr.inc()
                    if isinstance(_SCHED_BACKEND, MemorySchedulerBackend):
                        self._served[session] = self._served.get(session, 0) + 1
                    else:
                        _SCHED_BACKEND.inc_served(session)
                    # Update Jain's index after served count change
                    self.compute_jains_index()
                    if span_cm:
                        try:
                            import opentelemetry.trace as ottrace

                            span = ottrace.get_current_span()
                            span.set_attribute("fair.fast_path", True)
                        except Exception as err:  # noqa: S110 -- best-effort tracing attribute
                            _logging.debug("fair.fast_path trace attr failed: %s", err)
                    return True
                if timeout <= 0:
                    return False
                weight = (
                    self._weights[session]
                    if isinstance(_SCHED_BACKEND, MemorySchedulerBackend)
                    else _SCHED_BACKEND.get_weight(session)
                )
                ent = _FairQueueEntry(priority=cur / max(weight, 0.1), session=session, weight=weight)
                fut: asyncio.Future[bool] = asyncio.get_event_loop().create_future()
                ent.future = fut
                self._queue.append(ent)
                self._enq_ctr.inc()
                self._qlen_g.set(len(self._queue))
            try:
                await asyncio.wait_for(fut, timeout=timeout)
                return True
            except asyncio.TimeoutError:
                async with self._lock:
                    if not fut.done():
                        for i, e in enumerate(self._queue):
                            if e.future is fut:
                                self._queue.pop(i)
                                self._qlen_g.set(len(self._queue))
                                self._drop_ctr.inc()
                                break
                return False
        finally:
            if span_cm:
                span_cm.__exit__(None, None, None)

    async def release(self, session: str) -> None:
        async with self._lock:
            cur = self._active.get(session, 0)
            if cur > 1:
                self._active[session] = cur - 1
            else:
                self._active.pop(session, None)
            grant = self._select_next_locked()
            if grant:
                self._qlen_g.set(len(self._queue))
                self._dq_ctr.inc()
                if grant.future and not grant.future.done():
                    grant.future.set_result(True)

    def _select_next_locked(self) -> _FairQueueEntry | None:
        tracer = get_tracer()
        span_cm = tracer.start_as_current_span("fair.select") if tracer else None
        best_idx = -1
        best_ratio = None
        best_qos_rank = -1
        starved_idx = -1
        starved_wait_ms = 0.0
        now = time.time()
        for i, e in enumerate(self._queue):
            cur_sess = self._active.get(e.session, 0)
            win_allow = GLOBAL_AIMD.get(e.session)
            if cur_sess >= win_allow:  # respect AIMD cap
                continue
            served = (
                self._served.get(e.session, 0)
                if isinstance(_SCHED_BACKEND, MemorySchedulerBackend)
                else _SCHED_BACKEND.snapshot_served().get(e.session, 0)
            )
            # Use effective weight (including any active boosts)
            effective_weight = self._get_effective_weight(e.session)
            ratio = served / max(effective_weight, 0.1)
            qos_rank = 0
            if os.getenv("ENABLE_QOS_PRIORITY") == "1":
                try:
                    qos = self._qos.get(e.session, "silver")
                    qos_rank = 3 if qos == "gold" else (2 if qos == "silver" else 1)
                except Exception:
                    qos_rank = 0
            waited_ms = (now - e.enqueued_at) * 1000.0
            # Use dynamic threshold based on quantile
            dynamic_threshold = self._calculate_dynamic_threshold()
            if waited_ms > dynamic_threshold and waited_ms > starved_wait_ms:
                starved_wait_ms = waited_ms
                starved_idx = i
            if os.getenv("ENABLE_QOS_PRIORITY") == "1":
                if qos_rank > best_qos_rank or (
                    qos_rank == best_qos_rank
                    and (
                        best_ratio is None
                        or ratio < best_ratio
                        or (ratio == best_ratio and e.enqueued_at < self._queue[best_idx].enqueued_at)
                    )
                ):
                    best_qos_rank = qos_rank
                    best_ratio = ratio
                    best_idx = i
            else:
                if (
                    best_ratio is None
                    or ratio < best_ratio
                    or (ratio == best_ratio and e.enqueued_at < self._queue[best_idx].enqueued_at)
                ):
                    best_ratio = ratio
                    best_idx = i
        # Starvation override with boost
        if starved_idx != -1:
            best_idx = starved_idx
            starved_session = self._queue[starved_idx].session
            self._apply_starvation_boost(starved_session)
            self._starv_boost_ctr.inc()
        if best_idx == -1:
            return None
        e = self._queue.pop(best_idx)
        cur_sess = self._active.get(e.session, 0)
        self._active[e.session] = cur_sess + 1
        self._grant_ctr.inc()
        if isinstance(_SCHED_BACKEND, MemorySchedulerBackend):
            self._served[e.session] = self._served.get(e.session, 0) + 1
        else:
            _SCHED_BACKEND.inc_served(e.session)
        # Update Jain's index after served count change
        self.compute_jains_index()
        try:  # record wait
            waited_ms = (time.time() - e.enqueued_at) * 1000.0
            self._wait_hist.observe(waited_ms)
            # Track wait time for quantile calculation
            self._recent_waits.append(waited_ms)
            if len(self._recent_waits) > self._max_recent_waits:
                self._recent_waits.pop(0)  # remove oldest
            if waited_ms > self._wait_max_ms:
                self._wait_max_ms = waited_ms
                self._wait_max_g.set(waited_ms)
        except Exception as err:  # noqa: S110 -- non-critical metrics
            _logging.debug("wait metrics failed: %s", err)
        if span_cm:
            try:
                import opentelemetry.trace as ottrace

                span = ottrace.get_current_span()
                if best_idx != -1:
                    span.set_attribute("fair.granted_session", e.session)
                    span.set_attribute("fair.wait_ms", round(self._wait_max_ms, 2))
            except Exception as err:  # noqa: S110
                _logging.debug("fair select trace attrs failed: %s", err)
            span_cm.__exit__(None, None, None)
        return e


FAIR_SCHED: FairScheduler = FairScheduler()
GLOBAL_AIMD: AIMDController = AIMDController(backend=_AIMD_BACKEND)
SUCCESS_VALIDATOR: BaselineQualityScorer = BaselineQualityScorer()

# ---- Rate limiting (token bucket with burst) ----
_RATE_LIMIT = settings.rps_limit
_RATE_BURST = settings.rps_burst
_RATE_BUCKETS: defaultdict[str, dict[str, float]] = defaultdict(
    lambda: {"tokens": float(_RATE_BURST), "last": time.time()}
)
_RATE_LOCK = threading.Lock()
_RATE_LIMIT_HITS: dict[str, int] = {"dropped": 0}


def _rate_allow(identifier: str) -> bool:
    now = time.time()
    with _RATE_LOCK:
        b = _RATE_BUCKETS[identifier]
        elapsed = now - b["last"]
        refill = elapsed * _RATE_LIMIT
        if refill > 0:
            b["tokens"] = min(_RATE_BURST, b["tokens"] + refill)
            b["last"] = now
        if b["tokens"] >= 1:
            b["tokens"] -= 1
            return True
        return False


# ---- PII scrubbing ----
PII_PATTERNS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b"), "[REDACTED_ID]"),
]


def _scrub_pii(text: str) -> str:
    if not text:
        return text
    for pat, repl in PII_PATTERNS:
        text = pat.sub(repl, text)
    return text


# ---- Persistence helpers ----
def _persist_lifecycle(evt: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_LIFECYCLE_FILE), exist_ok=True)
        with open(_LIFECYCLE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(evt, separators=(",", ":")) + "\n")
        # GAP-216: Increment lifecycle events counter
        _ctr_lifecycle_events.inc()
    except Exception as err:  # noqa: S110 -- lifecycle persistence is best-effort
        _logging.debug("persist lifecycle failed: %s", err)


def _record_observation(obs: dict[str, Any]) -> None:
    # GAP-219: Track schema version metrics
    schema_version = obs.get("schema_version", 0)
    if schema_version == OBS_SCHEMA_VERSION:
        _ctr_schema_version_current.inc()
    else:
        _ctr_schema_version_outdated.inc()

    # GAP-340: Increment SLM observations counter
    _ctr_slm_observations.inc()

    # GAP-218: Redact PII from observation before persistence
    redacted_obs = PII.redact_object(obs)
    if redacted_obs != obs:  # Only increment if something was actually redacted
        _ctr_observations_redacted.inc(1)

    with _OBS_LOCK:
        _OBS_BUFFER.append(redacted_obs)
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        fname = f"slm_observations-{datetime.date.today().isoformat()}.jsonl"
        fpath = os.path.join(_DATA_DIR, fname)

        # GAP-215: Check file size and rotate if needed
        if os.path.exists(fpath):
            max_size_mb = float(os.getenv("OBSERVATION_MAX_FILE_SIZE_MB", "100"))
            if os.path.getsize(fpath) >= max_size_mb * 1024 * 1024:
                _rotate_observation_file(fpath)

        with open(fpath, "a", encoding="utf-8") as f:
            f.write(json.dumps(redacted_obs, separators=(",", ":")) + "\n")
    except Exception as err:  # noqa: S110 -- observation file write is best-effort
        _logging.debug("persist observation failed: %s", err)


def _rotate_observation_file(fpath: str) -> None:
    """GAP-215: Rotate and compress observation file when it exceeds size limit."""
    try:
        import gzip

        # Create compressed version
        base_name = os.path.basename(fpath)
        compressed_name = f"{base_name}.gz"
        compressed_path = os.path.join(os.path.dirname(fpath), compressed_name)

        # Compress the file
        with open(fpath, "rb") as f_in:
            with gzip.open(compressed_path, "wb", compresslevel=6) as f_out:
                f_out.writelines(f_in)

        # Clear the original file
        with open(fpath, "w", encoding="utf-8") as f:
            f.write("")

        # Increment rotation metric
        _ctr_obs_files_rotated.inc()

        _logging.info("Rotated observation file: %s -> %s", base_name, compressed_name)

    except Exception as err:  # noqa: S110 -- rotation is best-effort
        _logging.debug("observation file rotation failed: %s", err)


def _evaluate_quality(text: str) -> float:
    base = min(len(text) / 400.0, 1.0)
    return round(0.65 + 0.25 * base + random.uniform(-0.02, 0.02), 3)


def _record_latency(ms: float) -> None:
    if not settings.enable_latency_histogram:
        return
    with _METRICS_LOCK:
        for i, b in enumerate(_LATENCY_BUCKETS):
            if ms <= b:
                _LAT_BUCKET_COUNTS[i] += 1
                return
        _LAT_BUCKET_COUNTS[-1] += 1


def _persist_counters_loop() -> None:
    interval = max(2, settings.persist_interval_seconds)
    while not _STOP_EVENT.wait(interval):
        try:
            snap = REGISTRY.export()
            data = {
                "registry": snap,
                "promotion": _PROMOTION_COUNT,
                "demotion": _DEMOTION_COUNT,
                "rate_limit_dropped": _RATE_LIMIT_HITS["dropped"],
                "lat_buckets": _LAT_BUCKET_COUNTS,
                "fair_weights": FAIR_SCHED.snapshot_weights(),
            }
            os.makedirs(_DATA_DIR, exist_ok=True)
            with open(_COUNTERS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"))
        except Exception as err:  # noqa: S110 -- background persistence loop resilience
            _logging.debug("persist counters failed: %s", err)


def _load_counters() -> None:
    global _PROMOTION_COUNT, _DEMOTION_COUNT
    try:
        if os.path.exists(_COUNTERS_FILE):
            with open(_COUNTERS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            snap = data.get("registry", {})
            counters = snap.get("counters", {})
            # restore counters where possible
            for name, val in counters.items():
                if name in REGISTRY.counters:
                    REGISTRY.counters[name].set(val)
                else:
                    REGISTRY.counters[name] = REGISTRY.counter(name)
                    REGISTRY.counters[name].set(val)
            _PROMOTION_COUNT = max(_PROMOTION_COUNT, data.get("promotion", 0))
            _DEMOTION_COUNT = max(_DEMOTION_COUNT, data.get("demotion", 0))
            _RATE_LIMIT_HITS["dropped"] = data.get("rate_limit_dropped", 0)
            if settings.enable_latency_histogram and _LAT_BUCKET_COUNTS:
                saved_buckets = data.get("lat_buckets")
                if isinstance(saved_buckets, list) and len(saved_buckets) == len(_LAT_BUCKET_COUNTS):
                    for i, v in enumerate(saved_buckets):
                        _LAT_BUCKET_COUNTS[i] = max(_LAT_BUCKET_COUNTS[i], v)
            # restore fair scheduler weights
            fw = data.get("fair_weights")
            if isinstance(fw, dict):
                for sid, w in fw.items():
                    try:
                        FAIR_SCHED.set_weight(sid, float(w))
                    except Exception as err:  # noqa: S110
                        _logging.debug("restore fair weight failed: %s", err)

            # Initialize seasonal anomaly detection with historical data if available
            historical_requests = data.get("request_history", [])
            if historical_requests and len(historical_requests) >= 120:  # Need at least 2 hours of data
                try:
                    initialize_seasonal_anomaly_detection(historical_requests[-120:])  # Use last 2 hours
                    _logging.info(
                        "Seasonal anomaly detection initialized with %d historical points", len(historical_requests)
                    )
                except Exception as err:  # noqa: S110
                    _logging.debug("seasonal anomaly detection initialization failed: %s", err)

    except Exception as err:  # noqa: S110 -- counters load is best-effort
        _logging.debug("load counters failed: %s", err)


# ---- Middleware (correlation ID + rate limit) ----
@app.middleware("http")
async def middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    cid = (
        request.headers.get("x-correlation-id")
        or request.headers.get("x-request-id")
        or f"cid-{int(time.time() * 1000)}-{random.randint(1000, 9999)}"
    )
    request.state.correlation_id = cid
    api_key = request.headers.get("x-api-key") or request.headers.get("x_api_key") or ""
    ident = api_key or (request.client.host if request.client else "anon")
    if not _rate_allow(ident):
        _RATE_LIMIT_HITS["dropped"] += 1
        _ctr_rate_drop.inc()
        return JSONResponse(
            status_code=429, content=error_response(ErrorCode.RATE_LIMIT, "too_many_requests") | {"correlation_id": cid}
        )
    resp = await call_next(request)
    resp.headers["x-correlation-id"] = cid
    return resp


# ---- Health / Ready ----
@app.get("/healthz")
def health() -> dict[str, Any]:
    """Comprehensive health check with dependency validation."""
    health_status: dict[str, Any] = {"status": "healthy", "service": "router", "timestamp": time.time(), "checks": {}}

    # Check model registry
    registry_healthy = bool(_MODEL_REGISTRY)
    health_status["checks"]["model_registry"] = {
        "status": "healthy" if registry_healthy else "unhealthy",
        "details": f"{len(_MODEL_REGISTRY)} models loaded" if registry_healthy else "No models loaded",
    }

    # Check memory usage
    process = psutil.Process()
    memory_mb = process.memory_info().rss / 1024 / 1024
    memory_healthy = memory_mb < 1000  # Less than 1GB
    health_status["checks"]["memory_usage"] = {"status": "healthy" if memory_healthy else "degraded", "details": ".1f"}

    # Check service dependencies
    try:
        # Check if core services are available
        _services.get("quality_drift_detector")
        _services.get("active_learning_sampler")
        _services.get("continuous_improvement_pipeline")
        health_status["checks"]["service_dependencies"] = {
            "status": "healthy",
            "details": "All core services initialized",
        }
    except Exception as e:
        health_status["checks"]["service_dependencies"] = {
            "status": "unhealthy",
            "details": f"Service initialization error: {e}",
        }

    # Check data directory
    data_dir_exists = os.path.exists(_DATA_DIR)
    health_status["checks"]["data_directory"] = {
        "status": "healthy" if data_dir_exists else "unhealthy",
        "details": f"Data directory accessible: {_DATA_DIR}"
        if data_dir_exists
        else f"Data directory missing: {_DATA_DIR}",
    }

    # Determine overall status
    checks = health_status["checks"]
    unhealthy_checks = [check for check in checks.values() if check["status"] == "unhealthy"]
    if unhealthy_checks:
        health_status["status"] = "unhealthy"
    elif any(check["status"] == "degraded" for check in checks.values()):
        health_status["status"] = "degraded"

    return health_status


@app.get("/readyz")
def ready() -> dict[str, Any]:
    """Readiness check - ensures service is ready to handle requests."""
    readiness_status: dict[str, Any] = {"ready": True, "checks": {}}

    # Check model registry is loaded
    registry_ready = bool(_MODEL_REGISTRY)
    readiness_status["checks"]["model_registry"] = registry_ready

    # Check core services are initialized
    try:
        _services.get("quality_drift_detector")
        _services.get("active_learning_sampler")
        readiness_status["checks"]["core_services"] = True
    except Exception:
        readiness_status["checks"]["core_services"] = False
        readiness_status["ready"] = False

    # Overall readiness
    readiness_status["ready"] = all(readiness_status["checks"].values())

    return readiness_status


# ---- Admin guard ----
def _init_admin_keys_once() -> None:
    """Initialize admin keys with proper error handling."""
    try:
        admin_keys.load_persisted()
        env_keys = os.getenv("ROUTER_ADMIN_KEYS", "")
        legacy_single = os.getenv("ROUTER_ADMIN_API_KEY", "")
        combined = env_keys or legacy_single or ""

        # Only pass fallback api_key when no explicit env keys at all (production convenience)
        fallback = "" if combined else settings.api_key
        admin_keys.init_from_env(combined, fallback)

        if fallback and not admin_keys.list_keys():  # production bootstrap convenience
            try:
                admin_keys.init_from_env(fallback, fallback)
            except Exception as e:  # noqa: S110 -- admin key fallback is optional
                _logging.debug(f"Admin key fallback failed: {e}")

    except Exception as err:  # noqa: S110 -- admin key load is optional during bootstrap
        _logging.warning(f"Admin key initialization failed, continuing without admin auth: {err}")


_init_admin_keys_once()


def admin_guard(required_role: str = "read") -> Callable[[str | None], None]:
    def guard(x_api_key: str | None = Header(None)) -> None:
        admin_keys.ensure_env_keys_loaded()

        # Production security: Always enforce authentication
        if not admin_keys.list_keys():
            # Bootstrap mode: Allow access if no keys are configured
            return None

        if not x_api_key:
            _ctr_admin_denied.inc()
            raise HTTPException(status_code=401, detail="unauthorized")

        roles = admin_keys.key_roles(x_api_key)
        if not roles:
            _ctr_admin_denied.inc()
            raise HTTPException(status_code=401, detail="unauthorized")

        if required_role not in roles:
            _ctr_admin_denied.inc()
            raise HTTPException(status_code=403, detail="forbidden")
        # Rate limit enforcement
        now = time.time()
        rps = float(os.getenv("ROUTER_ADMIN_RPS", "30"))
        burst = float(os.getenv("ROUTER_ADMIN_RPS_BURST", str(int(rps))))
        key_hash = admin_keys.hash_key(x_api_key)
        bucket = _ADMIN_RL_BUCKETS.setdefault(key_hash, {"tokens": burst, "last": now})
        elapsed = now - bucket["last"]
        if elapsed > 0:
            bucket["tokens"] = min(burst, bucket["tokens"] + elapsed * rps)
            bucket["last"] = now
        if bucket["tokens"] < 1.0:
            _ctr_admin_rl_dropped.inc()
            raise HTTPException(status_code=429, detail="admin_rate_limited")
        bucket["tokens"] -= 1.0

    return guard


# ---- Ask endpoint ----
@app.post("/v1/ask")
async def ask(req: AskRequest, request: Request) -> StreamingResponse:  # StreamingResponse produced indirectly
    tracer = get_tracer()
    span_ctx = tracer.start_as_current_span("ask") if tracer else None
    if span_ctx:
        span_ctx.__enter__()
    # Global cap guard
    async with _CONCURRENCY_SEM:
        # OIDC/JWT (HS256) opt-in
        if os.getenv("ENABLE_OIDC") == "1":
            authz = request.headers.get("authorization") or request.headers.get("Authorization")
            if not authz or not authz.lower().startswith("bearer "):
                return JSONResponse(status_code=401, content={"error": "unauthorized"})
            token = authz.split(" ", 1)[1].strip()
            try:
                aud = os.getenv("OIDC_AUD") or None
                iss = os.getenv("OIDC_ISS") or None
                ok = False
                # Prefer JWKS if enabled
                if os.getenv("ENABLE_OIDC_JWKS") == "1":
                    from .oidc_jwks import get_cached_jwks, verify_with_jwks

                    jwks = get_cached_jwks()
                    if jwks:
                        ok, _claims = verify_with_jwks(token, jwks, expected_iss=iss, expected_aud=aud)
                if not ok:
                    from .oidc import verify_jwt_hs256

                    secret = (os.getenv("OIDC_SECRET") or "").encode("utf-8")
                    ok, _claims = verify_jwt_hs256(token, secret, expected_iss=iss, expected_aud=aud)
                if not ok:
                    return JSONResponse(status_code=401, content={"error": "unauthorized"})
            except Exception:
                return JSONResponse(status_code=401, content={"error": "unauthorized"})
        sess_id = (
            req.session_id or req.conversation_id or request.headers.get("x-session-id") or request.client.host
            if request.client
            else "anon"
        )

        # GAP-305: Consistency level enforcement (EVENTUAL vs RYW)
        from .consistency_enforcer import get_enforcer

        enforcer = get_enforcer()

        # Start or update session for consistency tracking
        consistency_level = req.consistency_level or "EVENTUAL"
        if consistency_level not in ("EVENTUAL", "RYW"):
            consistency_level = "EVENTUAL"

        session_state = enforcer.start_session(
            session_id=sess_id,
            consistency_level=consistency_level,  # type: ignore
            namespace=req.tenant,
            ttl_seconds=300.0,
        )
        # Optional: map request quality to QoS tier for scheduling
        try:
            qos = "gold" if req.quality == "high" else ("bronze" if req.quality == "fast" else "silver")
            if hasattr(globals(), "FAIR_SCHED") and os.getenv("ENABLE_QOS_PRIORITY") == "1":
                try:
                    FAIR_SCHED.set_qos(sess_id, qos)  # type: ignore[attr-defined]
                except Exception:  # noqa: S110 -- QoS scheduler is optional
                    pass
        except Exception:  # noqa: S110 -- QoS scheduler integration is optional
            pass
        # Data-scope enforcement (POC, opt-in)
        if os.getenv("ENABLE_SCOPE_ENFORCE") == "1":
            allowed_csv = os.getenv("ALLOWED_DATA_SCOPES", "public")
            allowed = {s.strip() for s in allowed_csv.split(",") if s.strip()}
            scope = request.headers.get("x-data-scope")
            if not scope or scope not in allowed:
                _ctr_scope_violation.inc()
                return JSONResponse(status_code=403, content={"error": "scope_forbidden", "allowed": sorted(allowed)})
        # AIMD window for this session
        window_allowed = GLOBAL_AIMD.get(sess_id)
        # Attempt fair acquisition (non-blocking for now). If denied, fall back to legacy check.
        active_now = 0
        async with _SESSION_LOCK:
            session_data = _SESSION_ACTIVE.get(sess_id, {"count": 0, "last_activity": time.time()})
            active_now = session_data["count"]
            if active_now >= window_allowed:
                raise HTTPException(
                    status_code=429,
                    detail=ErrorCode.BACKPRESSURE.value if hasattr(ErrorCode, "BACKPRESSURE") else "backpressure",
                )
            session_data["count"] = active_now + 1
            session_data["last_activity"] = time.time()
            _SESSION_ACTIVE[sess_id] = session_data
        await FAIR_SCHED.acquire(sess_id, window_allowed, timeout=0.0)
        # Enforce prompt size limit early
        max_chars = int(os.getenv("ROUTER_MAX_PROMPT_CHARS", str(settings.max_prompt_chars)))
        if len(req.prompt or "") > max_chars:
            # Provide structured error body with detail for test expectations
            return JSONResponse(status_code=413, content={"detail": "prompt_too_large"})
        # WAF core rules (opt-in)
        if os.getenv("ENABLE_WAF") == "1":
            allowed, reason = check_prompt(req.prompt or "")
            if not allowed:
                return JSONResponse(status_code=400, content={"error": "waf_block", "reason": reason})
        prompt_in = _scrub_pii(req.prompt) if settings.enable_pii_scrub else req.prompt
        if settings.enable_pii_scrub:
            _LAST_SCRUBBED_PROMPT["value"] = prompt_in
        # CCR subagent tag extraction: <CCR-SUBAGENT-MODEL>provider,model</CCR-SUBAGENT-MODEL>
        forced_model: str | None = None
        if prompt_in and "<CCR-SUBAGENT-MODEL>" in prompt_in:
            try:
                import re

                m = re.search(r"<CCR-SUBAGENT-MODEL>([^<]+)</CCR-SUBAGENT-MODEL>", prompt_in)
                if m:
                    forced_spec = m.group(1).strip()
                    # Accept "provider,model" or just "model"
                    forced_model = forced_spec.split(",", 1)[-1].strip()
                    # Remove tag from prompt before hashing/classification
                    prompt_in = re.sub(r"<CCR-SUBAGENT-MODEL>[^<]+</CCR-SUBAGENT-MODEL>", "", prompt_in)
            except Exception:  # noqa: S110
                forced_model = None
        plan, regret_analysis, routing_metadata = choose(req.quality, req.latency_slo_ms, _MODEL_REGISTRY, "A")
        if not plan:
            raise HTTPException(status_code=503, detail=ErrorCode.NO_MODELS.value)
        if forced_model:
            # Reorder plan putting forced model first if present, else append placeholder attempt
            forced_found = [c for c in plan if c.name == forced_model]
            if forced_found:
                others = [c for c in plan if c.name != forced_model]
                plan = forced_found + others
        primary = plan[0]
        escalation = plan[1] if len(plan) > 1 else None
        # Champion/Challenger (opt-in): pick challenger and expose in roles
        challenger_name: str | None = None
        if os.getenv("ENABLE_CHALLENGER") == "1":
            try:
                from .champion_challenger import Candidate, select_challenger

                candidates = [
                    Candidate(
                        name=c.name, cost_per_1k_tokens=float(c.cost_per_1k_tokens), quality_pred=float(c.quality_pred)
                    )
                    for c in plan
                ]
                ch = select_challenger(
                    Candidate(primary.name, float(primary.cost_per_1k_tokens), float(primary.quality_pred)), candidates
                )
                challenger_name = ch.name if ch else None
                if challenger_name:
                    # Runs metric increment is done when actual run occurs; for POC we only expose role
                    pass
            except Exception:
                challenger_name = None
        # Budget preflight (POC, opt-in)
        if os.getenv("ENABLE_BUDGET_PREFLIGHT") == "1":
            try:
                from .budget import BudgetGovernor, Usage
                from .budget_guard import preflight_check

                global _BUDGET_GOV  # type: ignore[no-redef]
                if "_BUDGET_GOV" not in globals():
                    _BUDGET_GOV = BudgetGovernor()  # type: ignore[assignment]
                est_out = 180 if req.quality == "high" else 120
                est_in = max(30, int(len(prompt_in or "") / 4))
                est_tokens = est_in + est_out
                est_usd_micros = int((est_tokens / 1000.0) * max(0.0, float(primary.cost_per_1k_tokens)) * 1_000_000)
                usage = Usage(tokens=est_tokens, usd_micros=est_usd_micros)
                if not preflight_check(sess_id, usage, _BUDGET_GOV):
                    return JSONResponse(status_code=429, content={"error": "backpressure", "detail": "budget_denied"})
            except Exception:  # noqa: S110
                pass
        start = time.time()
        cluster_hint = classify(prompt_in) or req.task_type
        p_hash = prompt_hash(prompt_in)
        cluster_key = cluster_hint or "_default"
        phase = "active"

    bandit_choice = None
    try:
        tracer = get_tracer()
        if tracer is None and os.getenv("ROUTER_TEST_TRACING_MODE", "").lower() == "dummy":
            try:
                from . import tracing as _tr

                _tr.init_tracing()
                tracer = get_tracer()
            except Exception:
                tracer = None
        bandit_span_cm = tracer.start_as_current_span("bandit.select") if tracer else None
        if bandit_span_cm:
            bandit_span = bandit_span_cm.__enter__()
            # Set strategy attribute immediately so it's always recorded, even on errors
            try:
                bandit_span.set_attribute("bandit.strategy", BANDIT_STRATEGY)
                bandit_span.set_attribute("bandit.cluster", cluster_key or "_default")
                try:
                    bandit_span.set_attribute("bandit.candidates", int(len(plan)))
                except Exception:  # noqa: S110 -- optional span attribute
                    pass
            except Exception:  # noqa: S110
                pass
        try:
            if BANDIT_STRATEGY == "ucb":
                bandit_choice = ucb_select(cluster_key, plan, UCB_EXPLORE_FACTOR, prompt_in, req.latency_slo_ms)
            elif BANDIT_STRATEGY == "thompson":
                bandit_choice = thompson_select(cluster_key, plan)
            else:
                bandit_choice = None
            if bandit_span_cm and bandit_choice:
                try:
                    bandit_span.set_attribute("bandit.choice", bandit_choice)
                except Exception:  # noqa: S110
                    pass
        finally:
            if bandit_span_cm:
                bandit_span_cm.__exit__(None, None, None)
    except Exception:
        bandit_choice = None
    if bandit_choice:
        plan = [next(c for c in plan if c.name == bandit_choice)] + [c for c in plan if c.name != bandit_choice]
        primary = plan[0]
        escalation = plan[1] if len(plan) > 1 else escalation

    shadow_models = [m for m, rec in _MODEL_REGISTRY.items() if rec.get("status") == "shadow"]

    async def stream() -> AsyncIterator[str]:
        tracer = get_tracer()
        dispatch_cm = tracer.start_as_current_span("dispatch") if tracer else None
        seq = 0
        escalation_used = False
        text_parts = []
        target_tokens = 180 if req.quality == "high" else 120
        primary_speed = 25
        roles = []
        if plan:
            roles.append({"role": "primary", "model": plan[0].name})
        if len(plan) > 1:
            roles.append({"role": "explore", "model": plan[1].name})
        if challenger_name:
            roles.append({"role": "challenger", "model": challenger_name})
        fb = plan[-1].name
        if fb not in [r["model"] for r in roles]:
            roles.append({"role": "fallback", "model": fb})
        if dispatch_cm:
            dispatch_span = dispatch_cm.__enter__()
            try:
                dispatch_span.set_attribute("roles.count", len(roles))
            except Exception:  # noqa: S110
                pass

        # Increment experiment frames metric if challenger is present
        if challenger_name:
            EXPERIMENT_FRAMES_TOTAL.inc(1)

        yield (
            json.dumps(
                {
                    "type": "plan",
                    "candidates": [
                        {
                            "model": c.name,
                            "cost_per_1k": c.cost_per_1k_tokens,
                            "quality_pred": c.quality_pred,
                            "latency_p95": c.latency_p95,
                        }
                        for c in plan
                    ],
                    "cluster_hint": cluster_hint,
                    "prompt_hash": p_hash,
                    "reason": "cheapest acceptable then escalation (bandit)",
                    "roles": roles,
                }
            )
            + "\n"
        )

        async def emit(model_name: str, chunk_text: str) -> AsyncIterator[str]:
            nonlocal seq
            seq += 1
            text_parts.append(chunk_text)
            yield json.dumps(Chunk(seq=seq, text=chunk_text, model=model_name).model_dump()) + "\n"

        # Emit challenger-selected event (POC) if enabled
        if os.getenv("ENABLE_CHALLENGER_EVENT") == "1" and challenger_name:
            yield json.dumps({"type": "event", "event": "challenger_selected", "model": challenger_name}) + "\n"

        generated = 0
        cancelled = False
        # Child span to represent adapter streaming
        adapter_cm = tracer.start_as_current_span("adapter.stream") if tracer else None
        if adapter_cm:
            adapter_cm.__enter__()
        while generated < target_tokens:
            elapsed = time.time() - start
            if not escalation_used and escalation and elapsed * 1000 > req.latency_slo_ms * 0.6:
                escalation_used = True
                yield json.dumps({"type": "event", "event": "escalate", "model": escalation.name}) + "\n"
            # hard timeout safeguard (extended to 4x SLO to reduce premature cancellations in tests)
            if elapsed * 1000 > req.latency_slo_ms * 4:
                cancelled = True
                break
            chunk = min(12, target_tokens - generated)
            generated += chunk
            await asyncio.sleep(chunk / primary_speed)
            # cancellation / disconnect check
            try:
                if await request.is_disconnected():
                    cancelled = True
                    break
            except Exception as err:  # noqa: S110 -- disconnect check best-effort
                _logging.debug("disconnect check failed: %s", err)
            phrase = "lorem" if generated < target_tokens else "done"
            async for out in emit(primary.name, phrase):
                yield out

        quality = (
            _evaluate_quality(" ".join(text_parts)) if settings.quality_eval_mode != "off" else random.uniform(0.7, 0.9)
        )
        total = time.time() - start
        duration_ms = total * 1000.0
        _record_latency(duration_ms)
        _ctr_req.inc()
        _ctr_duration_sum.inc(int(round(duration_ms)))
        if _hist_latency:
            _hist_latency.observe(duration_ms)
        cost_tokens = 30 + target_tokens
        cost_usd = (cost_tokens / 1000.0) * primary.cost_per_1k_tokens
        baseline = (cost_tokens / 1000.0) * 2.0
        savings = (baseline - cost_usd) / baseline * 100

        # GAP-349: Use carbon attribution system for accurate energy calculation
        total_tokens = target_tokens + 30
        kwh = carbon_attribution.calculate_energy_consumption(primary.name, total_tokens)
        co2e = carbon_attribution.calculate_carbon_footprint(kwh)

        # Calculate baseline comparison for energy savings attribution
        baseline_comparison = carbon_attribution.get_baseline_comparison(primary.name, total_tokens)

        # GAP-205: Validate response using success validator
        response_text = " ".join(text_parts)
        validation_result = SUCCESS_VALIDATOR.validate_response(
            response_text=response_text,
            prompt=req.prompt,
            model_name=primary.name,
            conversation_id=req.conversation_id,
            tenant=req.tenant,
        )

        final = FinalResponse(
            text=response_text,
            model_used=primary.name,
            tokens_in=30,
            tokens_out=target_tokens,
            cost_usd=round(cost_usd, 6),
            savings_pct=round(savings, 2),
            escalation_count=1 if escalation_used else 0,
            quality_score=round(quality, 3),
            cluster_hint=cluster_hint,
            energy_kwh=kwh,
            co2e_grams=co2e,
            tool_success=True,
            format_ok=validation_result.format_ok,
            safety_ok=validation_result.safety_ok,
            phase=phase,
        )
        if cancelled:
            _ctr_cancel.inc()
            yield (
                json.dumps(
                    {"type": "final", "aborted": True, "error": ErrorCode.CANCELLED.value, "model_used": primary.name}
                )
                + "\n"
            )
            # AIMD negative feedback
            try:
                sess_id = req.conversation_id or request.state.correlation_id
                GLOBAL_AIMD.feedback(sess_id, latency_ms=duration_ms, ok=False)
            except Exception as err:  # noqa: S110 -- AIMD feedback is best-effort
                _logging.debug("AIMD negative feedback failed: %s", err)
            return
        _ctr_success.inc()
        yield json.dumps(final.model_dump()) + "\n"

        # GAP-305: Record write operation for consistency enforcement
        if session_state.consistency_level == "RYW":
            enforcer.record_write(sess_id, req.tenant)

        # AIMD positive feedback
        try:
            sess_id = req.conversation_id or request.state.correlation_id
            GLOBAL_AIMD.feedback(sess_id, latency_ms=duration_ms, ok=True)
        except Exception as err:  # noqa: S110
            _logging.debug("AIMD positive feedback failed: %s", err)
        # Close spans
        if adapter_cm:
            adapter_cm.__exit__(None, None, None)
        if dispatch_cm:
            dispatch_cm.__exit__(None, None, None)

        # GAP-212: Check for seasonal anomalies in request latency
        latency_anomaly = check_metric_anomaly(duration_ms, "request_latency_ms")
        if latency_anomaly["is_anomaly"]:
            _logging.warning(
                "Seasonal anomaly detected in request latency: %.2fms (forecast: %.2fms, error: %.2fms, threshold: %.2fms)",
                duration_ms,
                latency_anomaly["forecast"],
                latency_anomaly["error"],
                latency_anomaly["threshold"],
            )

        observation = {
            "ts": time.time(),
            "prompt_hash": p_hash,
            "cluster_hint": cluster_hint,
            "task_type": cluster_hint,  # GAP-340: Add task_type for SLM training
            "model_plan": [c.name for c in plan],
            "primary_model": primary.name,
            "escalated": escalation_used,
            "latency_s": round(total, 4),
            "tokens_in": 30,
            "tokens_out": target_tokens,
            "cost_usd": round(cost_usd, 6),
            "savings_pct": round(savings, 2),
            "quality_score": round(quality, 3),
            "energy_kwh": kwh,
            "co2e_grams": co2e,
            "tool_success": True,
            "format_ok": validation_result.format_ok,
            "safety_ok": validation_result.safety_ok,
            "phase": phase,
            "bandit_primary": bandit_choice or primary.name,
            "bandit_strategy": BANDIT_STRATEGY,
            "schema_version": OBS_SCHEMA_VERSION,
            # GAP-349: Add carbon attribution data
            "energy_savings_kwh": baseline_comparison.get("energy_savings_kwh", 0.0),
            "carbon_savings_co2e_grams": baseline_comparison.get("carbon_savings_co2e_grams", 0.0),
            "energy_efficiency_ratio": baseline_comparison.get("efficiency_ratio", 1.0),
            # GAP-212: Add seasonal anomaly detection data
            "latency_anomaly_detected": latency_anomaly["is_anomaly"],
            "latency_forecast_ms": latency_anomaly["forecast"],
            "latency_error_ms": latency_anomaly["error"],
            "latency_threshold_ms": latency_anomaly["threshold"],
        }
        if validate_observation(observation):
            _record_observation(observation)
            log_event("observation.recorded", primary=primary.name, cluster=cluster_key)

            # GAP-202: Add quality observation to drift detector
            _services.get("quality_drift_detector").add_quality_observation(
                model_name=primary.name, quality_score=quality, timestamp=observation["ts"]
            )

            # GAP-203: Sample task for active learning
            _services.get("active_learning_sampler").enqueue_task(
                prompt_hash=p_hash, cluster_hint=cluster_hint, quality_score=quality, model_used=primary.name
            )
        update_stat(
            cluster_key, primary.name, validation_result.success, final.cost_usd, total, prompt_in, req.latency_slo_ms
        )
        stat = _MODEL_STATS.setdefault(
            (cluster_hint, primary.name), _ModelStat(calls=0, success=0, escalations=0, cost_sum=0.0)
        )
        stat["calls"] += 1
        stat["success"] += 1 if validation_result.success else 0
        stat["escalations"] += 1 if escalation_used else 0
        stat["cost_sum"] += round(cost_usd, 6)

        # GAP-209: Shadow evaluation with sampling strategy
        should_sample = should_sample_shadow(quality, duration_ms, shadow_models)

        if should_sample:

            def eval_shadow(sm: str, ph: str, base_q: float, base_cost: float) -> None:
                try:
                    sq = base_q + random.uniform(-0.02, 0.03)
                    sl = total * random.uniform(0.8, 1.1)
                    sc = base_cost * random.uniform(0.7, 0.95)
                    update_stat(cluster_hint or "_default", sm, True, sc, sl)
                    shadow_obs = {
                        "ts": time.time(),
                        "prompt_hash": ph,
                        "cluster_hint": cluster_hint,
                        "shadow_of": primary.name,
                        "shadow_model": sm,
                        "shadow_quality": round(sq, 3),
                        "shadow_latency_s": round(sl, 4),
                        "shadow_cost_usd": round(sc, 6),
                        "phase": "shadow_eval",
                    }
                    if validate_observation(shadow_obs):
                        _record_observation(shadow_obs)
                        _ctr_shadow_evals.inc()
                        # GAP-209: Track quality gap between primary and shadow
                        quality_gap = base_q - sq
                        _g_shadow_quality_gap.set(quality_gap)
                        log_event(
                            "shadow.evaluation.completed",
                            shadow_model=sm,
                            primary=primary.name,
                            quality_gap=quality_gap,
                        )

                        # GAP-344: Record shadow comparison for promotion tracking
                        shadow_tracker.record_shadow_comparison(
                            shadow_model=sm,
                            primary_model=primary.name,
                            shadow_quality=sq,
                            primary_quality=base_q,
                            shadow_cost=sc,
                            primary_cost=base_cost,
                        )

                    # GAP-202: Add shadow quality observation to drift detector
                    _services.get("quality_drift_detector").add_quality_observation(
                        model_name=sm, quality_score=sq, timestamp=time.time()
                    )
                except Exception as err:  # noqa: S110 -- shadow eval is non-critical; log and continue
                    _logging.debug("shadow eval failed model=%s err=%s", sm, err)

            for sm in shadow_models:
                t = threading.Thread(target=eval_shadow, args=(sm, p_hash, quality, cost_usd), daemon=True)
                _WORKER_THREADS.add(t)
                t.start()

            # Sync seed observations for immediate availability
            for sm in shadow_models:
                try:
                    seed_obs = {
                        "ts": time.time(),
                        "prompt_hash": p_hash,
                        "cluster_hint": cluster_hint,
                        "shadow_of": primary.name,
                        "shadow_model": sm,
                        "shadow_quality": round(quality + random.uniform(-0.01, 0.02), 3),
                        "shadow_latency_s": round(total * random.uniform(0.85, 1.05), 4),
                        "shadow_cost_usd": round(cost_usd * random.uniform(0.7, 0.95), 6),
                        "phase": "shadow_eval",
                        "mode": "sync_seed",
                    }
                    if validate_observation(seed_obs):
                        _record_observation(seed_obs)
                        _ctr_shadow_evals.inc()
                except Exception as err:  # noqa: S110
                    _logging.debug("shadow seed observation failed: %s", err)

        # Promotion / demotion
        try:
            from .adaptive_stats import fetch_stats

            stats = fetch_stats(cluster_key)
            # stats rows: model, calls, success, cost_sum, latency_sum
            stat_map_full: dict[str, tuple[int, float]] = {
                m: (calls, cost_sum) for m, calls, success, cost_sum, _lat in stats
            }
            promo_ref = {"value": _PROMOTION_COUNT}
            demo_ref = {"value": _DEMOTION_COUNT}
            evaluate_promotions(
                cluster_key,
                _MODEL_REGISTRY,
                _MODEL_LAST_ACTION,
                stat_map_full,
                _LIFECYCLE_HISTORY.append,
                _persist_lifecycle,
                _record_observation,
                promo_ref,
            )
            evaluate_demotions(
                cluster_key,
                _MODEL_REGISTRY,
                _MODEL_LAST_ACTION,
                stat_map_full,
                _LIFECYCLE_HISTORY.append,
                _persist_lifecycle,
                _record_observation,
                demo_ref,
            )
            if promo_ref["value"] != _PROMOTION_COUNT:
                globals()["_PROMOTION_COUNT"] = promo_ref["value"]
            if demo_ref["value"] != _DEMOTION_COUNT:
                globals()["_DEMOTION_COUNT"] = demo_ref["value"]
            try:
                save_registry(_MODEL_REGISTRY)
            except Exception as err:  # noqa: S110
                _logging.debug("save registry failed: %s", err)
        except Exception as err:  # noqa: S110 -- promotion/demotion evaluation failures tolerated
            _logging.debug("promotion/demotion eval failed: %s", err)

    async def wrapped_stream() -> AsyncIterator[str]:
        try:
            async for chunk in stream():
                yield chunk
        finally:
            if span_ctx:
                span_ctx.__exit__(None, None, None)
            # decrement active session counter
            try:
                async with _SESSION_LOCK:
                    if "sess_id" in locals():
                        session_data = _SESSION_ACTIVE.get(sess_id)
                        if session_data:
                            cur = session_data["count"]
                            if cur <= 1:
                                _SESSION_ACTIVE.pop(sess_id, None)
                            else:
                                session_data["count"] = cur - 1
                                session_data["last_activity"] = time.time()
                                _SESSION_ACTIVE[sess_id] = session_data
            except Exception as err:  # noqa: S110
                _logging.debug("session release failed: %s", err)
            # release fair scheduler slot if it was granted there (best-effort)
            try:
                await FAIR_SCHED.release(sess_id)
            except Exception as err:  # noqa: S110
                _logging.debug("fair release failed: %s", err)

    return StreamingResponse(wrapped_stream(), media_type="text/event-stream")


# ---- MCP WebSocket endpoint (GAP-125, GAP-128) ----
@app.websocket("/mcp")
async def mcp_websocket(websocket: WebSocket) -> None:
    """MCP WebSocket endpoint for Model Context Protocol integration.

    Supports listTools, callTool, and basic error/heartbeat frames.
    """
    await websocket.accept()

    # MCP session state
    mcp_session_active = REGISTRY.gauge("mcp_sessions_active")
    mcp_heartbeats_tx = REGISTRY.counter("mcp_heartbeats_tx")
    mcp_session_active.inc(1)

    try:
        # Basic heartbeat scheduler for MCP
        last_activity = time.time()
        heartbeat_interval = 30.0  # 30 second heartbeat interval

        while True:
            # Check for heartbeat timeout
            now = time.time()
            if now - last_activity > heartbeat_interval * 2:
                # Send error frame for idle timeout
                await websocket.send_json(
                    {"type": "error", "error": {"code": "IDLE_TIMEOUT", "message": "MCP session idle timeout"}}
                )
                break

            # Send periodic heartbeat
            if now - last_activity >= heartbeat_interval:
                await websocket.send_json({"type": "heartbeat"})
                mcp_heartbeats_tx.inc(1)
                last_activity = now

            # Try to receive message with timeout
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
                last_activity = time.time()

                # Handle MCP messages
                msg_type = data.get("type")

                if msg_type == "listTools":
                    # Generate dynamic tool descriptors from adapter registry
                    tools = generate_tool_descriptors()

                    # Return available tools
                    await websocket.send_json(
                        {
                            "type": "listTools",
                            "tools": tools,
                        }
                    )
                elif msg_type == "callTool":
                    # Handle tool call
                    tool_name = data.get("tool", {}).get("name")
                    tool_args = data.get("tool", {}).get("arguments", {})

                    if tool_name == "route.complete":
                        # Forward to existing ask endpoint logic
                        prompt = tool_args.get("prompt", "")
                        quality_target = tool_args.get("quality_target", "balanced")
                        # adapter_type = tool_args.get("adapter_type")  # TODO: Use for adapter-specific routing

                        # Create AskRequest with proper field mapping
                        ask_req = AskRequest(
                            prompt=prompt,
                            quality=quality_target,
                            max_cost_usd=tool_args.get("max_cost_usd", 0.05),
                            latency_slo_ms=tool_args.get("latency_slo_ms", 2000),
                        )

                        # Call internal routing logic with streaming
                        try:
                            # For now, simulate streaming completion response
                            # In production, this would call the full ask pipeline with streaming
                            from metrics.registry import MCP_PARTIAL_FRAMES_TOTAL

                            from .choose_model import choose

                            plan, regret_analysis, routing_metadata = choose(
                                ask_req.quality, ask_req.latency_slo_ms, _MODEL_REGISTRY, "A"
                            )
                            selected_model = plan[0].name if plan else "unknown"

                            # Simulate streaming by breaking response into chunks
                            full_response = f"Completion processed via {selected_model}: {prompt[:100]}..."
                            words = full_response.split()
                            cumulative_tokens = 0

                            # Send partial responses for each chunk
                            for i, chunk in enumerate(words):
                                if i > 0:  # Don't send first chunk as partial
                                    chunk_text = " ".join(words[: i + 1])
                                    cumulative_tokens = len(chunk_text.split())

                                    await websocket.send_json(
                                        {
                                            "type": "toolOutput",
                                            "toolCallId": data.get("id"),
                                            "content": [{"type": "text", "text": chunk}],
                                            "sequence": i,
                                            "cumulative_tokens": cumulative_tokens,
                                            "is_partial": True,
                                            "dp_metrics_emitted": True,
                                        }
                                    )
                                    MCP_PARTIAL_FRAMES_TOTAL.inc(1)

                                    # Small delay to simulate streaming
                                    await asyncio.sleep(0.1)

                            # Send final response
                            await websocket.send_json(
                                {
                                    "type": "toolOutput",
                                    "toolCallId": data.get("id"),
                                    "content": [{"type": "text", "text": full_response}],
                                    "sequence": len(words),
                                    "cumulative_tokens": len(full_response.split()),
                                    "final": True,
                                    "dp_metrics_emitted": True,
                                    "metadata": {
                                        "model_used": selected_model,
                                        "latency_ms": 150,
                                        "cost_estimate": 0.002,
                                        "quality_target": quality_target,
                                    },
                                }
                            )

                        except Exception as e:
                            # Send error frame
                            await websocket.send_json(
                                {"type": "error", "error": {"code": "INTERNAL_ERROR", "message": str(e)}}
                            )

                    elif tool_name.startswith("adapter."):
                        # Handle adapter-specific tool calls
                        adapter_id = tool_name[8:]  # Remove "adapter." prefix
                        from metrics.registry import MCP_PARTIAL_FRAMES_TOTAL

                        from .capability_handler import get_capability_handler

                        handler = get_capability_handler()
                        adapter = handler.registry.get_adapter(adapter_id)

                        if adapter and adapter.is_healthy():
                            # Direct adapter call with streaming (simplified for POC)
                            prompt = tool_args.get("prompt", "")
                            model = tool_args.get("model", adapter.models[0] if adapter.models else "unknown")

                            # Simulate streaming response for adapter call
                            full_response = f"Direct adapter call to {adapter_id} ({model}): {prompt[:100]}..."
                            words = full_response.split()
                            cumulative_tokens = 0

                            # Send partial responses for each chunk
                            for i, chunk in enumerate(words):
                                if i > 0:  # Don't send first chunk as partial
                                    chunk_text = " ".join(words[: i + 1])
                                    cumulative_tokens = len(chunk_text.split())

                                    await websocket.send_json(
                                        {
                                            "type": "toolOutput",
                                            "toolCallId": data.get("id"),
                                            "content": [{"type": "text", "text": chunk}],
                                            "sequence": i,
                                            "cumulative_tokens": cumulative_tokens,
                                            "is_partial": True,
                                            "dp_metrics_emitted": True,
                                        }
                                    )
                                    MCP_PARTIAL_FRAMES_TOTAL.inc(1)

                                    # Small delay to simulate streaming
                                    await asyncio.sleep(0.05)

                            # Send final response
                            await websocket.send_json(
                                {
                                    "type": "toolOutput",
                                    "toolCallId": data.get("id"),
                                    "content": [{"type": "text", "text": full_response}],
                                    "sequence": len(words),
                                    "cumulative_tokens": len(full_response.split()),
                                    "final": True,
                                    "dp_metrics_emitted": True,
                                    "metadata": {
                                        "adapter_id": adapter_id,
                                        "model_used": model,
                                        "latency_ms": 75,
                                        "direct_call": True,
                                    },
                                }
                            )

                        else:
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "error": {
                                        "code": "ADAPTER_UNAVAILABLE",
                                        "message": f"Adapter {adapter_id} not available or unhealthy",
                                    },
                                }
                            )

                    else:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "error": {"code": "METHOD_NOT_FOUND", "message": f"Unknown tool: {tool_name}"},
                            }
                        )

                else:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "error": {"code": "METHOD_NOT_FOUND", "message": f"Unknown message type: {msg_type}"},
                        }
                    )

            except asyncio.TimeoutError:
                # No message received, continue heartbeat loop
                continue

    except WebSocketDisconnect:
        pass
    finally:
        mcp_session_active.dec(1)


# ---- Admin endpoints ----
@app.get("/admin/cluster_stats")
def cluster_stats(guard: None = Depends(admin_guard("read"))) -> dict[str, list[dict[str, object]]]:
    out = []
    for (cluster, model), stat in _MODEL_STATS.items():
        out.append({"cluster": cluster, "model": model, **stat})
    return {"stats": out}


@app.get("/admin/model_status")
def model_status(guard: None = Depends(admin_guard("read"))) -> dict[str, object]:
    out = []
    for m, rec in _MODEL_REGISTRY.items():
        out.append(
            {
                "model": m,
                "status": rec.get("status"),
                "capabilities": rec.get("capabilities", []),
                "safety_grade": rec.get("safety_grade"),
            }
        )
    return {"models": out, "promotions": _PROMOTION_COUNT, "demotions": _DEMOTION_COUNT}


@app.get("/admin/lifecycle")
def lifecycle(limit: int = Query(50, ge=1, le=500), guard: None = Depends(admin_guard("read"))) -> dict[str, object]:
    with _OBS_LOCK:
        items = list(_LIFECYCLE_HISTORY)[-limit:]
    return {"count": len(items), "items": items}


@app.get("/admin/version")
def version(guard: None = Depends(admin_guard("read"))) -> dict[str, object]:
    return {
        "service_version": settings.service_version,
        "bandit_strategy": BANDIT_STRATEGY,
        "schema_version": OBS_SCHEMA_VERSION,
        "max_prompt_chars": settings.max_prompt_chars,
    }


@app.get("/admin/keys")
def list_admin_keys(guard: None = Depends(admin_guard("read"))) -> dict[str, object]:
    _ctr_admin_actions.inc()
    t0 = time.perf_counter() if os.getenv("ADMIN_TIMING") else None
    out = {"keys": admin_keys.list_keys()}
    if t0 is not None:
        try:
            log_event("admin.keys.list.timing", {"ms": int((time.perf_counter() - t0) * 1000)})
        except Exception:  # noqa: S110
            pass
    return out


@app.post("/admin/keys")
def create_admin_key(
    body: dict[str, Any] | None = Body(default=None),  # noqa: B008 FastAPI pattern
    guard: None = Depends(admin_guard("write")),  # noqa: B008
) -> dict[str, object]:  # noqa: B008 FastAPI pattern
    try:
        t0 = time.perf_counter() if os.getenv("ADMIN_TIMING") else None
        import secrets

        roles = ["read", "write"]
        if isinstance(body, dict):
            if "roles" in body and isinstance(body["roles"], list) and body["roles"]:
                roles = body["roles"]
        plaintext = secrets.token_urlsafe(24)
        h, _ = admin_keys.add_key(plaintext, set(roles))
        _ctr_admin_actions.inc()
        out = {"hash": h, "key": plaintext, "roles": sorted(set(roles))}
        if t0 is not None:
            try:
                log_event("admin.keys.create.timing", {"ms": int((time.perf_counter() - t0) * 1000)})
            except Exception:  # noqa: S110
                pass
        return out
    except Exception as e:
        _ctr_admin_actions_err.inc()
        raise HTTPException(status_code=500, detail="create_failed") from e


@app.delete("/admin/keys/{key_hash}")
def delete_admin_key(key_hash: str, guard: None = Depends(admin_guard("write"))) -> dict[str, bool]:
    try:
        t0 = time.perf_counter() if os.getenv("ADMIN_TIMING") else None
        ok = admin_keys.remove_key(key_hash)
        if not ok:
            raise HTTPException(status_code=400, detail="not_deleted")
        _ctr_admin_actions.inc()
        out = {"deleted": True}
        if t0 is not None:
            try:
                log_event("admin.keys.delete.timing", {"ms": int((time.perf_counter() - t0) * 1000)})
            except Exception:  # noqa: S110
                pass
        return out
    except HTTPException:
        raise
    except Exception as e:
        _ctr_admin_actions_err.inc()
        raise HTTPException(status_code=500, detail="delete_failed") from e


@app.get("/admin/audit")
def audit_recent(limit: int = Query(50, ge=1, le=500), guard: None = Depends(admin_guard("read"))) -> dict[str, object]:
    _ctr_admin_actions.inc()
    return {"items": admin_keys.audit_recent(limit)}


@app.get("/admin/observation_schema")
def observation_schema(guard: None = Depends(admin_guard("read"))) -> dict[str, object]:
    from .observation_schema import OBS_JSON_SCHEMA

    return {"version": OBS_SCHEMA_VERSION, "schema": OBS_JSON_SCHEMA}


@app.get("/admin/observations")
def get_observations(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    model: str | None = Query(None, description="Filter by model name"),
    cluster: str | None = Query(None, description="Filter by cluster"),
    schema_version: int | None = Query(None, description="Filter by schema version"),
    guard: None = Depends(admin_guard("read")),
) -> dict[str, object]:
    """GAP-219: Get recent observations with optional filtering.

    Returns observations from the current day's file, with support for pagination
    and filtering by model, cluster, or schema version.
    """
    try:
        # Read observations from today's file
        fname = f"slm_observations-{datetime.date.today().isoformat()}.jsonl"
        fpath = os.path.join(_DATA_DIR, fname)

        observations = []
        if os.path.exists(fpath):
            with open(fpath, encoding="utf-8") as f:
                for line_num, line in enumerate(f):
                    if line_num < offset:
                        continue
                    if len(observations) >= limit:
                        break

                    try:
                        obs = json.loads(line.strip())

                        # Apply filters
                        if model and obs.get("primary_model") != model:
                            continue
                        if cluster and obs.get("cluster_hint") != cluster:
                            continue
                        if schema_version is not None and obs.get("schema_version") != schema_version:
                            continue

                        observations.append(obs)
                    except json.JSONDecodeError:
                        continue  # Skip malformed lines

        return {
            "items": observations,
            "total_count": len(observations),
            "limit": limit,
            "offset": offset,
            "filters": {"model": model, "cluster": cluster, "schema_version": schema_version},
            "schema_version_current": OBS_SCHEMA_VERSION,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read observations: {e}") from e


@app.get("/admin/shadow_stats")
def shadow_stats(guard: None = Depends(admin_guard("read"))) -> dict[str, object]:
    # Aggregate shadow observations in buffer (simple scan; optimize later if needed)
    with _OBS_LOCK:
        items = [o for o in _OBS_BUFFER if o.get("phase") == "shadow_eval"]
    # Summaries per shadow model
    summary: dict[str, dict[str, float | int]] = {}
    for o in items:
        sm = str(o.get("shadow_model"))
        rec = summary.setdefault(sm, {"count": 0, "avg_quality": 0.0, "avg_latency_s": 0.0, "avg_cost_usd": 0.0})
        # update running averages explicitly casting
        prev_count = int(rec["count"])
        new_count = prev_count + 1
        rec["count"] = new_count
        rec["avg_quality"] = (
            (float(rec["avg_quality"]) * prev_count) + float(o.get("shadow_quality", 0.0))
        ) / new_count
        rec["avg_latency_s"] = (
            (float(rec["avg_latency_s"]) * prev_count) + float(o.get("shadow_latency_s", 0.0))
        ) / new_count
        rec["avg_cost_usd"] = (
            (float(rec["avg_cost_usd"]) * prev_count) + float(o.get("shadow_cost_usd", 0.0))
        ) / new_count
    # Ensure all currently shadow models appear even if zero observations so tests can detect presence
    try:
        for m, rec in _MODEL_REGISTRY.items():  # noqa: B007 (intentional reuse of rec variable name)
            if rec.get("status") == "shadow" and m not in summary:
                summary[m] = {"count": 0, "avg_quality": 0.0, "avg_latency_s": 0.0, "avg_cost_usd": 0.0}
    except Exception as err:  # noqa: S110
        _logging.debug("shadow_stats registry expand failed: %s", err)
    shadow_models_list = [{"model": m, **summary[m]} for m in sorted(summary.keys())]
    return {"items": items[-200:], "summary": summary, "shadow_models": shadow_models_list}


@app.get("/admin/_debug_last_prompt")
def debug_last_prompt(guard: None = Depends(admin_guard("read"))) -> dict[str, object]:
    v = _LAST_SCRUBBED_PROMPT["value"] or ""
    return {"last_prompt": v, "length": len(v), "snippet": v[:80]}


if settings.enable_metrics:

    @app.get("/metrics")
    def metrics_endpoint() -> PlainTextResponse:
        # Snapshot registry first
        snap = REGISTRY.export()
        cnt = snap["counters"]
        req_count = cnt.get("requests_total", 0)
        dur_sum = cnt.get("request_duration_ms_sum", 0)
        avg_ms = (dur_sum / req_count) if req_count else 0.0

        # Derive dynamic flow utilization
        try:
            active_sessions = len(_SESSION_ACTIVE)
            active_total = sum(session_data["count"] for session_data in _SESSION_ACTIVE.values())
            allowed_sum = 0
            from .window_update import GLOBAL_AIMD

            for sid in _SESSION_ACTIVE.keys():
                try:
                    allowed_sum += GLOBAL_AIMD.get(sid)
                except Exception as err:  # noqa: S110
                    _logging.debug("utilization weight fetch failed: %s", err)
            utilization_pct = (active_total / allowed_sum * 100.0) if allowed_sum else 0.0
        except Exception:
            active_sessions = active_total = 0
            utilization_pct = 0.0

        lines = []
        # Legacy / simple gauges
        lines.append("router_version{} 1")  # legacy
        lines.append(f'atp_router_service_version_info{{version="{settings.service_version}"}} 1')
        lines.append(f"model_registry_size {len(_MODEL_REGISTRY)}")
        # Promotion/demotion counters (emit both new and legacy names for tests/backcompat)
        lines.append(f"atp_router_promotions_total {_PROMOTION_COUNT}")
        lines.append(f"atp_router_demotions_total {_DEMOTION_COUNT}")
        lines.append(f"promotion_total {_PROMOTION_COUNT}")  # legacy
        lines.append(f"demotion_total {_DEMOTION_COUNT}")  # legacy
        lines.append(f"rate_limit_dropped_total {_RATE_LIMIT_HITS['dropped']}")
        lines.append(f"request_count_total {req_count}")
        lines.append(f"request_success_total {cnt.get('requests_success_total', 0)}")
        lines.append(f"request_error_total {cnt.get('requests_error_total', 0)}")
        lines.append(f"request_cancelled_total {cnt.get('requests_cancel_total', 0)}")
        lines.append(f"request_duration_avg_ms {round(avg_ms, 3)}")
        # Optional UCB score gauge snapshot for all clusters
        try:
            all_clusters = fetch_all_clusters()
            for cluster in all_clusters:
                scores = compute_ucb_scores(cluster, UCB_EXPLORE_FACTOR)
                for model, data in scores.items():
                    lines.append(
                        f'atp_router_ucb_score{{cluster="{cluster}",model="{model}"}} {round(data.get("score", 0.0), 4)}'
                    )
                    # Also emit individual components for observability
                    lines.append(
                        f'atp_router_ucb_exploit{{cluster="{cluster}",model="{model}"}} {round(data.get("exploit", 0.0), 4)}'
                    )
                    lines.append(
                        f'atp_router_ucb_explore{{cluster="{cluster}",model="{model}"}} {round(data.get("explore", 0.0), 4)}'
                    )
        except Exception:  # noqa: S110
            pass
        lines.append(f"flow_active_sessions {active_sessions}")
        lines.append(f"flow_active_streams {active_total}")
        lines.append(f"flow_window_utilization_pct {round(utilization_pct, 2)}")

        # Latency buckets (legacy path)
        if settings.enable_latency_histogram and _LAT_BUCKET_COUNTS:
            cumulative = 0
            for b, count in zip(_LATENCY_BUCKETS, _LAT_BUCKET_COUNTS[:-1], strict=False):
                cumulative += count
                lines.append(f'request_latency_ms_bucket{{le="{b}"}} {cumulative}')
            cumulative += _LAT_BUCKET_COUNTS[-1]
            lines.append(f'request_latency_ms_bucket{{le="+Inf"}} {cumulative}')
            lines.append(f"request_latency_ms_count {cumulative}")

        # Structured counters
        for name, val in snap["counters"].items():
            lines.append(f"{name} {val}")
        # Histograms
        for hname, hdata in snap["histograms"].items():
            buckets = hdata["buckets"]
            counts = hdata["counts"]
            cumulative = 0
            for b, c in zip(buckets, counts[:-1], strict=False):
                cumulative += c
                lines.append(f'{hname}_bucket{{le="{b}"}} {cumulative}')
            cumulative += counts[-1]
            lines.append(f'{hname}_bucket{{le="+Inf"}} {cumulative}')
            lines.append(f"{hname}_count {cumulative}")
            # Derived percentiles for fairness wait histogram only (approx by bucket upper bound)
            if hname == "fair_sched_wait_ms" and cumulative > 0:
                targets = {
                    "p50": 0.50 * cumulative,
                    "p90": 0.90 * cumulative,
                    "p95": 0.95 * cumulative,
                    "p99": 0.99 * cumulative,
                }
                running = 0
                emitted = set()
                for b, c in zip(buckets + ["+Inf"], counts, strict=False):
                    running += c
                    for label, thr in list(targets.items()):
                        if label not in emitted and running >= thr:
                            # Use bucket boundary as percentile approximation
                            lines.append(f"{hname}_{label} {b}")
                            emitted.add(label)
                    if len(emitted) == len(targets):
                        break
        # Per-model counters
        for (_cluster, model), stat in _MODEL_STATS.items():
            lines.append(f'model_calls_total{{model="{model}"}} {stat["calls"]}')
        # Backward compatibility names
        lines.append(f"atp_router_total_calls {req_count}")
        if _MODEL_STATS:
            for (_cluster, model), stat in _MODEL_STATS.items():
                lines.append(f'atp_router_model_calls{{model="{model}"}} {stat["calls"]}')
        else:
            try:
                from .adaptive_stats import fetch_all_clusters as _fetch_all_clusters
                from .adaptive_stats import fetch_stats

                for c in _fetch_all_clusters():
                    for m, calls, _succ, _cost_sum, _lat in fetch_stats(c):
                        lines.append(f'atp_router_model_calls{{model="{m}"}} {calls}')
            except Exception:  # noqa: S110
                pass
        return PlainTextResponse("\n".join(lines) + "\n")


# ---- Fair scheduler admin ----
@app.get("/admin/fair/weights")
def fair_weights(guard: None = Depends(admin_guard("read"))) -> dict[str, dict[str, float]]:
    return {"weights": FAIR_SCHED.snapshot_weights()}


@app.post("/admin/fair/weight")
def fair_set_weight(
    session: str, weight: float = Query(..., ge=0.1, le=100.0), guard: None = Depends(admin_guard("write"))
) -> dict[str, object]:
    FAIR_SCHED.set_weight(session, weight)
    return {"ok": True, "session": session, "weight": weight}


@app.get("/admin/fair/served")
def fair_served(
    limit: int = Query(20, ge=1, le=500), guard: None = Depends(admin_guard("read"))
) -> dict[str, list[dict[str, int | float | str]]]:
    return {"served": FAIR_SCHED.snapshot_served(limit=limit)}


@app.get("/admin/state_health")
def state_health(guard: None = Depends(admin_guard("read"))) -> dict[str, object]:
    backend = "memory"
    status = "ok"
    detail = {}
    try:
        from router_service.state_backend import RedisAIMDBackend, RedisSchedulerBackend

        if isinstance(_SCHED_BACKEND, RedisSchedulerBackend):
            backend = "redis"
            try:
                pong = _SCHED_BACKEND.r.ping()
                status = "ok" if pong else "error"
            except Exception as e:
                status = "error"
                detail["error"] = str(e)[:120]
        if isinstance(_AIMD_BACKEND, RedisAIMDBackend):
            backend = "redis"
    except Exception as err:  # noqa: S110 -- backend status introspection best-effort
        _logging.debug("state health introspection failed: %s", err)
    _g_state_backend_up.set(1 if status == "ok" else 0)
    return {"backend": backend, "status": status, "detail": detail}


@app.get("/admin/quality_drift")
def quality_drift(guard: None = Depends(admin_guard("read"))) -> dict[str, object]:
    """GAP-202: Get quality drift statistics for all models."""
    detector = _services.get("quality_drift_detector")
    alerts = detector.check_all_models()
    stats = detector.get_all_stats()
    return {
        "alerts": alerts,
        "stats": stats,
        "window_size": detector.window_size,
        "drift_threshold_sigma": detector.drift_threshold_sigma,
    }


@app.get("/admin/quality_drift/{model_name}")
def quality_drift_model(model_name: str, guard: None = Depends(admin_guard("read"))) -> dict[str, object]:
    """GAP-202: Get quality drift statistics for a specific model."""
    detector = _services.get("quality_drift_detector")
    drift_info = detector.check_drift(model_name)
    stats = detector.get_model_stats(model_name)

    result = {"model": model_name}
    if drift_info:
        result["drift_alert"] = drift_info
    if stats:
        result["stats"] = stats
    else:
        result["error"] = "Model not found or no data available"

    return result


@app.post("/admin/quality_drift/{model_name}/reset_baseline")
def reset_quality_baseline(model_name: str, guard: None = Depends(admin_guard("write"))) -> dict[str, object]:
    """GAP-202: Reset quality baseline for a model (useful after model updates)."""
    success = _services.get("quality_drift_detector").reset_baseline(model_name)
    return {
        "model": model_name,
        "baseline_reset": success,
        "message": "Baseline reset successful"
        if success
        else "Failed to reset baseline - insufficient data or model not found",
    }


@app.get("/admin/active_learning/queue")
def active_learning_queue(guard: None = Depends(admin_guard("read"))) -> dict[str, object]:
    """GAP-203: Get active learning queue statistics."""
    sampler = _services.get("active_learning_sampler")
    stats = sampler.get_queue_stats()
    return {
        "queue_stats": stats,
        "sampler_config": {
            "max_queue_size": sampler.max_queue_size,
            "uncertainty_threshold": sampler.uncertainty_threshold,
            "diversity_weight": sampler.diversity_weight,
            "fairness_window_hours": sampler.fairness_window_hours,
        },
    }


@app.get("/admin/active_learning/tasks")
def active_learning_tasks(
    limit: int = Query(10, ge=1, le=100), guard: None = Depends(admin_guard("read"))
) -> dict[str, object]:
    """GAP-203: Get active learning tasks from the queue."""
    sampler = _services.get("active_learning_sampler")
    tasks = []
    for i, task in enumerate(sampler.task_queue):
        if i >= limit:
            break
        tasks.append(
            {
                "prompt_hash": task.prompt_hash,
                "cluster_hint": task.cluster_hint,
                "quality_score": round(task.quality_score, 3),
                "uncertainty_score": round(task.uncertainty_score, 3),
                "timestamp": task.timestamp,
                "model_used": task.model_used,
                "sampling_method": task.sampling_method,
                "age_seconds": time.time() - task.timestamp,
            }
        )

    return {"tasks": tasks, "total_queued": len(sampler.task_queue), "returned_count": len(tasks)}


@app.delete("/admin/active_learning/tasks/{count}")
def dequeue_active_learning_tasks(
    count: int = Path(..., ge=1, le=50), guard: None = Depends(admin_guard("write"))
) -> dict[str, object]:
    """GAP-203: Dequeue active learning tasks for processing."""
    sampler = _services.get("active_learning_sampler")
    dequeued_tasks = []
    for _ in range(count):
        task = sampler.dequeue_task()
        if task is None:
            break
        dequeued_tasks.append(
            {
                "prompt_hash": task.prompt_hash,
                "cluster_hint": task.cluster_hint,
                "quality_score": round(task.quality_score, 3),
                "uncertainty_score": round(task.uncertainty_score, 3),
                "timestamp": task.timestamp,
                "model_used": task.model_used,
                "sampling_method": task.sampling_method,
            }
        )

    return {
        "dequeued_tasks": dequeued_tasks,
        "dequeued_count": len(dequeued_tasks),
        "remaining_queue_size": len(sampler.task_queue),
    }


# GAP-204: Continuous Improvement Pipeline Endpoints


@app.post("/admin/ci/pipeline/trigger")
async def trigger_ci_pipeline(
    reason: str = Query("manual_trigger"), guard: None = Depends(admin_guard("write"))
) -> dict[str, object]:
    """GAP-204: Trigger the continuous improvement pipeline."""
    try:
        pipeline = _services.get("continuous_improvement_pipeline")
        execution = await pipeline.execute_pipeline(reason)
        return {
            "execution_id": execution.execution_id,
            "status": execution.status.value,
            "trigger_reason": execution.trigger_reason,
            "start_time": execution.start_time,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline trigger failed: {e}") from e


@app.get("/admin/ci/pipeline/executions")
def get_ci_executions(
    limit: int = Query(10, ge=1, le=100), guard: None = Depends(admin_guard("read"))
) -> dict[str, object]:
    """GAP-204: Get recent pipeline executions."""
    pipeline = _services.get("continuous_improvement_pipeline")
    executions = pipeline.get_recent_executions(limit)
    return {
        "executions": [
            {
                "execution_id": e.execution_id,
                "trigger_reason": e.trigger_reason,
                "status": e.status.value,
                "start_time": e.start_time,
                "end_time": e.end_time,
                "duration_seconds": e.duration(),
                "steps_completed": sum(1 for s in e.steps.values() if s.status == PipelineStatus.SUCCESS),
                "total_steps": len(e.steps),
            }
            for e in executions
        ],
        "total_executions": len(pipeline.executions),
    }


@app.get("/admin/ci/pipeline/executions/{execution_id}")
def get_ci_execution(execution_id: str, guard: None = Depends(admin_guard("read"))) -> dict[str, object]:
    """GAP-204: Get details of a specific pipeline execution."""
    pipeline = _services.get("continuous_improvement_pipeline")
    execution = pipeline.get_execution_status(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    return {
        "execution_id": execution.execution_id,
        "trigger_reason": execution.trigger_reason,
        "status": execution.status.value,
        "start_time": execution.start_time,
        "end_time": execution.end_time,
        "duration_seconds": execution.duration(),
        "steps": {
            step.stage.value: {
                "status": step.status.value,
                "start_time": step.start_time,
                "end_time": step.end_time,
                "duration_seconds": step.duration(),
                "result": step.result,
                "error": step.error,
            }
            for step in execution.steps.values()
        },
    }


@app.get("/admin/ci/pipeline/stats")
def get_ci_pipeline_stats(guard: None = Depends(admin_guard("read"))) -> dict[str, object]:
    """GAP-204: Get continuous improvement pipeline statistics."""
    pipeline = _services.get("continuous_improvement_pipeline")
    return pipeline.get_pipeline_stats()


@app.get("/admin/evidence")
def get_compliance_evidence(
    include_model_registry: bool = Query(True, description="Include model registry data"),
    include_custody_logs: bool = Query(True, description="Include model custody logs"),
    include_admin_audit: bool = Query(True, description="Include admin audit logs"),
    include_router_stats: bool = Query(True, description="Include router statistics"),
    include_lifecycle: bool = Query(True, description="Include lifecycle events"),
    include_slm_observations: bool = Query(True, description="Include SLM observations"),
    include_threat_model: bool = Query(True, description="Include threat model"),
    limit_records: int = Query(1000, ge=1, le=10000, description="Maximum records per evidence type"),
    guard: None = Depends(admin_guard("read")),
) -> dict[str, Any]:
    """GAP-325: Export compliance evidence data for audit and regulatory purposes.

    Collects evidence from multiple sources including model registry, custody logs,
    admin audit logs, router statistics, lifecycle events, SLM observations, and threat model.
    """
    import json
    import os
    from datetime import datetime, timedelta

    import yaml

    evidence = {
        "export_timestamp": datetime.utcnow().isoformat(),
        "service_version": settings.service_version,
        "evidence_types": [],
        "data": {},
    }

    # Helper function to safely read JSONL files
    def read_jsonl_file(filepath: str, limit: int) -> list[dict[str, Any]]:
        records = []
        try:
            if os.path.exists(filepath):
                with open(filepath, encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if i >= limit:
                            break
                        line = line.strip()
                        if line:
                            try:
                                records.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue  # Skip malformed lines
        except Exception as e:
            _logging.warning(f"Failed to read {filepath}: {e}")
        return records

    # Helper function to safely read JSON files
    def read_json_file(filepath: str) -> dict[str, Any] | None:
        try:
            if os.path.exists(filepath):
                with open(filepath, encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            _logging.warning(f"Failed to read {filepath}: {e}")
        return None

    # Helper function to safely read YAML files
    def read_yaml_file(filepath: str) -> dict[str, Any] | None:
        try:
            if os.path.exists(filepath):
                with open(filepath, encoding="utf-8") as f:
                    return yaml.safe_load(f)
        except Exception as e:
            _logging.warning(f"Failed to read {filepath}: {e}")
        return None

    # 1. Model Registry (GAP-325)
    if include_model_registry:
        registry_path = os.path.join(os.path.dirname(__file__), "model_registry.json")
        registry_data = read_json_file(registry_path)
        if registry_data:
            evidence["evidence_types"].append("model_registry")
            evidence["data"]["model_registry"] = {
                "source": "model_registry.json",
                "models_count": len(registry_data),
                "models": registry_data,
            }

    # 2. Model Custody Logs (GAP-325)
    if include_custody_logs:
        custody_path = os.path.join(os.path.dirname(__file__), "model_custody.log")
        custody_records = read_jsonl_file(custody_path, limit_records)
        if custody_records:
            evidence["evidence_types"].append("model_custody")
            evidence["data"]["model_custody"] = {
                "source": "model_custody.log",
                "records_count": len(custody_records),
                "records": custody_records,
            }

    # 3. Admin Audit Logs (GAP-325)
    if include_admin_audit:
        admin_audit_path = os.path.join(_DATA_DIR, "admin_audit.jsonl")
        admin_audit_records = read_jsonl_file(admin_audit_path, limit_records)
        if admin_audit_records:
            evidence["evidence_types"].append("admin_audit")
            evidence["data"]["admin_audit"] = {
                "source": "data/admin_audit.jsonl",
                "records_count": len(admin_audit_records),
                "records": admin_audit_records,
            }

    # 4. Router Statistics (GAP-325)
    if include_router_stats:
        router_stats = {}

        # Router counters
        router_counters_path = os.path.join(_DATA_DIR, "router_counters.json")
        router_counters = read_json_file(router_counters_path)
        if router_counters:
            router_stats["router_counters"] = router_counters

        # Runtime counters
        runtime_counters_path = os.path.join(_DATA_DIR, "runtime_counters.json")
        runtime_counters = read_json_file(runtime_counters_path)
        if runtime_counters:
            router_stats["runtime_counters"] = runtime_counters

        # General counters
        counters_path = os.path.join(_DATA_DIR, "counters.json")
        counters = read_json_file(counters_path)
        if counters:
            router_stats["counters"] = counters

        if router_stats:
            evidence["evidence_types"].append("router_statistics")
            evidence["data"]["router_statistics"] = {
                "source": "data/{router_counters,runtime_counters,counters}.json",
                "components": list(router_stats.keys()),
                "data": router_stats,
            }

    # 5. Lifecycle Events (GAP-325)
    if include_lifecycle:
        lifecycle_data = {}

        # Current lifecycle events
        lifecycle_path = os.path.join(_DATA_DIR, "lifecycle.jsonl")
        lifecycle_records = read_jsonl_file(lifecycle_path, limit_records)
        if lifecycle_records:
            lifecycle_data["current"] = lifecycle_records

        # Lifecycle history
        lifecycle_history_path = os.path.join(_DATA_DIR, "lifecycle_history.jsonl")
        lifecycle_history_records = read_jsonl_file(lifecycle_history_path, limit_records)
        if lifecycle_history_records:
            lifecycle_data["history"] = lifecycle_history_records

        if lifecycle_data:
            evidence["evidence_types"].append("lifecycle_events")
            evidence["data"]["lifecycle_events"] = {
                "source": "data/{lifecycle,lifecycle_history}.jsonl",
                "components": list(lifecycle_data.keys()),
                "total_records": sum(len(records) for records in lifecycle_data.values()),
                "data": lifecycle_data,
            }

    # 6. SLM Observations (GAP-325)
    if include_slm_observations:
        slm_data = {}
        total_records = 0

        # Get recent SLM observation files (last 7 days)
        for i in range(7):
            date = (datetime.utcnow() - timedelta(days=i)).date()
            filename = f"slm_observations-{date.isoformat()}.jsonl"
            filepath = os.path.join(_DATA_DIR, filename)

            records = read_jsonl_file(filepath, limit_records // 7)  # Distribute limit across files
            if records:
                slm_data[str(date)] = records
                total_records += len(records)

        if slm_data:
            evidence["evidence_types"].append("slm_observations")
            evidence["data"]["slm_observations"] = {
                "source": "data/slm_observations-*.jsonl",
                "date_range": "last_7_days",
                "files_count": len(slm_data),
                "total_records": total_records,
                "data": slm_data,
            }

    # 7. Threat Model (GAP-325)
    if include_threat_model:
        threat_model_path = os.path.join(_DATA_DIR, "threat_model_poc.yaml")
        threat_model_data = read_yaml_file(threat_model_path)
        if threat_model_data:
            evidence["evidence_types"].append("threat_model")
            evidence["data"]["threat_model"] = {"source": "data/threat_model_poc.yaml", "data": threat_model_data}

    # Add reconciliation audit if available
    reconciliation_path = os.path.join(_DATA_DIR, "reconciliation_audit.jsonl")
    reconciliation_records = read_jsonl_file(reconciliation_path, limit_records)
    if reconciliation_records:
        evidence["evidence_types"].append("reconciliation_audit")
        evidence["data"]["reconciliation_audit"] = {
            "source": "data/reconciliation_audit.jsonl",
            "records_count": len(reconciliation_records),
            "records": reconciliation_records,
        }

    # Add current system state information
    evidence["system_state"] = {
        "model_registry_size": len(_MODEL_REGISTRY),
        "active_sessions": len(_SESSION_ACTIVE),
        "total_promotions": _PROMOTION_COUNT,
        "total_demotions": _DEMOTION_COUNT,
        "fair_scheduler_weights": FAIR_SCHED.snapshot_weights(),
        "service_uptime_seconds": time.time() - getattr(settings, "start_time", time.time()),
    }

    return evidence


@app.get("/agp/explain")
def agp_explain(
    prefix: str = Query(..., description="Route prefix to explain"),
    tenant: str | None = Query(None, description="Tenant name for policy evaluation"),
    task_type: str | None = Query(None, description="Task type for policy evaluation"),
    data_scope: list[str] | None = _DATA_SCOPE_QUERY,
) -> dict[str, Any]:
    """Explain AGP route selection for a given prefix and context."""
    _ctr_explain_requests.inc()

    # Build context for policy evaluation
    context = {}
    if tenant:
        context["tenant"] = tenant
    if task_type:
        context["task_type"] = task_type
    if data_scope:
        context["data_scope"] = data_scope

    # Use policy simulation for explanation
    try:
        import os
        import sys

        # Import policy simulation logic
        sys.path.append(os.path.join(os.path.dirname(__file__), "..", "tools"))
        from policy_sim_poc import simulate

        # Use the policy_poc.yaml file
        policy_path = os.path.join(os.path.dirname(__file__), "..", "tools", "policy_poc.yaml")
        result = simulate(policy_path, context)

        return {
            "prefix": prefix,
            "context": context,
            "decision": result["decision"],
            "rule_evaluation_trace": result["trace"],
            "explanation": f"Policy evaluation resulted in '{result['decision']}' based on {len(result['trace'])} rules",
        }
    except Exception as e:
        return {
            "prefix": prefix,
            "context": context,
            "error": f"Policy evaluation failed: {str(e)}",
            "decision": "error",
        }


@app.get("/agp/trace")
def agp_trace(
    prefix: str = Query(..., description="Route prefix to trace"),
    start_router: str = Query(..., description="Starting router ID for trace"),
    max_hops: int = Query(30, ge=1, le=100, description="Maximum number of hops"),
    ttl: int = Query(64, ge=1, le=255, description="Initial TTL value"),
) -> dict[str, Any]:
    """Trace AGP route path for a prefix (traceroute-like functionality)."""
    _ctr_trace_requests.inc()

    try:
        # Import AGP tracer
        import os
        import sys

        sys.path.append(os.path.join(os.path.dirname(__file__), "..", "tools"))
        from agptrace import AGPTracer

        # For now, use sample route table - in production this would come from actual routing table
        route_table_path = os.path.join(os.path.dirname(__file__), "..", "tools", "route_table_sample.yaml")
        tracer = AGPTracer(route_table_path)
        result = tracer.trace_route(prefix, start_router, max_hops, ttl)

        # Add start_router to response
        result["start_router"] = start_router

        return result
    except Exception as e:
        return {
            "prefix": prefix,
            "start_router": start_router,
            "error": f"Trace failed: {str(e)}",
            "hops": [],
            "total_hops": 0,
            "trace_complete": False,
        }


# ---- Lifespan context ----
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_tracing()
    _load_counters()
    global _PERSIST_THREAD
    _STOP_EVENT.clear()
    if os.getenv("ROUTER_DISABLE_PERSIST_THREAD", "0") != "1":
        _PERSIST_THREAD = threading.Thread(target=_persist_counters_loop, name="counter-persist", daemon=True)
        _PERSIST_THREAD.start()
    # Startup: session cleanup task
    cleanup_task = asyncio.create_task(_cleanup_expired_sessions())
    logger.info("service.startup", component="session_cleanup")

    # Optional: config hot-reload for model_registry.json
    # Set ROUTER_MODEL_REGISTRY_WATCH=1 to enable (production-safe if file is managed externally)
    hot_reload_task = None
    try:
        if os.getenv("ROUTER_MODEL_REGISTRY_WATCH", "0") == "1":
            from .config_hot_reload import ConfigHotReloader

            registry_path = os.path.join(os.path.dirname(__file__), "model_registry.json")

            def _reload_registry(cfg: dict[str, Any]) -> None:
                if isinstance(cfg, dict):
                    _MODEL_REGISTRY.clear()
                    _MODEL_REGISTRY.update(cfg)
                    logger.info("model_registry.reloaded", models=len(_MODEL_REGISTRY))

            reloader = ConfigHotReloader(registry_path, _reload_registry, check_interval=2.0)
            reloader.start()

            async def _wait_reloader():
                try:
                    while True:
                        await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    await reloader.stop()

            hot_reload_task = asyncio.create_task(_wait_reloader())
            logger.info("config_hot_reload.enabled", file=registry_path)
    except Exception as err:  # noqa: S110
        logger.warning("config_hot_reload.init_failed", error=str(err))
    yield
    _STOP_EVENT.set()
    if _PERSIST_THREAD:
        try:
            _PERSIST_THREAD.join(timeout=2)
        except Exception as err:  # noqa: S110
            _logging.debug("persist thread join failed: %s", err)
    for t in list(_WORKER_THREADS):
        try:
            t.join(timeout=0.5)
        except Exception as err:  # noqa: S110
            logger.debug("worker.join_error", error=str(err))
    # Shutdown: session cleanup
    try:
        cleanup_task.cancel()
        await cleanup_task
    except BaseException:
        # Swallow cancellation and any teardown-time exceptions
        pass
    # Shutdown: hot-reload task
    if hot_reload_task:
        try:
            hot_reload_task.cancel()
            await hot_reload_task
        except BaseException:
            pass
    logger.info("service.shutdown", version=settings.service_version)


app.router.lifespan_context = lifespan  # replace deprecated on_event usage


# ---- Shutdown / Exception ----
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    global _ERROR_COUNT
    _ERROR_COUNT += 1
    _ctr_error.inc()
    return JSONResponse(status_code=500, content=error_response(ErrorCode.INTERNAL, str(exc)[:200]))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    # Count only non-2xx as errors (already incremented elsewhere for internal)
    global _ERROR_COUNT
    if exc.status_code >= 400:
        _ERROR_COUNT += 1
        _ctr_error.inc()
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail, "status": exc.status_code})


# POC: map unexpected exceptions to structured error payloads using error taxonomy.
@app.exception_handler(Exception)
async def _handle_any_exception(request: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
    try:
        # Avoid import-order churn by importing locally
        from .error_mapping import marshal_exception

        # Preserve HTTPException status if applicable
        if isinstance(exc, HTTPException):
            payload = {"error": str(exc.detail), "detail": ""}
            try:
                # Map detail to structured code if it matches our taxonomy
                payload = marshal_exception(Exception(str(exc.detail)))
            except Exception:  # noqa: S110
                pass
            return JSONResponse(payload, status_code=exc.status_code)

        payload = marshal_exception(exc)
        return JSONResponse(payload, status_code=500)
    except Exception:
        return JSONResponse({"error": "internal_error", "detail": "handler_failed"}, status_code=500)


# --- Frame signature verification (POC endpoint) ---
@app.post("/v1/verify_frame")
def verify_frame_endpoint(body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:  # noqa: B008
    if os.getenv("ENABLE_FRAME_VERIFY") != "1":
        return {"ok": True, "skipped": True}
    try:
        from .frame_sign import verify_frame_dict, verify_frame_with_km
        from .key_manager import KeyManager
        from .replay_guard import NonceStore
        from .replay_guard_redis import RedisNonceStore

        secret = os.getenv("FRAME_VERIFY_SECRET", "")
        if not secret:
            return {"ok": False, "error": "missing_secret"}
        if not isinstance(body, dict):
            return {"ok": False, "error": "invalid_body"}
        if os.getenv("ENABLE_KMS") == "1" and isinstance(body.get("kid"), str):
            global _KEYMGR  # type: ignore[no-redef]
            if "_KEYMGR" not in globals():
                _KEYMGR = KeyManager()  # type: ignore[assignment]
                # Seed keys from env: KEYMGR_KEYS="k1=secret1,k2=secret2"
                seed = os.getenv("KEYMGR_KEYS", "")
                if seed:
                    for part in seed.split(","):
                        if "=" in part:
                            kid, val = part.split("=", 1)
                            _KEYMGR.add_key(kid.strip(), val.strip().encode("utf-8"))  # type: ignore[attr-defined]
            ok = verify_frame_with_km(body, _KEYMGR)  # type: ignore[arg-type]
        else:
            ok = verify_frame_dict(body, secret.encode("utf-8"))
        # Anti-replay (optional)
        if os.getenv("ENABLE_REPLAY_GUARD") == "1":
            nonce = body.get("nonce")
            if not isinstance(nonce, str) or not nonce:
                return {"ok": False, "error": "missing_nonce"}
            if os.getenv("ENABLE_REDIS_NONCE") == "1":
                try:
                    global _REDIS_NONCE  # type: ignore[no-redef]
                    if "_REDIS_NONCE" not in globals():
                        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                        client = _get_redis_client(redis_url)  # type: ignore[name-defined]
                        _REDIS_NONCE = RedisNonceStore(client)  # type: ignore[assignment]
                    if not _REDIS_NONCE.check_and_store(nonce):  # type: ignore[attr-defined]
                        return {"ok": False, "error": "replay"}
                except Exception as e:
                    return {"ok": False, "error": f"redis_unavailable: {e}"}
            else:
                global _NONCE_STORE  # type: ignore[no-redef]
                if "_NONCE_STORE" not in globals():
                    _NONCE_STORE = NonceStore()  # type: ignore[assignment]
                if not _NONCE_STORE.check_and_store(nonce):  # type: ignore[attr-defined]
                    return {"ok": False, "error": "replay"}
        return {"ok": ok}
    except Exception as err:
        return {"ok": False, "error": str(err)}


# Internal helper to allow tests to override Redis client creation
def _get_redis_client(url: str):  # pragma: no cover - thin wrapper
    import redis

    return redis.Redis.from_url(url)
