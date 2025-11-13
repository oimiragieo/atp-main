"""Tests for ABAC (Attribute-Based Access Control) system."""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from router_service.policy_engine import (
    ABACPolicy,
    AttributeCondition,
    Context,
    Effect,
    EnhancedPolicyEngine,
    Operator,
    PolicyRule,
    get_policy_engine,
)
from router_service.enterprise_auth import UserInfo, AuthProvider


class TestAttributeCondition:
    """Test attribute condition evaluation."""
    
    def test_equals_condition(self):
        condition = AttributeCondition("user.role", Operator.EQUALS, "admin")
        
        assert condition.evaluate({"user.role": "admin"}) is True
        assert condition.evaluate({"user.role": "user"}) is False
        assert condition.evaluate({}) is False
    
    def test_in_condition(self):
        condition = AttributeCondition("user.roles", Operator.IN, ["admin", "moderator"])
        
        assert condition.evaluate({"user.roles": "admin"}) is True
        assert condition.evaluate({"user.roles": "user"}) is False
        assert condition.evaluate({}) is False
    
    def test_contains_condition(self):
        condition = AttributeCondition("user.groups", Operator.CONTAINS, "engineering")
        
        assert condition.evaluate({"user.groups": "engineering-team"}) is True
        assert condition.evaluate({"user.groups": "marketing-team"}) is False
        assert condition.evaluate({}) is False
    
    def test_exists_condition(self):
        condition = AttributeCondition("user.tenant_id", Operator.EXISTS, None)
        
        assert condition.evaluate({"user.tenant_id": "tenant1"}) is True
        assert condition.evaluate({}) is False
    
    def test_greater_than_condition(self):
        condition = AttributeCondition("user.clearance_level", Operator.GREATER_THAN, 5)
        
        assert condition.evaluate({"user.clearance_level": 10}) is True
        assert condition.evaluate({"user.clearance_level": 3}) is False
        assert condition.evaluate({"user.clearance_level": "invalid"}) is False


class TestPolicyRule:
    """Test policy rule evaluation."""
    
    def test_rule_evaluation(self):
        rule = PolicyRule(
            rule_id="admin_access",
            description="Admin access rule",
            effect=Effect.PERMIT,
            conditions=[
                AttributeCondition("user.roles", Operator.CONTAINS, "admin")
            ],
            resources=["api/*"],
            actions=["read", "write"]
        )
        
        # Test matching request
        assert rule.matches_request("api/users", "read") is True
        assert rule.matches_request("api/users", "write") is True
        assert rule.matches_request("api/users", "delete") is False
        assert rule.matches_request("web/dashboard", "read") is False
        
        # Test condition evaluation
        admin_attrs = {"user.roles": ["admin", "user"]}
        user_attrs = {"user.roles": ["user"]}
        
        assert rule.evaluate(admin_attrs) is True
        assert rule.evaluate(user_attrs) is False
    
    def test_wildcard_resource_matching(self):
        rule = PolicyRule(
            rule_id="wildcard_test",
            description="Wildcard test",
            effect=Effect.PERMIT,
            conditions=[],
            resources=["api/*/admin", "data/*"]
        )
        
        assert rule.matches_request("api/v1/admin", "read") is True
        assert rule.matches_request("api/v2/admin", "read") is True
        assert rule.matches_request("api/v1/users", "read") is False
        assert rule.matches_request("data/reports", "read") is True
        assert rule.matches_request("data/reports/monthly", "read") is True


