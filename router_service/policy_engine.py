"""Enterprise Policy Engine with ABAC Support.

Enhanced policy engine supporting both escalation decisions and attribute-based
access control (ABAC). Integrates with enterprise authentication system for
fine-grained permissions and tenant isolation.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from metrics.registry import REGISTRY

from .tracing import get_tracer

logger = logging.getLogger(__name__)

# Metrics
_CTR_ESC_LOW_CONF = REGISTRY.counter("escalations_total_low_conf")
_CTR_ESC_DISAGREE = REGISTRY.counter("escalations_total_disagreement")
_CTR_ABAC_EVALUATIONS = REGISTRY.counter("abac_evaluations_total")
_CTR_ABAC_PERMITS = REGISTRY.counter("abac_permits_total")
_CTR_ABAC_DENIES = REGISTRY.counter("abac_denies_total")
_CTR_POLICY_CACHE_HITS = REGISTRY.counter("policy_cache_hits_total")
_CTR_POLICY_CACHE_MISSES = REGISTRY.counter("policy_cache_misses_total")


class Effect(Enum):
    """Policy decision effect."""

    PERMIT = "permit"
    DENY = "deny"


class Operator(Enum):
    """Attribute comparison operators."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    CONTAINS = "contains"
    MATCHES = "matches"  # regex
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"


@dataclass
class AttributeCondition:
    """Single attribute condition in a policy rule."""

    attribute: str
    operator: Operator
    value: Any

    def evaluate(self, attributes: dict[str, Any]) -> bool:
        """Evaluate this condition against provided attributes."""
        attr_value = attributes.get(self.attribute)

        if self.operator == Operator.EXISTS:
            return self.attribute in attributes
        elif self.operator == Operator.NOT_EXISTS:
            return self.attribute not in attributes

        if attr_value is None:
            return False

        try:
            if self.operator == Operator.EQUALS:
                return attr_value == self.value
            elif self.operator == Operator.NOT_EQUALS:
                return attr_value != self.value
            elif self.operator == Operator.IN:
                return attr_value in self.value if isinstance(self.value, (list, set, tuple)) else False
            elif self.operator == Operator.NOT_IN:
                return attr_value not in self.value if isinstance(self.value, (list, set, tuple)) else True
            elif self.operator == Operator.GREATER_THAN:
                return float(attr_value) > float(self.value)
            elif self.operator == Operator.LESS_THAN:
                return float(attr_value) < float(self.value)
            elif self.operator == Operator.CONTAINS:
                return str(self.value) in str(attr_value)
            elif self.operator == Operator.MATCHES:
                return bool(re.match(str(self.value), str(attr_value)))
        except (ValueError, TypeError) as e:
            logger.debug(f"Attribute condition evaluation error: {e}")
            return False

        return False


@dataclass
class PolicyRule:
    """ABAC policy rule with conditions and effect."""

    rule_id: str
    description: str
    effect: Effect
    conditions: list[AttributeCondition]
    resources: list[str] | None = None  # Resource patterns this rule applies to
    actions: list[str] | None = None  # Actions this rule applies to

    def matches_request(self, resource: str, action: str) -> bool:
        """Check if this rule applies to the given resource and action."""
        if self.resources and not any(self._matches_pattern(resource, pattern) for pattern in self.resources):
            return False
        if self.actions and action not in self.actions:
            return False
        return True

    def _matches_pattern(self, resource: str, pattern: str) -> bool:
        """Check if resource matches pattern (supports wildcards)."""
        # Convert wildcard pattern to regex
        regex_pattern = pattern.replace("*", ".*").replace("?", ".")
        return bool(re.match(f"^{regex_pattern}$", resource))

    def evaluate(self, attributes: dict[str, Any]) -> bool:
        """Evaluate all conditions in this rule (AND logic)."""
        return all(condition.evaluate(attributes) for condition in self.conditions)


@dataclass
class ABACPolicy:
    """Attribute-Based Access Control policy."""

    policy_id: str
    name: str
    description: str
    rules: list[PolicyRule]
    priority: int = 0
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def evaluate(self, resource: str, action: str, attributes: dict[str, Any]) -> Effect | None:
        """Evaluate policy for given resource, action, and attributes."""
        if not self.enabled:
            return None

        applicable_rules = [rule for rule in self.rules if rule.matches_request(resource, action)]

        for rule in applicable_rules:
            if rule.evaluate(attributes):
                return rule.effect

        return None


