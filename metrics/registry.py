"""Lightweight metrics registry abstraction to replace ad-hoc globals.

Design goals:
- Minimal overhead (<2% vs direct globals for counters)
- Thread-safe increments
- Export snapshot for /metrics endpoint without tight coupling
- Pluggable backend hooks later (Prometheus client, OTel)
"""

from __future__ import annotations

import threading
import time
from typing import Any


class Counter:
    __slots__ = ("_value", "_lock")

    def __init__(self, initial: int = 0) -> None:
        self._value = initial
        self._lock = threading.Lock()

    def inc(self, amount: int = 1) -> None:
        if amount == 0:
            return
        with self._lock:
            self._value += amount

    def set(self, value: int) -> None:  # used only during snapshot restore
        with self._lock:
            self._value = value

    @property
    def value(self) -> int:
        return self._value


class Histogram:
    __slots__ = ("_buckets", "_counts", "_lock")

    def __init__(self, buckets: list[float]) -> None:
        self._buckets = list(buckets)
        self._counts = [0] * (len(buckets) + 1)
        self._lock = threading.Lock()

    def observe(self, v: float) -> None:
        with self._lock:
            for i, b in enumerate(self._buckets):
                if v <= b:
                    self._counts[i] += 1
                    return
            self._counts[-1] += 1

    def snapshot(self) -> dict[str, Any]:
        return {"buckets": self._buckets, "counts": list(self._counts)}


class Gauge:
    __slots__ = ("_value", "_lock")

    def __init__(self, initial: float = 0.0) -> None:
        self._value = float(initial)
        self._lock = threading.Lock()

    def set(self, v: float) -> None:
        with self._lock:
            self._value = float(v)

    def inc(self, amt: float = 1.0) -> None:
        with self._lock:
            self._value += amt

    def dec(self, amt: float = 1.0) -> None:
        with self._lock:
            self._value -= amt

    @property
    def value(self) -> float:
        return self._value


class MetricsRegistry:
    def __init__(self) -> None:
        self.counters: dict[str, Counter] = {}
        self.histograms: dict[str, Histogram] = {}
        self.gauges: dict[str, Gauge] = {}
        self._lock = threading.Lock()

    def counter(self, name: str) -> Counter:
        with self._lock:
            c = self.counters.get(name)
            if c:
                return c
            c = Counter()
            self.counters[name] = c
            return c

    def histogram(self, name: str, buckets: list[float]) -> Histogram:
        with self._lock:
            h = self.histograms.get(name)
            if h:
                return h
            h = Histogram(buckets)
            self.histograms[name] = h
            return h

    def gauge(self, name: str) -> Gauge:
        with self._lock:
            g = self.gauges.get(name)
            if g:
                return g
            g = Gauge()
            self.gauges[name] = g
            return g

    def export(self) -> dict[str, Any]:
        out = {
            "counters": {k: v.value for k, v in self.counters.items()},
            "histograms": {k: v.snapshot() for k, v in self.histograms.items()},
            "gauges": {k: v.value for k, v in self.gauges.items()},
            "ts": time.time(),
        }
        return out


REGISTRY = MetricsRegistry()

# GAP-213: Carbon intensity tracking metrics
CARBON_INTENSITY_WEIGHT = REGISTRY.gauge("carbon_intensity_weight")
CARBON_API_REQUESTS_TOTAL = REGISTRY.counter("carbon_api_requests_total")
CARBON_API_ERRORS_TOTAL = REGISTRY.counter("carbon_api_errors_total")
CARBON_AWARE_ROUTING_DECISIONS_TOTAL = REGISTRY.counter("carbon_aware_routing_decisions_total")

# GAP-214A: Energy and CO2e attribution metrics
ENERGY_KWH_TOTAL = REGISTRY.counter("energy_kwh_total")
CO2E_GRAMS_TOTAL = REGISTRY.counter("co2e_grams_total")
ENERGY_SAVINGS_PCT = REGISTRY.histogram("energy_savings_pct", [0.0, 10.0, 25.0, 50.0, 75.0, 90.0, 100.0])