class TestABACPolicy:
    """Test ABAC policy evaluation."""
    
    def test_policy_evaluation(self):
        policy = ABACPolicy(
            policy_id="test_policy",
            name="Test Policy",
            description="Test policy for unit tests",
            rules=[
                PolicyRule(
                    rule_id="admin_permit",
                    description="Permit admin access",
                    effect=Effect.PERMIT,
                    conditions=[
                        AttributeCondition("user.roles", Operator.CONTAINS, "admin")
                    ],
                    actions=["read", "write", "delete"]
                ),
                PolicyRule(
                    rule_id="user_read_only",
                    description="Permit user read access",
                    effect=Effect.PERMIT,
                    conditions=[
                        AttributeCondition("user.roles", Operator.CONTAINS, "user")
                    ],
                    actions=["read"]
                )
            ]
        )
        
        admin_attrs = {"user.roles": ["admin"]}
        user_attrs = {"user.roles": ["user"]}
        guest_attrs = {"user.roles": ["guest"]}
        
        # Admin should get PERMIT for all actions
        assert policy.evaluate("api/data", "read", admin_attrs) == Effect.PERMIT
        assert policy.evaluate("api/data", "write", admin_attrs) == Effect.PERMIT
        assert policy.evaluate("api/data", "delete", admin_attrs) == Effect.PERMIT
        
        # User should get PERMIT only for read
        assert policy.evaluate("api/data", "read", user_attrs) == Effect.PERMIT
        assert policy.evaluate("api/data", "write", user_attrs) is None
        assert policy.evaluate("api/data", "delete", user_attrs) is None
        
        # Guest should get no permissions
        assert policy.evaluate("api/data", "read", guest_attrs) is None
    
    def test_disabled_policy(self):
        policy = ABACPolicy(
            policy_id="disabled_policy",
            name="Disabled Policy",
            description="This policy is disabled",
            enabled=False,
            rules=[
                PolicyRule(
                    rule_id="permit_all",
                    description="Permit everything",
                    effect=Effect.PERMIT,
                    conditions=[]
                )
            ]
        )
        
        # Disabled policy should return None
        assert policy.evaluate("api/data", "read", {}) is None


class TestEnhancedPolicyEngine:
    """Test the enhanced policy engine."""
    
    def setup_method(self):
        """Set up test environment."""
        self.engine = EnhancedPolicyEngine()
    
    def test_add_and_get_policy(self):
        policy = ABACPolicy(
            policy_id="test_policy",
            name="Test Policy",
            description="Test policy",
            rules=[]
        )
        
        self.engine.add_abac_policy(policy)
        
        retrieved = self.engine.get_abac_policy("test_policy")
        assert retrieved is not None
        assert retrieved.policy_id == "test_policy"
        assert retrieved.name == "Test Policy"
    
    def test_remove_policy(self):
        policy = ABACPolicy(
            policy_id="test_policy",
            name="Test Policy",
            description="Test policy",
            rules=[]
        )
        
        self.engine.add_abac_policy(policy)
        assert self.engine.get_abac_policy("test_policy") is not None
        
        success = self.engine.remove_abac_policy("test_policy")
        assert success is True
        assert self.engine.get_abac_policy("test_policy") is None
        
        # Removing non-existent policy should return False
        success = self.engine.remove_abac_policy("non_existent")
        assert success is False
    
    def test_policy_priority_evaluation(self):
        # High priority DENY policy
        deny_policy = ABACPolicy(
            policy_id="deny_policy",
            name="Deny Policy",
            description="High priority deny",
            priority=100,
            rules=[
                PolicyRule(
                    rule_id="deny_all",
                    description="Deny everything",
                    effect=Effect.DENY,
                    conditions=[
                        AttributeCondition("user.roles", Operator.CONTAINS, "blocked")
                    ]
                )
            ]
        )
        
        # Low priority PERMIT policy
        permit_policy = ABACPolicy(
            policy_id="permit_policy",
            name="Permit Policy",
            description="Low priority permit",
            priority=10,
            rules=[
                PolicyRule(
                    rule_id="permit_all",
                    description="Permit everything",
                    effect=Effect.PERMIT,
                    conditions=[
                        AttributeCondition("user.roles", Operator.CONTAINS, "blocked")
                    ]
                )
            ]
        )
        
        self.engine.add_abac_policy(deny_policy)
        self.engine.add_abac_policy(permit_policy)
        
        ctx = Context(
            user_id="test_user",
            roles={"blocked"},
            resource="api/data",
            action="read"
        )
        
        decision = self.engine.evaluate_abac(ctx)
        
        # DENY should take precedence due to higher priority
        assert decision.effect == Effect.DENY
        assert decision.permitted is False
        assert "deny_policy" in decision.applicable_policies
    
    def test_context_attribute_extraction(self):
        ctx = Context(
            user_id="user123",
            tenant_id="tenant456",
            roles={"admin", "user"},
            groups={"engineering"},
            attributes={"clearance": "secret"},
            resource="api/data",
            action="read",
            environment={"ip": "192.168.1.1"}
        )
        
        attrs = ctx.get_all_attributes()
        
        assert attrs["user.id"] == "user123"
        assert attrs["user.tenant_id"] == "tenant456"
        assert "admin" in attrs["user.roles"]
        assert "engineering" in attrs["user.groups"]
        assert attrs["request.resource"] == "api/data"
        assert attrs["request.action"] == "read"
        assert attrs["clearance"] == "secret"
        assert attrs["env.ip"] == "192.168.1.1"
        assert "request.timestamp" in attrs
    
    def test_policy_caching(self):
        policy = ABACPolicy(
            policy_id="cached_policy",
            name="Cached Policy",
            description="Test caching",
            rules=[
                PolicyRule(
                    rule_id="permit_admin",
                    description="Permit admin",
                    effect=Effect.PERMIT,
                    conditions=[
                        AttributeCondition("user.roles", Operator.CONTAINS, "admin")
                    ]
                )
            ]
        )
        
        self.engine.add_abac_policy(policy)
        
        ctx = Context(
            user_id="admin_user",
            roles={"admin"},
            resource="api/data",
            action="read"
        )
        
        # First evaluation should miss cache
        decision1 = self.engine.evaluate_abac(ctx)
        assert decision1.permitted is True
        
        # Second evaluation should hit cache
        decision2 = self.engine.evaluate_abac(ctx)
        assert decision2.permitted is True
        
        # Both decisions should be equivalent
        assert decision1.effect == decision2.effect
        assert decision1.permitted == decision2.permitted