@dataclass
class Context:
    """Enhanced context for policy evaluation."""

    # Legacy escalation context
    confidence: float | None = None
    disagreement: bool = False

    # ABAC context
    user_id: str | None = None
    tenant_id: str | None = None
    roles: set[str] = field(default_factory=set)
    groups: set[str] = field(default_factory=set)
    attributes: dict[str, Any] = field(default_factory=dict)
    resource: str | None = None
    action: str | None = None
    environment: dict[str, Any] = field(default_factory=dict)

    def get_all_attributes(self) -> dict[str, Any]:
        """Get all attributes for ABAC evaluation."""
        all_attrs = {
            "user.id": self.user_id,
            "user.tenant_id": self.tenant_id,
            "user.roles": list(self.roles),
            "user.groups": list(self.groups),
            "request.resource": self.resource,
            "request.action": self.action,
            "request.timestamp": datetime.utcnow().isoformat(),
        }

        # Add custom attributes
        all_attrs.update(self.attributes)

        # Add environment attributes
        for key, value in self.environment.items():
            all_attrs[f"env.{key}"] = value

        # Remove None values
        return {k: v for k, v in all_attrs.items() if v is not None}


@dataclass
class Decision:
    """Enhanced policy decision."""

    # Legacy escalation decision
    escalate: bool = False
    reason: str | None = None

    # ABAC decision
    effect: Effect | None = None
    permitted: bool = False
    applicable_policies: list[str] = field(default_factory=list)
    evaluation_time_ms: float = 0.0


class EnhancedPolicyEngine:
    """Enhanced policy engine with ABAC support."""

    def __init__(self):
        self.abac_policies: dict[str, ABACPolicy] = {}
        self.policy_cache: dict[str, Decision] = {}
        self.cache_ttl = timedelta(minutes=5)
        self.cache_timestamps: dict[str, datetime] = {}

        # Legacy escalation policy
        self.escalation_policy = EscalationPolicy()

    def add_abac_policy(self, policy: ABACPolicy) -> None:
        """Add or update an ABAC policy."""
        policy.updated_at = datetime.utcnow()
        if policy.created_at is None:
            policy.created_at = policy.updated_at

        self.abac_policies[policy.policy_id] = policy
        self._clear_cache()
        logger.info(f"Added ABAC policy: {policy.policy_id}")

    def remove_abac_policy(self, policy_id: str) -> bool:
        """Remove an ABAC policy."""
        if policy_id in self.abac_policies:
            del self.abac_policies[policy_id]
            self._clear_cache()
            logger.info(f"Removed ABAC policy: {policy_id}")
            return True
        return False

    def get_abac_policy(self, policy_id: str) -> ABACPolicy | None:
        """Get an ABAC policy by ID."""
        return self.abac_policies.get(policy_id)

    def list_abac_policies(self) -> list[ABACPolicy]:
        """List all ABAC policies."""
        return list(self.abac_policies.values())

    def evaluate_abac(self, ctx: Context) -> Decision:
        """Evaluate ABAC policies for the given context."""
        start_time = datetime.utcnow()
        _CTR_ABAC_EVALUATIONS.inc()

        tracer = get_tracer()
        span_cm = tracer.start_as_current_span("policy.evaluate_abac") if tracer else None

        try:
            if not ctx.resource or not ctx.action:
                decision = Decision(effect=Effect.DENY, permitted=False, reason="missing_resource_or_action")
                _CTR_ABAC_DENIES.inc()
                return decision

            # Check cache
            cache_key = self._get_cache_key(ctx)
            cached_decision = self._get_cached_decision(cache_key)
            if cached_decision:
                _CTR_POLICY_CACHE_HITS.inc()
                return cached_decision

            _CTR_POLICY_CACHE_MISSES.inc()

            # Get all attributes for evaluation
            attributes = ctx.get_all_attributes()

            # Evaluate policies in priority order
            applicable_policies = []
            final_effect = None

            sorted_policies = sorted(
                self.abac_policies.values(),
                key=lambda p: p.priority,
                reverse=True,  # Higher priority first
            )

            for policy in sorted_policies:
                if not policy.enabled:
                    continue

                effect = policy.evaluate(ctx.resource, ctx.action, attributes)
                if effect is not None:
                    applicable_policies.append(policy.policy_id)
                    if final_effect is None:
                        final_effect = effect

                    # DENY takes precedence (fail-safe)
                    if effect == Effect.DENY:
                        final_effect = Effect.DENY
                        break

            # Default to DENY if no policies match
            if final_effect is None:
                final_effect = Effect.DENY

            permitted = final_effect == Effect.PERMIT
            evaluation_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            decision = Decision(
                effect=final_effect,
                permitted=permitted,
                applicable_policies=applicable_policies,
                evaluation_time_ms=evaluation_time,
            )

            # Cache the decision
            self._cache_decision(cache_key, decision)

            # Update metrics
            if permitted:
                _CTR_ABAC_PERMITS.inc()
            else:
                _CTR_ABAC_DENIES.inc()

            return decision

        finally:
            if span_cm:
                try:
                    import opentelemetry.trace as ottrace

                    span = ottrace.get_current_span()
                    span.set_attribute("abac.resource", ctx.resource or "")
                    span.set_attribute("abac.action", ctx.action or "")
                    span.set_attribute("abac.user_id", ctx.user_id or "")
                    span.set_attribute("abac.tenant_id", ctx.tenant_id or "")
                except Exception as e:
                    logger.debug(f"Failed to set span attributes for ABAC evaluation: {e}")
                span_cm.__exit__(None, None, None)

    def evaluate(self, ctx: Context) -> Decision:
        """Evaluate both escalation and ABAC policies."""
        # Start with escalation evaluation (legacy)
        escalation_decision = self.escalation_policy.evaluate(ctx)

        # If ABAC context is provided, evaluate ABAC policies
        if ctx.resource and ctx.action:
            abac_decision = self.evaluate_abac(ctx)

            # Combine decisions
            return Decision(
                escalate=escalation_decision.escalate,
                reason=escalation_decision.reason,
                effect=abac_decision.effect,
                permitted=abac_decision.permitted,
                applicable_policies=abac_decision.applicable_policies,
                evaluation_time_ms=abac_decision.evaluation_time_ms,
            )

        return escalation_decision

    def _get_cache_key(self, ctx: Context) -> str:
        """Generate cache key for context."""
        key_data = {
            "resource": ctx.resource,
            "action": ctx.action,
            "user_id": ctx.user_id,
            "tenant_id": ctx.tenant_id,
            "roles": sorted(ctx.roles),
            "groups": sorted(ctx.groups),
            "attributes": sorted(ctx.attributes.items()) if ctx.attributes else [],
        }
        return json.dumps(key_data, sort_keys=True)

    def _get_cached_decision(self, cache_key: str) -> Decision | None:
        """Get cached decision if still valid."""
        if cache_key in self.policy_cache:
            timestamp = self.cache_timestamps.get(cache_key)
            if timestamp and datetime.utcnow() - timestamp < self.cache_ttl:
                return self.policy_cache[cache_key]
            else:
                # Remove expired entry
                self.policy_cache.pop(cache_key, None)
                self.cache_timestamps.pop(cache_key, None)
        return None

    def _cache_decision(self, cache_key: str, decision: Decision) -> None:
        """Cache a policy decision."""
        self.policy_cache[cache_key] = decision
        self.cache_timestamps[cache_key] = datetime.utcnow()

    def _clear_cache(self) -> None:
        """Clear the policy cache."""
        self.policy_cache.clear()
        self.cache_timestamps.clear()