# GAP-220: Federated routing prior aggregator metrics
FEDERATED_ROUNDS_COMPLETED = REGISTRY.counter("federated_rounds_completed")

# GAP-221: Privacy budget management metrics
DP_BUDGET_REMAINING = REGISTRY.gauge("dp_budget_remaining")

# GAP-371: Federated reward signal schema metrics
FEDERATED_REWARD_BATCHES_TOTAL = REGISTRY.counter("federated_reward_batches_total")

# GAP-372: Secure aggregation protocol metrics
SECURE_AGG_FAILURES_TOTAL = REGISTRY.counter("secure_agg_failures_total")

# GAP-309: Vector backfill & re-embedding pipeline metrics
REEMBED_JOBS_COMPLETED_TOTAL = REGISTRY.counter("reembed_jobs_completed_total")
REEMBED_JOBS_FAILED_TOTAL = REGISTRY.counter("reembed_jobs_failed_total")
REEMBED_JOBS_ACTIVE = REGISTRY.gauge("reembed_jobs_active")
REEMBED_JOBS_QUEUED = REGISTRY.gauge("reembed_jobs_queued")
REEMBED_BATCHES_PROCESSED_TOTAL = REGISTRY.counter("reembed_batches_processed_total")
REEMBED_ITEMS_REEMBEDDED_TOTAL = REGISTRY.counter("reembed_items_reembedded_total")

# GAP-310: Cross-namespace access audit & anomaly detection metrics
MEMORY_ACCESS_ANOMALIES_TOTAL = REGISTRY.counter("memory_access_anomalies_total")

# GAP-271: DP telemetry exporter metrics
DP_EVENTS_EXPORTED_TOTAL = REGISTRY.counter("dp_events_exported_total")

# GAP-123: Adapter capability advertisement metrics
ADAPTERS_REGISTERED = REGISTRY.gauge("adapters_registered")

# GAP-124: Adapter health & p95 telemetry push metrics
ADAPTER_HEALTH_UPDATES = REGISTRY.counter("adapter_health_updates_total")

# GAP-125: MCP WebSocket endpoint metrics
MCP_SESSIONS_ACTIVE = REGISTRY.gauge("mcp_sessions_active")
MCP_HEARTBEATS_TX = REGISTRY.counter("mcp_heartbeats_tx")

# GAP-126: Tool descriptor generator metrics
TOOLS_EXPOSED_TOTAL = REGISTRY.gauge("tools_exposed_total")

# GAP-127: Streaming partial toolOutput events metrics
MCP_PARTIAL_FRAMES_TOTAL = REGISTRY.counter("mcp_partial_frames_total")

# GAP-129: Experiment metadata surfacing metrics
EXPERIMENT_FRAMES_TOTAL = REGISTRY.counter("experiment_frames_total")

# GAP-135: Rejection/speculative sampling event surfacing metrics
SPECULATIVE_EVENTS_TOTAL = REGISTRY.counter("speculative_events_total")

# GAP-162: Policy change approval workflow metrics
POLICY_CHANGE_REQUESTS_TOTAL = REGISTRY.counter("policy_change_requests_total")
POLICY_CHANGE_REQUESTS_APPROVED_TOTAL = REGISTRY.counter("policy_change_requests_approved_total")
POLICY_CHANGE_REQUESTS_REJECTED_TOTAL = REGISTRY.counter("policy_change_requests_rejected_total")
POLICY_CHANGE_REQUESTS_EXPIRED_TOTAL = REGISTRY.counter("policy_change_requests_expired_total")
POLICY_CHANGE_REQUESTS_PENDING = REGISTRY.gauge("policy_change_requests_pending")
POLICY_APPROVAL_LATENCY = REGISTRY.histogram(
    "policy_approval_latency_seconds", [3600, 7200, 14400, 28800, 604800]
)  # 1h, 2h, 4h, 8h, 1w

