"""
Advanced Loop Detection and Abuse Prevention System

This module provides comprehensive protection against request loops, abuse patterns,
and anomalous behavior with automatic blocking and progressive rate limiting.
"""

import asyncio
import hashlib
import logging
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4

try:
    from metrics.registry import REGISTRY

    _CTR_LOOP_DETECTIONS = REGISTRY.counter("loop_detections_total", ["detection_type"])
    _CTR_ABUSE_BLOCKS = REGISTRY.counter("abuse_blocks_total", ["block_reason"])
    _CTR_RATE_LIMITS = REGISTRY.counter("rate_limit_hits_total", ["limit_type"])
    _HIST_REQUEST_DEPTH = REGISTRY.histogram("request_depth", ["tenant_id"])
    _GAUGE_ACTIVE_REQUESTS = REGISTRY.gauge("active_requests_by_tenant", ["tenant_id"])
    METRICS_AVAILABLE = True
except Exception:
    METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)


class BlockReason(Enum):
    """Reasons for blocking requests"""

    REQUEST_LOOP = "request_loop"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    ANOMALOUS_BEHAVIOR = "anomalous_behavior"
    RECURSIVE_DEPTH_EXCEEDED = "recursive_depth_exceeded"
    SUSPICIOUS_PATTERN = "suspicious_pattern"
    DDOS_PROTECTION = "ddos_protection"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"