@dataclass
class EscalationPolicy:
    """Legacy escalation policy for backward compatibility."""

    low_conf_threshold: float = 0.6
    escalate_on_disagreement: bool = True

    def evaluate(self, ctx: Context) -> Decision:
        """Evaluate escalation policy."""
        tracer = get_tracer()
        span_cm = tracer.start_as_current_span("policy.evaluate_escalation") if tracer else None
        reason: str | None = None
        escalate = False
        try:
            # Low confidence
            if ctx.confidence is not None and ctx.confidence < self.low_conf_threshold:
                escalate = True
                reason = "low_conf"
                _CTR_ESC_LOW_CONF.inc(1)
            # Disagreement
            elif self.escalate_on_disagreement and ctx.disagreement:
                escalate = True
                reason = "disagreement"
                _CTR_ESC_DISAGREE.inc(1)
            return Decision(escalate=escalate, reason=reason)
        finally:
            if span_cm:
                try:
                    import opentelemetry.trace as ottrace

                    span = ottrace.get_current_span()
                    span.set_attribute("policy.escalate", escalate)
                    if reason:
                        span.set_attribute("policy.reason", reason)
                except Exception as e:
                    logger.debug(f"Failed to set span attributes for escalation evaluation: {e}")
                span_cm.__exit__(None, None, None)


# Global policy engine instance
_policy_engine = EnhancedPolicyEngine()


def get_policy_engine() -> EnhancedPolicyEngine:
    """Get the global policy engine instance."""
    return _policy_engine


# Legacy compatibility
Policy = EscalationPolicy