# GAP-328: Access review attestation workflow metrics
ACCESS_REVIEWS_COMPLETED_TOTAL = REGISTRY.counter("access_reviews_completed_total")

# GAP-329: Config drift & security baseline detector metrics
CONFIG_DRIFT_ALERTS_TOTAL = REGISTRY.counter("config_drift_alerts_total")

# GAP-329B: Vector DB certification matrix metrics
VECTOR_BACKEND_RECALL_AT_K_IN_MEMORY = REGISTRY.gauge("vector_backend_recall_at_k_in_memory")
VECTOR_BACKEND_RECALL_AT_K_WEAVIATE = REGISTRY.gauge("vector_backend_recall_at_k_weaviate")
VECTOR_BACKEND_RECALL_AT_K_PINECONE = REGISTRY.gauge("vector_backend_recall_at_k_pinecone")
VECTOR_BACKEND_RECALL_AT_K_PGVECTOR = REGISTRY.gauge("vector_backend_recall_at_k_pgvector")

# GAP-329C: Audit Merkle root anchoring strategy metrics
MERKLE_ROOT_PUBLISH_TOTAL = REGISTRY.counter("merkle_root_publish_total")
MERKLE_ROOT_VERIFICATION_TOTAL = REGISTRY.counter("merkle_root_verification_total")
MERKLE_ROOT_VERIFICATION_FAILED_TOTAL = REGISTRY.counter("merkle_root_verification_failed_total")
MERKLE_ROOT_PUBLISH_LATENCY = REGISTRY.histogram("merkle_root_publish_latency_seconds", [0.1, 0.5, 1.0, 2.0, 5.0])

# GAP-329D: SLA tier specification & SLO targets metrics
SLO_BREACH_EVENTS_TOTAL = REGISTRY.counter("slo_breach_events_total")

# GAP-335C: On-prem operator packaging metrics
ONPREM_DEPLOYS_TOTAL = REGISTRY.counter("onprem_deploys_total")
ONPREM_DEPLOY_SUCCESS_TOTAL = REGISTRY.counter("onprem_deploy_success_total")
ONPREM_DEPLOY_FAILED_TOTAL = REGISTRY.counter("onprem_deploy_failed_total")
ONPREM_IMAGE_SYNC_DURATION = REGISTRY.histogram("onprem_image_sync_duration_seconds", [60, 300, 600, 1800, 3600])

# GAP-360: Edge node request relay & auth metrics
EDGE_REQUESTS_TOTAL = REGISTRY.counter("edge_requests_total")
EDGE_AUTH_FAILURES_TOTAL = REGISTRY.counter("edge_auth_failures_total")
EDGE_RELAY_LATENCY = REGISTRY.histogram("edge_relay_latency_seconds", [0.1, 0.5, 1.0, 2.0, 5.0, 10.0])
EDGE_ACTIVE_CONNECTIONS = REGISTRY.gauge("edge_active_connections")

# GAP-361: Edge prompt compression & small SLM fallback metrics
EDGE_SAVINGS_PCT = REGISTRY.gauge("edge_savings_pct")

# GAP-362: Predictive prewarming scheduler metrics
PREWARM_HITS_TOTAL = REGISTRY.counter("prewarm_hits_total")
PREWARM_WASTE_MS = REGISTRY.histogram(
    "prewarm_waste_ms", [1000, 5000, 10000, 30000, 60000, 300000]
)  # 1s, 5s, 10s, 30s, 1m, 5m

# GAP-363: Edge cache metrics
EDGE_CACHE_HITS_TOTAL = REGISTRY.counter("edge_cache_hits_total")
EDGE_CACHE_MISSES_TOTAL = REGISTRY.counter("edge_cache_misses_total")
EDGE_CACHE_EVICTIONS_TOTAL = REGISTRY.counter("edge_cache_evictions_total")
EDGE_CACHE_SIZE = REGISTRY.gauge("edge_cache_size")
EDGE_CACHE_HIT_RATIO = REGISTRY.gauge("edge_cache_hit_ratio")

