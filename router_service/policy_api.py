"""Policy Management API Endpoints.

REST API endpoints for managing ABAC policies, including CRUD operations,
policy validation, and testing capabilities.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, validator

from .enterprise_auth import UserInfo, require_admin, require_authentication
from .policy_engine import (
    ABACPolicy,
    AttributeCondition,
    Context,
    Effect,
    Operator,
    PolicyRule,
    get_policy_engine,
)

logger = logging.getLogger(__name__)

# Create router
policy_router = APIRouter(prefix="/api/v1/policies", tags=["policies"])


# Pydantic models for API
class AttributeConditionModel(BaseModel):
    """API model for attribute condition."""
    attribute: str = Field(..., description="Attribute name (e.g., 'user.roles')")
    operator: Operator = Field(..., description="Comparison operator")
    value: Any = Field(..., description="Value to compare against")


class PolicyRuleModel(BaseModel):
    """API model for policy rule."""
    rule_id: str = Field(..., description="Unique rule identifier")
    description: str = Field(..., description="Human-readable rule description")
    effect: Effect = Field(..., description="Rule effect (permit/deny)")
    conditions: List[AttributeConditionModel] = Field(..., description="Rule conditions")
    resources: Optional[List[str]] = Field(None, description="Resource patterns (supports wildcards)")
    actions: Optional[List[str]] = Field(None, description="Applicable actions")


class ABACPolicyModel(BaseModel):
    """API model for ABAC policy."""
    policy_id: str = Field(..., description="Unique policy identifier")
    name: str = Field(..., description="Policy name")
    description: str = Field(..., description="Policy description")
    rules: List[PolicyRuleModel] = Field(..., description="Policy rules")
    priority: int = Field(0, description="Policy priority (higher = evaluated first)")
    enabled: bool = Field(True, description="Whether policy is enabled")
    
    @validator('policy_id')
    def validate_policy_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Policy ID cannot be empty')
        if len(v) > 100:
            raise ValueError('Policy ID too long (max 100 characters)')
        return v.strip()
    
    @validator('rules')
    def validate_rules(cls, v):
        if not v:
            raise ValueError('Policy must have at least one rule')
        rule_ids = [rule.rule_id for rule in v]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError('Rule IDs must be unique within policy')
        return v


class PolicyTestRequest(BaseModel):
    """Request model for policy testing."""
    resource: str = Field(..., description="Resource to test access for")
    action: str = Field(..., description="Action to test")
    user_id: Optional[str] = Field(None, description="User ID for testing")
    tenant_id: Optional[str] = Field(None, description="Tenant ID for testing")
    roles: List[str] = Field(default_factory=list, description="User roles")
    groups: List[str] = Field(default_factory=list, description="User groups")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Additional attributes")
    environment: Dict[str, Any] = Field(default_factory=dict, description="Environment attributes")


class PolicyTestResponse(BaseModel):
    """Response model for policy testing."""
    permitted: bool = Field(..., description="Whether access is permitted")
    effect: Optional[Effect] = Field(None, description="Final policy effect")
    applicable_policies: List[str] = Field(..., description="Policies that matched")
    evaluation_time_ms: float = Field(..., description="Evaluation time in milliseconds")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional evaluation details")


class PolicyListResponse(BaseModel):
    """Response model for policy listing."""
    policies: List[ABACPolicyModel]
    total: int
    page: int
    page_size: int


@policy_router.post("/", response_model=ABACPolicyModel)
async def create_policy(
    policy: ABACPolicyModel,
    user: UserInfo = Depends(require_admin())
) -> ABACPolicyModel:
    """Create a new ABAC policy."""
    engine = get_policy_engine()
    
    # Check if policy already exists
    if engine.get_abac_policy(policy.policy_id):
        raise HTTPException(status_code=409, detail=f"Policy {policy.policy_id} already exists")
    
    try:
        # Convert to internal model
        abac_policy = _convert_to_internal_policy(policy)
        
        # Add to engine
        engine.add_abac_policy(abac_policy)
        
        logger.info(f"Created ABAC policy {policy.policy_id} by user {user.user_id}")
        
        return policy
        
    except Exception as e:
        logger.error(f"Failed to create policy {policy.policy_id}: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to create policy: {str(e)}")


@policy_router.get("/", response_model=PolicyListResponse)
async def list_policies(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Page size"),
    enabled_only: bool = Query(False, description="Only return enabled policies"),
    user: UserInfo = Depends(require_authentication({"read", "write", "admin"}))
) -> PolicyListResponse:
    """List ABAC policies with pagination."""
    engine = get_policy_engine()
    
    all_policies = engine.list_abac_policies()
    
    if enabled_only:
        all_policies = [p for p in all_policies if p.enabled]
    
    # Sort by priority (descending) then by name
    all_policies.sort(key=lambda p: (-p.priority, p.name))
    
    # Pagination
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_policies = all_policies[start_idx:end_idx]
    
    # Convert to API models
    api_policies = [_convert_to_api_policy(p) for p in page_policies]
    
    return PolicyListResponse(
        policies=api_policies,
        total=len(all_policies),
        page=page,
        page_size=page_size
    )


@policy_router.get("/{policy_id}", response_model=ABACPolicyModel)
async def get_policy(
    policy_id: str,
    user: UserInfo = Depends(require_authentication({"read", "write", "admin"}))
) -> ABACPolicyModel:
    """Get a specific ABAC policy."""
    engine = get_policy_engine()
    
    policy = engine.get_abac_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
    
    return _convert_to_api_policy(policy)


@policy_router.put("/{policy_id}", response_model=ABACPolicyModel)
async def update_policy(
    policy_id: str,
    policy: ABACPolicyModel,
    user: UserInfo = Depends(require_admin())
) -> ABACPolicyModel:
    """Update an existing ABAC policy."""
    engine = get_policy_engine()
    
    # Ensure policy ID matches
    if policy.policy_id != policy_id:
        raise HTTPException(status_code=400, detail="Policy ID in URL must match policy ID in body")
    
    # Check if policy exists
    existing_policy = engine.get_abac_policy(policy_id)
    if not existing_policy:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
    
    try:
        # Convert to internal model, preserving creation time
        abac_policy = _convert_to_internal_policy(policy)
        abac_policy.created_at = existing_policy.created_at
        
        # Update in engine
        engine.add_abac_policy(abac_policy)
        
        logger.info(f"Updated ABAC policy {policy_id} by user {user.user_id}")
        
        return policy
        
    except Exception as e:
        logger.error(f"Failed to update policy {policy_id}: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to update policy: {str(e)}")


@policy_router.delete("/{policy_id}")
async def delete_policy(
    policy_id: str,
    user: UserInfo = Depends(require_admin())
) -> Dict[str, str]:
    """Delete an ABAC policy."""
    engine = get_policy_engine()
    
    if not engine.remove_abac_policy(policy_id):
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
    
    logger.info(f"Deleted ABAC policy {policy_id} by user {user.user_id}")
    
    return {"message": f"Policy {policy_id} deleted successfully"}


@policy_router.post("/{policy_id}/enable")
async def enable_policy(
    policy_id: str,
    user: UserInfo = Depends(require_admin())
) -> Dict[str, str]:
    """Enable an ABAC policy."""
    engine = get_policy_engine()
    
    policy = engine.get_abac_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
    
    policy.enabled = True
    policy.updated_at = datetime.utcnow()
    engine.add_abac_policy(policy)
    
    logger.info(f"Enabled ABAC policy {policy_id} by user {user.user_id}")
    
    return {"message": f"Policy {policy_id} enabled successfully"}


@policy_router.post("/{policy_id}/disable")
async def disable_policy(
    policy_id: str,
    user: UserInfo = Depends(require_admin())
) -> Dict[str, str]:
    """Disable an ABAC policy."""
    engine = get_policy_engine()
    
    policy = engine.get_abac_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
    
    policy.enabled = False
    policy.updated_at = datetime.utcnow()
    engine.add_abac_policy(policy)
    
    logger.info(f"Disabled ABAC policy {policy_id} by user {user.user_id}")
    
    return {"message": f"Policy {policy_id} disabled successfully"}


@policy_router.post("/test", response_model=PolicyTestResponse)
async def test_policies(
    request: PolicyTestRequest,
    user: UserInfo = Depends(require_authentication({"read", "write", "admin"}))
) -> PolicyTestResponse:
    """Test policy evaluation for given context."""
    engine = get_policy_engine()
    
    # Create context from request
    ctx = Context(
        user_id=request.user_id,
        tenant_id=request.tenant_id,
        roles=set(request.roles),
        groups=set(request.groups),
        attributes=request.attributes,
        resource=request.resource,
        action=request.action,
        environment=request.environment
    )
    
    # Evaluate policies
    decision = engine.evaluate_abac(ctx)
    
    return PolicyTestResponse(
        permitted=decision.permitted,
        effect=decision.effect,
        applicable_policies=decision.applicable_policies,
        evaluation_time_ms=decision.evaluation_time_ms,
        details={
            "context": ctx.get_all_attributes(),
            "total_policies": len(engine.list_abac_policies()),
            "enabled_policies": len([p for p in engine.list_abac_policies() if p.enabled])
        }
    )


@policy_router.post("/validate", response_model=Dict[str, Any])
async def validate_policy(
    policy: ABACPolicyModel,
    user: UserInfo = Depends(require_authentication({"read", "write", "admin"}))
) -> Dict[str, Any]:
    """Validate a policy without creating it."""
    try:
        # Try to convert to internal model (this validates the structure)
        _convert_to_internal_policy(policy)
        
        return {
            "valid": True,
            "message": "Policy is valid",
            "warnings": []
        }
        
    except Exception as e:
        return {
            "valid": False,
            "message": f"Policy validation failed: {str(e)}",
            "errors": [str(e)]
        }


def _convert_to_internal_policy(api_policy: ABACPolicyModel) -> ABACPolicy:
    """Convert API policy model to internal policy model."""
    rules = []
    
    for rule_model in api_policy.rules:
        conditions = []
        
        for cond_model in rule_model.conditions:
            condition = AttributeCondition(
                attribute=cond_model.attribute,
                operator=cond_model.operator,
                value=cond_model.value
            )
            conditions.append(condition)
        
        rule = PolicyRule(
            rule_id=rule_model.rule_id,
            description=rule_model.description,
            effect=rule_model.effect,
            conditions=conditions,
            resources=rule_model.resources,
            actions=rule_model.actions
        )
        rules.append(rule)
    
    return ABACPolicy(
        policy_id=api_policy.policy_id,
        name=api_policy.name,
        description=api_policy.description,
        rules=rules,
        priority=api_policy.priority,
        enabled=api_policy.enabled
    )


def _convert_to_api_policy(internal_policy: ABACPolicy) -> ABACPolicyModel:
    """Convert internal policy model to API policy model."""
    rules = []
    
    for rule in internal_policy.rules:
        conditions = []
        
        for condition in rule.conditions:
            cond_model = AttributeConditionModel(
                attribute=condition.attribute,
                operator=condition.operator,
                value=condition.value
            )
            conditions.append(cond_model)
        
        rule_model = PolicyRuleModel(
            rule_id=rule.rule_id,
            description=rule.description,
            effect=rule.effect,
            conditions=conditions,
            resources=rule.resources,
            actions=rule.actions
        )
        rules.append(rule_model)
    
    return ABACPolicyModel(
        policy_id=internal_policy.policy_id,
        name=internal_policy.name,
        description=internal_policy.description,
        rules=rules,
        priority=internal_policy.priority,
        enabled=internal_policy.enabled
    )