class ThreatLevel(Enum):
    """Threat severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RequestSignature:
    """Unique signature for request identification"""

    content_hash: str
    endpoint: str
    method: str
    tenant_id: str
    user_id: str | None = None

    def __hash__(self):
        return hash((self.content_hash, self.endpoint, self.method, self.tenant_id, self.user_id))


@dataclass
class RequestContext:
    """Context information for a request"""

    request_id: str
    signature: RequestSignature
    timestamp: datetime
    parent_request_id: str | None = None
    depth: int = 0
    source_ip: str | None = None
    user_agent: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "signature": asdict(self.signature),
            "timestamp": self.timestamp.isoformat(),
            "parent_request_id": self.parent_request_id,
            "depth": self.depth,
            "source_ip": self.source_ip,
            "user_agent": self.user_agent,
        }


@dataclass
class AbuseEvent:
    """Record of detected abuse"""

    event_id: str
    timestamp: datetime
    tenant_id: str
    user_id: str | None
    source_ip: str | None
    block_reason: BlockReason
    threat_level: ThreatLevel
    details: dict[str, Any]
    action_taken: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "source_ip": self.source_ip,
            "block_reason": self.block_reason.value,
            "threat_level": self.threat_level.value,
            "details": self.details,
            "action_taken": self.action_taken,
        }


class CircuitBreaker:
    """Enhanced circuit breaker with configurable thresholds"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60, half_open_max_calls: int = 3):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open
        self.half_open_calls = 0

    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half_open"
                self.half_open_calls = 0
            else:
                raise Exception("Circuit breaker is open")

        if self.state == "half_open":
            if self.half_open_calls >= self.half_open_max_calls:
                raise Exception("Circuit breaker half-open limit exceeded")
            self.half_open_calls += 1

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e

    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt reset"""
        if self.last_failure_time is None:
            return True
        return time.time() - self.last_failure_time > self.recovery_timeout

    def _on_success(self):
        """Handle successful call"""
        self.failure_count = 0
        if self.state == "half_open":
            self.state = "closed"

    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "open"


class RateLimiter:
    """Progressive rate limiter with multiple tiers"""

    def __init__(self):
        self.request_counts = defaultdict(lambda: defaultdict(int))
        self.request_times = defaultdict(lambda: defaultdict(deque))
        self.blocked_until = defaultdict(lambda: defaultdict(float))

        # Rate limit tiers (requests per minute)
        self.limits = {"normal": 1000, "elevated": 500, "restricted": 100, "blocked": 10}

        # Escalation thresholds
        self.escalation_thresholds = {
            "elevated": 5,  # violations to reach elevated
            "restricted": 3,  # violations to reach restricted
            "blocked": 2,  # violations to reach blocked
        }

        self.violation_counts = defaultdict(lambda: defaultdict(int))
        self.current_tier = defaultdict(lambda: defaultdict(lambda: "normal"))

    def is_allowed(self, tenant_id: str, user_id: str = None, endpoint: str = "default") -> tuple[bool, str, int]:
        """Check if request is allowed under current rate limits"""
        key = f"{tenant_id}:{user_id or 'anonymous'}:{endpoint}"
        current_time = time.time()

        # Check if currently blocked
        if current_time < self.blocked_until[tenant_id][key]:
            remaining = int(self.blocked_until[tenant_id][key] - current_time)
            return False, "temporarily_blocked", remaining

        # Get current tier and limit
        tier = self.current_tier[tenant_id][key]
        limit = self.limits[tier]

        # Clean old requests (older than 1 minute)
        request_times = self.request_times[tenant_id][key]
        while request_times and current_time - request_times[0] > 60:
            request_times.popleft()

        # Check current rate
        if len(request_times) >= limit:
            # Rate limit exceeded
            self._handle_violation(tenant_id, key, tier)
            if METRICS_AVAILABLE:
                _CTR_RATE_LIMITS.labels(limit_type=tier).inc()
            return False, f"rate_limit_exceeded_{tier}", 60

        # Allow request
        request_times.append(current_time)
        return True, "allowed", 0

    def _handle_violation(self, tenant_id: str, key: str, current_tier: str):
        """Handle rate limit violation and escalate if necessary"""
        self.violation_counts[tenant_id][key] += 1
        violations = self.violation_counts[tenant_id][key]

        # Escalate tier based on violations
        if current_tier == "normal" and violations >= self.escalation_thresholds["elevated"]:
            self.current_tier[tenant_id][key] = "elevated"
            logger.warning(f"Escalated {key} to elevated tier")
        elif current_tier == "elevated" and violations >= self.escalation_thresholds["restricted"]:
            self.current_tier[tenant_id][key] = "restricted"
            logger.warning(f"Escalated {key} to restricted tier")
        elif current_tier == "restricted" and violations >= self.escalation_thresholds["blocked"]:
            self.current_tier[tenant_id][key] = "blocked"
            # Block for 5 minutes
            self.blocked_until[tenant_id][key] = time.time() + 300
            logger.error(f"Blocked {key} for 5 minutes")

    def reset_violations(self, tenant_id: str, user_id: str = None, endpoint: str = "default"):
        """Reset violation count for a key"""
        key = f"{tenant_id}:{user_id or 'anonymous'}:{endpoint}"
        self.violation_counts[tenant_id][key] = 0
        self.current_tier[tenant_id][key] = "normal"


class LoopDetector:
    """Detect request loops and recursive patterns"""

    def __init__(self, max_depth: int = 10, loop_window: int = 300):
        self.max_depth = max_depth
        self.loop_window = loop_window  # seconds

        self.active_requests: dict[str, RequestContext] = {}
        self.request_history: dict[str, list[RequestContext]] = defaultdict(list)
        self.signature_counts: dict[RequestSignature, int] = defaultdict(int)

    def start_request(self, request_context: RequestContext) -> tuple[bool, str | None]:
        """Start tracking a request and check for loops"""

        # Check request depth
        if request_context.depth > self.max_depth:
            if METRICS_AVAILABLE:
                _CTR_LOOP_DETECTIONS.labels(detection_type="depth_exceeded").inc()
            return False, f"Request depth {request_context.depth} exceeds maximum {self.max_depth}"

        # Check for immediate loops (same signature in active requests)
        signature = request_context.signature
        for active_req in self.active_requests.values():
            if active_req.signature == signature:
                if METRICS_AVAILABLE:
                    _CTR_LOOP_DETECTIONS.labels(detection_type="immediate_loop").inc()
                return False, "Immediate loop detected: duplicate active request"

        # Check for pattern loops in recent history
        tenant_history = self.request_history[signature.tenant_id]
        recent_requests = [
            req for req in tenant_history if (datetime.now() - req.timestamp).total_seconds() < self.loop_window
        ]

        signature_count = sum(1 for req in recent_requests if req.signature == signature)
        if signature_count >= 5:  # Same signature 5+ times in window
            if METRICS_AVAILABLE:
                _CTR_LOOP_DETECTIONS.labels(detection_type="pattern_loop").inc()
            return False, f"Pattern loop detected: signature repeated {signature_count} times"

        # Track the request
        self.active_requests[request_context.request_id] = request_context
        self.request_history[signature.tenant_id].append(request_context)
        self.signature_counts[signature] += 1

        if METRICS_AVAILABLE:
            _HIST_REQUEST_DEPTH.labels(tenant_id=signature.tenant_id).observe(request_context.depth)
            _GAUGE_ACTIVE_REQUESTS.labels(tenant_id=signature.tenant_id).set(
                len([r for r in self.active_requests.values() if r.signature.tenant_id == signature.tenant_id])
            )

        return True, None

    def end_request(self, request_id: str):
        """Stop tracking a request"""
        if request_id in self.active_requests:
            context = self.active_requests.pop(request_id)

            if METRICS_AVAILABLE:
                _GAUGE_ACTIVE_REQUESTS.labels(tenant_id=context.signature.tenant_id).set(
                    len(
                        [
                            r
                            for r in self.active_requests.values()
                            if r.signature.tenant_id == context.signature.tenant_id
                        ]
                    )
                )

    def cleanup_old_history(self):
        """Clean up old request history"""
        cutoff = datetime.now() - timedelta(seconds=self.loop_window * 2)

        for tenant_id in list(self.request_history.keys()):
            self.request_history[tenant_id] = [req for req in self.request_history[tenant_id] if req.timestamp > cutoff]

            if not self.request_history[tenant_id]:
                del self.request_history[tenant_id]


class AnomalyDetector:
    """Detect anomalous behavior patterns"""

    def __init__(self):
        self.request_patterns = defaultdict(lambda: defaultdict(list))
        self.baseline_metrics = defaultdict(dict)
        self.anomaly_scores = defaultdict(float)

    def analyze_request(self, context: RequestContext) -> tuple[bool, float, str]:
        """Analyze request for anomalous patterns"""
        tenant_id = context.signature.tenant_id
        current_time = time.time()

        # Track request patterns
        patterns = self.request_patterns[tenant_id]

        # Request frequency analysis
        patterns["timestamps"].append(current_time)
        patterns["endpoints"].append(context.signature.endpoint)
        patterns["methods"].append(context.signature.method)
        patterns["depths"].append(context.depth)

        # Keep only recent data (last 10 minutes)
        cutoff = current_time - 600
        for key in patterns:
            if key == "timestamps":
                patterns[key] = [t for t in patterns[key] if t > cutoff]
            else:
                # Keep corresponding entries
                valid_indices = [i for i, t in enumerate(patterns["timestamps"]) if t > cutoff]
                patterns[key] = [patterns[key][i] for i in valid_indices if i < len(patterns[key])]

        # Calculate anomaly score
        anomaly_score = self._calculate_anomaly_score(tenant_id, patterns)
        self.anomaly_scores[tenant_id] = anomaly_score

        # Determine if anomalous
        is_anomalous = anomaly_score > 0.8
        reason = self._get_anomaly_reason(patterns, anomaly_score)

        return is_anomalous, anomaly_score, reason

    def _calculate_anomaly_score(self, tenant_id: str, patterns: dict[str, list]) -> float:
        """Calculate anomaly score based on patterns"""
        score = 0.0

        if not patterns["timestamps"]:
            return 0.0

        # Frequency anomaly (requests per minute)
        request_count = len(patterns["timestamps"])
        if request_count > 100:  # More than 100 requests in 10 minutes
            score += min(0.4, (request_count - 100) / 500)

        # Endpoint diversity anomaly
        unique_endpoints = len(set(patterns["endpoints"]))
        if unique_endpoints > 20:  # Accessing many different endpoints
            score += min(0.3, (unique_endpoints - 20) / 50)

        # Depth anomaly
        if patterns["depths"]:
            avg_depth = sum(patterns["depths"]) / len(patterns["depths"])
            if avg_depth > 5:  # High average request depth
                score += min(0.3, (avg_depth - 5) / 10)

        # Method pattern anomaly
        method_counts = defaultdict(int)
        for method in patterns["methods"]:
            method_counts[method] += 1

        # Unusual method distribution
        if len(method_counts) > 1:
            method_entropy = self._calculate_entropy(list(method_counts.values()))
            if method_entropy > 1.5:  # High entropy in method usage
                score += min(0.2, (method_entropy - 1.5) / 2)

        return min(1.0, score)

    def _calculate_entropy(self, values: list[int]) -> float:
        """Calculate entropy of a distribution"""
        import math

        total = sum(values)
        if total == 0:
            return 0.0

        entropy = 0.0
        for value in values:
            if value > 0:
                p = value / total
                entropy -= p * math.log2(p)

        return entropy

    def _get_anomaly_reason(self, patterns: dict[str, list], score: float) -> str:
        """Get human-readable reason for anomaly detection"""
        reasons = []

        request_count = len(patterns["timestamps"])
        if request_count > 100:
            reasons.append(f"high_frequency_{request_count}_requests")

        unique_endpoints = len(set(patterns["endpoints"]))
        if unique_endpoints > 20:
            reasons.append(f"endpoint_scanning_{unique_endpoints}_endpoints")

        if patterns["depths"]:
            avg_depth = sum(patterns["depths"]) / len(patterns["depths"])
            if avg_depth > 5:
                reasons.append(f"deep_recursion_avg_{avg_depth:.1f}")

        return "_".join(reasons) if reasons else f"anomaly_score_{score:.2f}"


class AbusePreventionSystem:
    """Main abuse prevention system coordinating all components"""

    def __init__(self):
        self.loop_detector = LoopDetector()
        self.rate_limiter = RateLimiter()
        self.anomaly_detector = AnomalyDetector()
        self.circuit_breakers = defaultdict(CircuitBreaker)
        self.abuse_events: list[AbuseEvent] = []
        self.blocked_entities: dict[str, datetime] = {}

        # Start cleanup task
        self._cleanup_task = None
        self._start_cleanup_task()

    def _start_cleanup_task(self):
        """Start background cleanup task"""

        async def cleanup_loop():
            while True:
                try:
                    self.loop_detector.cleanup_old_history()
                    self._cleanup_old_events()
                    await asyncio.sleep(300)  # Clean up every 5 minutes
                except Exception as e:
                    logger.error(f"Error in cleanup task: {e}")
                    await asyncio.sleep(60)

        try:
            loop = asyncio.get_event_loop()
            self._cleanup_task = loop.create_task(cleanup_loop())
        except RuntimeError:
            # No event loop running, cleanup will be manual
            pass

    def check_request(
        self,
        request_id: str,
        tenant_id: str,
        endpoint: str,
        method: str,
        content: str,
        user_id: str | None = None,
        source_ip: str | None = None,
        user_agent: str | None = None,
        parent_request_id: str | None = None,
        depth: int = 0,
    ) -> tuple[bool, BlockReason | None, str]:
        """Comprehensive request check"""

        # Create request signature
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        signature = RequestSignature(
            content_hash=content_hash, endpoint=endpoint, method=method, tenant_id=tenant_id, user_id=user_id
        )

        # Create request context
        context = RequestContext(
            request_id=request_id,
            signature=signature,
            timestamp=datetime.now(),
            parent_request_id=parent_request_id,
            depth=depth,
            source_ip=source_ip,
            user_agent=user_agent,
        )

        # Check if entity is blocked
        entity_key = f"{tenant_id}:{user_id or 'anonymous'}"
        if entity_key in self.blocked_entities:
            if datetime.now() < self.blocked_entities[entity_key]:
                return False, BlockReason.SUSPICIOUS_PATTERN, "Entity temporarily blocked"
            else:
                del self.blocked_entities[entity_key]

        # Rate limiting check
        allowed, reason, wait_time = self.rate_limiter.is_allowed(tenant_id, user_id, endpoint)
        if not allowed:
            self._record_abuse_event(
                tenant_id,
                user_id,
                source_ip,
                BlockReason.RATE_LIMIT_EXCEEDED,
                ThreatLevel.MEDIUM,
                {"reason": reason, "wait_time": wait_time, "endpoint": endpoint},
            )
            return False, BlockReason.RATE_LIMIT_EXCEEDED, f"Rate limit exceeded: {reason}"

        # Loop detection check
        loop_allowed, loop_reason = self.loop_detector.start_request(context)
        if not loop_allowed:
            self._record_abuse_event(
                tenant_id,
                user_id,
                source_ip,
                BlockReason.REQUEST_LOOP,
                ThreatLevel.HIGH,
                {"reason": loop_reason, "depth": depth, "endpoint": endpoint},
            )
            return False, BlockReason.REQUEST_LOOP, loop_reason

        # Anomaly detection check
        is_anomalous, anomaly_score, anomaly_reason = self.anomaly_detector.analyze_request(context)
        if is_anomalous:
            # Block entity for 10 minutes on high anomaly score
            if anomaly_score > 0.9:
                self.blocked_entities[entity_key] = datetime.now() + timedelta(minutes=10)
                threat_level = ThreatLevel.CRITICAL
            else:
                threat_level = ThreatLevel.HIGH

            self._record_abuse_event(
                tenant_id,
                user_id,
                source_ip,
                BlockReason.ANOMALOUS_BEHAVIOR,
                threat_level,
                {"anomaly_score": anomaly_score, "reason": anomaly_reason, "endpoint": endpoint},
            )

            if anomaly_score > 0.9:
                return False, BlockReason.ANOMALOUS_BEHAVIOR, f"Anomalous behavior detected: {anomaly_reason}"

        # Circuit breaker check
        circuit_breaker = self.circuit_breakers[f"{tenant_id}:{endpoint}"]
        if circuit_breaker.state == "open":
            return False, BlockReason.CIRCUIT_BREAKER_OPEN, "Circuit breaker is open"

        return True, None, "Request allowed"

    def end_request(self, request_id: str, success: bool = True):
        """Mark request as completed"""
        self.loop_detector.end_request(request_id)

        # Update circuit breaker based on success
        # This would be called by the actual request handler

    def _record_abuse_event(
        self,
        tenant_id: str,
        user_id: str | None,
        source_ip: str | None,
        block_reason: BlockReason,
        threat_level: ThreatLevel,
        details: dict[str, Any],
    ):
        """Record an abuse event"""
        event = AbuseEvent(
            event_id=str(uuid4()),
            timestamp=datetime.now(),
            tenant_id=tenant_id,
            user_id=user_id,
            source_ip=source_ip,
            block_reason=block_reason,
            threat_level=threat_level,
            details=details,
            action_taken="blocked" if threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL] else "logged",
        )

        self.abuse_events.append(event)

        if METRICS_AVAILABLE:
            _CTR_ABUSE_BLOCKS.labels(block_reason=block_reason.value).inc()

        logger.warning(f"Abuse event recorded: {event.to_dict()}")

    def _cleanup_old_events(self):
        """Clean up old abuse events"""
        cutoff = datetime.now() - timedelta(days=30)
        self.abuse_events = [event for event in self.abuse_events if event.timestamp > cutoff]

    def get_abuse_events(self, tenant_id: str | None = None, hours: int = 24) -> list[dict[str, Any]]:
        """Get recent abuse events"""
        cutoff = datetime.now() - timedelta(hours=hours)

        events = [event for event in self.abuse_events if event.timestamp > cutoff]

        if tenant_id:
            events = [event for event in events if event.tenant_id == tenant_id]

        return [event.to_dict() for event in events]

    def get_system_status(self) -> dict[str, Any]:
        """Get system status and statistics"""
        return {
            "active_requests": len(self.loop_detector.active_requests),
            "circuit_breakers": {
                key: {"state": cb.state, "failure_count": cb.failure_count} for key, cb in self.circuit_breakers.items()
            },
            "blocked_entities": len(self.blocked_entities),
            "recent_abuse_events": len(
                [e for e in self.abuse_events if (datetime.now() - e.timestamp).total_seconds() < 3600]
            ),
            "anomaly_scores": dict(self.anomaly_detector.anomaly_scores),
        }

    def reset_entity(self, tenant_id: str, user_id: str | None = None):
        """Reset abuse tracking for an entity"""
        entity_key = f"{tenant_id}:{user_id or 'anonymous'}"

        # Remove from blocked entities
        if entity_key in self.blocked_entities:
            del self.blocked_entities[entity_key]

        # Reset rate limiter
        self.rate_limiter.reset_violations(tenant_id, user_id)

        # Reset anomaly scores
        if tenant_id in self.anomaly_detector.anomaly_scores:
            del self.anomaly_detector.anomaly_scores[tenant_id]

        logger.info(f"Reset abuse tracking for {entity_key}")


# Global instance
abuse_prevention_system = AbusePreventionSystem()


# Convenience functions
def check_request_abuse(
    request_id: str, tenant_id: str, endpoint: str, method: str, content: str, **kwargs
) -> tuple[bool, str | None]:
    """Check if request should be blocked for abuse"""
    allowed, block_reason, message = abuse_prevention_system.check_request(
        request_id, tenant_id, endpoint, method, content, **kwargs
    )

    if not allowed:
        return False, f"{block_reason.value}: {message}"

    return True, None


def end_request_tracking(request_id: str, success: bool = True):
    """End request tracking"""
    abuse_prevention_system.end_request(request_id, success)


def get_abuse_statistics(tenant_id: str | None = None) -> dict[str, Any]:
    """Get abuse prevention statistics"""
    return {
        "system_status": abuse_prevention_system.get_system_status(),
        "recent_events": abuse_prevention_system.get_abuse_events(tenant_id, hours=24),
    }