# GAP-367: High-cardinality guardrail advisor metrics
CARDINALITY_ALERTS_TOTAL = REGISTRY.counter("cardinality_alerts_total")
CARDINALITY_METRICS_MONITORED = REGISTRY.gauge("cardinality_metrics_monitored")
CARDINALITY_VIOLATIONS_ACTIVE = REGISTRY.gauge("cardinality_violations_active")

# GAP-368: Evidence pack assembly pipeline metrics
EVIDENCE_PACKS_GENERATED_TOTAL = REGISTRY.counter("evidence_packs_generated_total")
EVIDENCE_PACK_GENERATION_DURATION = REGISTRY.histogram(
    "evidence_pack_generation_duration_seconds", [30, 60, 120, 300, 600]
)

# GAP-373: Reinforcement prior update integration metrics
PRIOR_UPDATES_APPLIED_TOTAL = REGISTRY.counter("prior_updates_applied_total")
PRIOR_UPDATE_FAILURES_TOTAL = REGISTRY.counter("prior_update_failures_total")
ACTIVE_PRIORS = REGISTRY.gauge("active_priors")
PRIOR_UPDATE_LATENCY_SECONDS = REGISTRY.histogram("prior_update_latency_seconds", [0.001, 0.01, 0.1, 1.0, 5.0])

# Enterprise Cache System Metrics (Task 2.3)
CACHE_L1_HITS_TOTAL = REGISTRY.counter("cache_l1_hits_total")
CACHE_L1_MISSES_TOTAL = REGISTRY.counter("cache_l1_misses_total")
CACHE_L1_SETS_TOTAL = REGISTRY.counter("cache_l1_sets_total")
CACHE_L1_DELETES_TOTAL = REGISTRY.counter("cache_l1_deletes_total")
CACHE_L1_EVICTIONS_TOTAL = REGISTRY.counter("cache_l1_evictions_total")
CACHE_L1_SIZE = REGISTRY.gauge("cache_l1_size")
CACHE_L1_MEMORY_BYTES = REGISTRY.gauge("cache_l1_memory_bytes")

CACHE_L2_HITS_TOTAL = REGISTRY.counter("cache_l2_hits_total")
CACHE_L2_MISSES_TOTAL = REGISTRY.counter("cache_l2_misses_total")
CACHE_L2_SETS_TOTAL = REGISTRY.counter("cache_l2_sets_total")
CACHE_L2_DELETES_TOTAL = REGISTRY.counter("cache_l2_deletes_total")
CACHE_L2_ERRORS_TOTAL = REGISTRY.counter("cache_l2_errors_total")
CACHE_L2_TIMEOUTS_TOTAL = REGISTRY.counter("cache_l2_timeouts_total")

CACHE_HITS_TOTAL = REGISTRY.counter("cache_hits_total")
CACHE_MISSES_TOTAL = REGISTRY.counter("cache_misses_total")
CACHE_HIT_RATIO = REGISTRY.gauge("cache_hit_ratio")