class TestTenantIsolation:
    """Test tenant isolation functionality."""
    
    def test_tenant_scoped_service(self):
        from router_service.tenant_isolation import TenantScopedService
        
        service = TenantScopedService()
        
        # Mock user info
        user_info = UserInfo(
            user_id="user123",
            email="user@example.com",
            name="Test User",
            roles={"user"},
            tenant_id="tenant1"
        )
        
        # Test tenant filter generation
        tenant_filter = service.get_tenant_filter(user_info)
        assert tenant_filter["tenant_id"] == "tenant1"
        assert tenant_filter["user_id"] == "user123"  # Non-admin sees only own data
        
        # Test admin user
        admin_user = UserInfo(
            user_id="admin123",
            email="admin@example.com",
            name="Admin User",
            roles={"admin"},
            tenant_id="tenant1"
        )
        
        admin_filter = service.get_tenant_filter(admin_user)
        assert admin_filter["tenant_id"] == "tenant1"
        assert "user_id" not in admin_filter  # Admin sees all tenant data


@pytest.mark.asyncio
class TestPolicyAPI:
    """Test policy management API endpoints."""
    
    async def test_create_policy_endpoint(self):
        from router_service.policy_api import ABACPolicyModel, PolicyRuleModel, AttributeConditionModel
        from router_service.enterprise_auth import UserInfo, AuthProvider
        
        # Mock user
        admin_user = UserInfo(
            user_id="admin",
            email="admin@test.com",
            name="Admin",
            roles={"admin"},
            provider=AuthProvider.ADMIN_KEYS
        )
        
        # Create test policy
        policy_data = ABACPolicyModel(
            policy_id="test_api_policy",
            name="Test API Policy",
            description="Policy created via API",
            rules=[
                PolicyRuleModel(
                    rule_id="test_rule",
                    description="Test rule",
                    effect=Effect.PERMIT,
                    conditions=[
                        AttributeConditionModel(
                            attribute="user.roles",
                            operator=Operator.CONTAINS,
                            value="admin"
                        )
                    ]
                )
            ]
        )
        
        # Test policy creation (would normally be done via FastAPI)
        from router_service.policy_api import _convert_to_internal_policy
        
        internal_policy = _convert_to_internal_policy(policy_data)
        assert internal_policy.policy_id == "test_api_policy"
        assert len(internal_policy.rules) == 1
        assert internal_policy.rules[0].effect == Effect.PERMIT


def test_global_policy_engine():
    """Test global policy engine singleton."""
    engine1 = get_policy_engine()
    engine2 = get_policy_engine()
    
    # Should return the same instance
    assert engine1 is engine2


def test_legacy_compatibility():
    """Test backward compatibility with legacy escalation policy."""
    from router_service.policy_engine import Policy, Context, Decision
    
    # Legacy policy should still work
    legacy_policy = Policy(low_conf_threshold=0.7, escalate_on_disagreement=True)
    
    # Test low confidence escalation
    ctx = Context(confidence=0.5, disagreement=False)
    decision = legacy_policy.evaluate(ctx)
    assert decision.escalate is True
    assert decision.reason == "low_conf"
    
    # Test disagreement escalation
    ctx = Context(confidence=0.8, disagreement=True)
    decision = legacy_policy.evaluate(ctx)
    assert decision.escalate is True
    assert decision.reason == "disagreement"
    
    # Test no escalation
    ctx = Context(confidence=0.8, disagreement=False)
    decision = legacy_policy.evaluate(ctx)
    assert decision.escalate is False
    assert decision.reason is None