CACHE_OPERATION_DURATION_SECONDS = REGISTRY.histogram(
    "cache_operation_duration_seconds", [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

CACHE_REDIS_CONNECTIONS_ACTIVE = REGISTRY.gauge("cache_redis_connections_active")
CACHE_REDIS_CONNECTIONS_CREATED_TOTAL = REGISTRY.counter("cache_redis_connections_created_total")
CACHE_REDIS_CONNECTION_ERRORS_TOTAL = REGISTRY.counter("cache_redis_connection_errors_total")

CACHE_INVALIDATIONS_SENT_TOTAL = REGISTRY.counter("cache_invalidations_sent_total")
CACHE_INVALIDATIONS_RECEIVED_TOTAL = REGISTRY.counter("cache_invalidations_received_total")
CACHE_INVALIDATION_ERRORS_TOTAL = REGISTRY.counter("cache_invalidation_errors_total")

# Redis Cluster Metrics
REDIS_CLUSTER_NODES_TOTAL = REGISTRY.gauge("redis_cluster_nodes_total")
REDIS_CLUSTER_NODES_HEALTHY = REGISTRY.gauge("redis_cluster_nodes_healthy")
REDIS_CLUSTER_SLOTS_ASSIGNED = REGISTRY.gauge("redis_cluster_slots_assigned")
REDIS_CLUSTER_SLOTS_OK = REGISTRY.gauge("redis_cluster_slots_ok")
REDIS_CLUSTER_FAILOVERS_TOTAL = REGISTRY.counter("redis_cluster_failovers_total")
REDIS_CLUSTER_REBALANCES_TOTAL = REGISTRY.counter("redis_cluster_rebalances_total")

# Real-time Pricing Monitoring Metrics (Task 3.1)
PRICING_API_REQUESTS_TOTAL = REGISTRY.counter("pricing_api_requests_total")
PRICING_API_ERRORS_TOTAL = REGISTRY.counter("pricing_api_errors_total")
PRICING_API_TIMEOUTS_TOTAL = REGISTRY.counter("pricing_api_timeouts_total")
PRICING_API_RATE_LIMITS_TOTAL = REGISTRY.counter("pricing_api_rate_limits_total")

PRICING_UPDATES_TOTAL = REGISTRY.counter("pricing_updates_total")
PRICING_UPDATE_ERRORS_TOTAL = REGISTRY.counter("pricing_update_errors_total")
PRICING_CHANGES_DETECTED_TOTAL = REGISTRY.counter("pricing_changes_detected_total")
PRICING_STALE_ENTRIES = REGISTRY.gauge("pricing_stale_entries")

PRICING_VALIDATION_TOTAL = REGISTRY.counter("pricing_validation_total")
PRICING_VALIDATION_ERRORS_TOTAL = REGISTRY.counter("pricing_validation_errors_total")
PRICING_VALIDATION_ERROR_RATE = REGISTRY.gauge("pricing_validation_error_rate")

PRICING_ALERTS_SENT_TOTAL = REGISTRY.counter("pricing_alerts_sent_total")
PRICING_ALERT_ERRORS_TOTAL = REGISTRY.counter("pricing_alert_errors_total")

PRICING_CACHE_HITS_TOTAL = REGISTRY.counter("pricing_cache_hits_total")
PRICING_CACHE_MISSES_TOTAL = REGISTRY.counter("pricing_cache_misses_total")
PRICING_CACHE_SIZE = REGISTRY.gauge("pricing_cache_size")

# Enhanced Cost Tracking Metrics
COST_USD_TOTAL_BY_PROVIDER = REGISTRY.histogram("cost_usd_total_by_provider", [0.01, 0.1, 1.0, 10.0, 100.0])
COST_USD_TOTAL_BY_MODEL = REGISTRY.histogram("cost_usd_total_by_model", [0.01, 0.1, 1.0, 10.0, 100.0])
COST_USD_TOTAL_BY_TENANT = REGISTRY.histogram("cost_usd_total_by_tenant", [0.01, 0.1, 1.0, 10.0, 100.0])

TOKENS_INPUT_TOTAL = REGISTRY.counter("tokens_input_total")
TOKENS_OUTPUT_TOTAL = REGISTRY.counter("tokens_output_total")
TOKENS_TOTAL_BY_PROVIDER = REGISTRY.counter("tokens_total_by_provider")
TOKENS_TOTAL_BY_MODEL = REGISTRY.counter("tokens_total_by_model")

REQUESTS_TOTAL_ENHANCED = REGISTRY.counter("requests_total_enhanced")
REQUESTS_BY_PROVIDER = REGISTRY.counter("requests_by_provider")
REQUESTS_BY_MODEL = REGISTRY.counter("requests_by_model")

COST_PER_TOKEN_BY_MODEL = REGISTRY.gauge("cost_per_token_by_model")
COST_EFFICIENCY_SCORE = REGISTRY.gauge("cost_efficiency_score")
