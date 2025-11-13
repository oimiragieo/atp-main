"""Budget management and enforcement system."""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .optimization_config import OptimizationConfig
from ..cache import get_cache_manager

logger = logging.getLogger(__name__)


class BudgetManager:
    """Manages budgets and enforces spending limits per tenant and project."""
    
    def __init__(self, config: Optional[OptimizationConfig] = None):
        self.config = config or OptimizationConfig.from_environment()
        self.cache_manager = get_cache_manager()
        
        # Budget tracking
        self._tenant_budgets: Dict[str, float] = self.config.per_tenant_budgets or {}
        self._project_budgets: Dict[str, float] = self.config.per_project_budgets or {}
        
        # Current spending tracking
        self._tenant_spending: Dict[str, float] = {}
        self._project_spending: Dict[str, float] = {}
        self._global_spending: float = 0.0
        
        # Rate limiting
        self._tenant_rate_limits: Dict[str, int] = self.config.tenant_rate_limits or {}
        self._tenant_request_counts: Dict[str, List[float]] = {}  # timestamp lists
        
        # Alert tracking
        self._budget_alerts_sent: Dict[str, float] = {}  # last alert timestamp
        self._alert_cooldown = 3600  # 1 hour between similar alerts
        
        logger.info("Budget manager initialized")
    
    async def set_tenant_budget(self, tenant_id: str, monthly_budget_usd: float) -> None:
        """Set monthly budget for a tenant."""
        self._tenant_budgets[tenant_id] = monthly_budget_usd
        
        # Cache the budget
        cache_key = f"budget:tenant:{tenant_id}"
        await self.cache_manager.set(cache_key, monthly_budget_usd, 86400)  # 24 hour TTL
        
        logger.info(f"Set budget for tenant {tenant_id}: ${monthly_budget_usd}")
    
    async def set_project_budget(self, project_id: str, monthly_budget_usd: float) -> None:
        """Set monthly budget for a project."""
        self._project_budgets[project_id] = monthly_budget_usd
        
        # Cache the budget
        cache_key = f"budget:project:{project_id}"
        await self.cache_manager.set(cache_key, monthly_budget_usd, 86400)  # 24 hour TTL
        
        logger.info(f"Set budget for project {project_id}: ${monthly_budget_usd}")
    
    async def record_spending(
        self,
        cost_usd: float,
        tenant_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Record spending and check budget limits."""
        current_time = time.time()
        
        # Update spending tracking
        self._global_spending += cost_usd
        
        if tenant_id:
            self._tenant_spending[tenant_id] = self._tenant_spending.get(tenant_id, 0.0) + cost_usd
        
        if project_id:
            self._project_spending[project_id] = self._project_spending.get(project_id, 0.0) + cost_usd
        
        # Check budget limits
        budget_status = await self._check_budget_limits(tenant_id, project_id)
        
        # Update cache with current spending
        if tenant_id:
            cache_key = f"spending:tenant:{tenant_id}"
            await self.cache_manager.set(cache_key, self._tenant_spending[tenant_id], 3600)
        
        if project_id:
            cache_key = f"spending:project:{project_id}"
            await self.cache_manager.set(cache_key, self._project_spending[project_id], 3600)
        
        return {
            "cost_usd": cost_usd,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "budget_status": budget_status,
            "recorded_at": current_time
        }
    
    async def _check_budget_limits(
        self,
        tenant_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Check if spending is within budget limits."""
        status = {
            "within_budget": True,
            "warnings": [],
            "critical_alerts": [],
            "enforcement_actions": []
        }
        
        # Check tenant budget
        if tenant_id and tenant_id in self._tenant_budgets:
            tenant_budget = self._tenant_budgets[tenant_id]
            tenant_spending = self._tenant_spending.get(tenant_id, 0.0)
            usage_percent = (tenant_spending / tenant_budget) * 100
            
            if usage_percent >= self.config.budget_critical_threshold_percent:
                status["critical_alerts"].append({
                    "type": "tenant_budget_critical",
                    "tenant_id": tenant_id,
                    "usage_percent": usage_percent,
                    "budget_usd": tenant_budget,
                    "spending_usd": tenant_spending
                })
                status["within_budget"] = False
                
                # Apply enforcement action
                action = await self._apply_enforcement_action(tenant_id, "tenant", usage_percent)
                if action:
                    status["enforcement_actions"].append(action)
            
            elif usage_percent >= self.config.budget_warning_threshold_percent:
                status["warnings"].append({
                    "type": "tenant_budget_warning",
                    "tenant_id": tenant_id,
                    "usage_percent": usage_percent,
                    "budget_usd": tenant_budget,
                    "spending_usd": tenant_spending
                })
        
        # Check project budget
        if project_id and project_id in self._project_budgets:
            project_budget = self._project_budgets[project_id]
            project_spending = self._project_spending.get(project_id, 0.0)
            usage_percent = (project_spending / project_budget) * 100
            
            if usage_percent >= self.config.budget_critical_threshold_percent:
                status["critical_alerts"].append({
                    "type": "project_budget_critical",
                    "project_id": project_id,
                    "usage_percent": usage_percent,
                    "budget_usd": project_budget,
                    "spending_usd": project_spending
                })
                status["within_budget"] = False
                
                # Apply enforcement action
                action = await self._apply_enforcement_action(project_id, "project", usage_percent)
                if action:
                    status["enforcement_actions"].append(action)
            
            elif usage_percent >= self.config.budget_warning_threshold_percent:
                status["warnings"].append({
                    "type": "project_budget_warning",
                    "project_id": project_id,
                    "usage_percent": usage_percent,
                    "budget_usd": project_budget,
                    "spending_usd": project_spending
                })
        
        # Send alerts if needed
        if status["warnings"] or status["critical_alerts"]:
            await self._send_budget_alerts(status)
        
        return status
    
    async def _apply_enforcement_action(
        self,
        entity_id: str,
        entity_type: str,
        usage_percent: float
    ) -> Optional[Dict[str, Any]]:
        """Apply budget enforcement action."""
        if not self.config.budget_enforcement_enabled:
            return None
        
        action_type = self.config.budget_enforcement_action
        current_time = time.time()
        
        if action_type == "block":
            # Block all requests
            cache_key = f"budget_block:{entity_type}:{entity_id}"
            await self.cache_manager.set(cache_key, True, 3600)  # Block for 1 hour
            
            return {
                "action": "block",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "usage_percent": usage_percent,
                "applied_at": current_time
            }
        
        elif action_type == "throttle":
            # Apply rate limiting
            throttle_factor = min(0.1, (100 - usage_percent) / 100)  # Reduce to 10% or less
            cache_key = f"budget_throttle:{entity_type}:{entity_id}"
            await self.cache_manager.set(cache_key, throttle_factor, 3600)
            
            return {
                "action": "throttle",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "throttle_factor": throttle_factor,
                "usage_percent": usage_percent,
                "applied_at": current_time
            }
        
        elif action_type == "alert":
            # Just alert, no enforcement
            return {
                "action": "alert_only",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "usage_percent": usage_percent,
                "applied_at": current_time
            }
        
        return None
    
    async def _send_budget_alerts(self, status: Dict[str, Any]) -> None:
        """Send budget alerts."""
        if not self.config.alerts_enabled:
            return
        
        current_time = time.time()
        
        # Check cooldown for alerts
        for alert in status.get("critical_alerts", []) + status.get("warnings", []):
            alert_key = f"{alert['type']}:{alert.get('tenant_id', alert.get('project_id', 'global'))}"
            
            last_alert_time = self._budget_alerts_sent.get(alert_key, 0)
            if current_time - last_alert_time < self._alert_cooldown:
                continue  # Skip due to cooldown
            
            # Send alert (implementation would depend on alert channels)
            await self._send_alert(alert)
            self._budget_alerts_sent[alert_key] = current_time
    
    async def _send_alert(self, alert: Dict[str, Any]) -> None:
        """Send individual budget alert."""
        # This would integrate with the pricing alert system
        logger.warning(f"Budget alert: {alert}")
        
        # In a full implementation, this would use the alert channels
        # configured in the optimization config
    
    async def check_request_allowed(
        self,
        tenant_id: Optional[str] = None,
        project_id: Optional[str] = None,
        estimated_cost: Optional[float] = None
    ) -> Dict[str, Any]:
        """Check if a request is allowed based on budget and rate limits."""
        current_time = time.time()
        
        result = {
            "allowed": True,
            "reasons": [],
            "throttle_factor": 1.0,
            "estimated_cost": estimated_cost
        }
        
        # Check budget blocks
        if tenant_id:
            block_key = f"budget_block:tenant:{tenant_id}"
            is_blocked = await self.cache_manager.get(block_key)
            if is_blocked:
                result["allowed"] = False
                result["reasons"].append("tenant_budget_exceeded")
        
        if project_id:
            block_key = f"budget_block:project:{project_id}"
            is_blocked = await self.cache_manager.get(block_key)
            if is_blocked:
                result["allowed"] = False
                result["reasons"].append("project_budget_exceeded")
        
        # Check throttling
        if tenant_id:
            throttle_key = f"budget_throttle:tenant:{tenant_id}"
            throttle_factor = await self.cache_manager.get(throttle_key)
            if throttle_factor:
                result["throttle_factor"] = min(result["throttle_factor"], throttle_factor)
        
        if project_id:
            throttle_key = f"budget_throttle:project:{project_id}"
            throttle_factor = await self.cache_manager.get(throttle_key)
            if throttle_factor:
                result["throttle_factor"] = min(result["throttle_factor"], throttle_factor)
        
        # Check rate limits
        if tenant_id and tenant_id in self._tenant_rate_limits:
            rate_limit = self._tenant_rate_limits[tenant_id]
            if not await self._check_rate_limit(tenant_id, rate_limit, current_time):
                result["allowed"] = False
                result["reasons"].append("tenant_rate_limit_exceeded")
        
        # Check if estimated cost would exceed budget
        if estimated_cost and result["allowed"]:
            budget_check = await self._check_estimated_cost_impact(
                estimated_cost, tenant_id, project_id
            )
            if not budget_check["allowed"]:
                result["allowed"] = False
                result["reasons"].extend(budget_check["reasons"])
        
        return result
    
    async def _check_rate_limit(self, tenant_id: str, rate_limit: int, current_time: float) -> bool:
        """Check if tenant is within rate limit."""
        if tenant_id not in self._tenant_request_counts:
            self._tenant_request_counts[tenant_id] = []
        
        # Clean old timestamps (older than 1 hour)
        hour_ago = current_time - 3600
        self._tenant_request_counts[tenant_id] = [
            ts for ts in self._tenant_request_counts[tenant_id] if ts > hour_ago
        ]
        
        # Check if under limit
        if len(self._tenant_request_counts[tenant_id]) >= rate_limit:
            return False
        
        # Record this request
        self._tenant_request_counts[tenant_id].append(current_time)
        return True
    
    async def _check_estimated_cost_impact(
        self,
        estimated_cost: float,
        tenant_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Check if estimated cost would cause budget to be exceeded."""
        result = {"allowed": True, "reasons": []}
        
        # Check tenant budget impact
        if tenant_id and tenant_id in self._tenant_budgets:
            tenant_budget = self._tenant_budgets[tenant_id]
            current_spending = self._tenant_spending.get(tenant_id, 0.0)
            projected_spending = current_spending + estimated_cost
            usage_percent = (projected_spending / tenant_budget) * 100
            
            if usage_percent > self.config.budget_critical_threshold_percent:
                result["allowed"] = False
                result["reasons"].append("tenant_budget_would_exceed")
        
        # Check project budget impact
        if project_id and project_id in self._project_budgets:
            project_budget = self._project_budgets[project_id]
            current_spending = self._project_spending.get(project_id, 0.0)
            projected_spending = current_spending + estimated_cost
            usage_percent = (projected_spending / project_budget) * 100
            
            if usage_percent > self.config.budget_critical_threshold_percent:
                result["allowed"] = False
                result["reasons"].append("project_budget_would_exceed")
        
        return result
    
    async def get_budget_status(
        self,
        tenant_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get current budget status."""
        status = {
            "global_spending": self._global_spending,
            "tenant_status": {},
            "project_status": {}
        }
        
        # Tenant status
        if tenant_id:
            if tenant_id in self._tenant_budgets:
                budget = self._tenant_budgets[tenant_id]
                spending = self._tenant_spending.get(tenant_id, 0.0)
                usage_percent = (spending / budget) * 100
                
                status["tenant_status"][tenant_id] = {
                    "budget_usd": budget,
                    "spending_usd": spending,
                    "remaining_usd": budget - spending,
                    "usage_percent": usage_percent,
                    "status": self._get_budget_health_status(usage_percent)
                }
        else:
            # All tenants
            for tid, budget in self._tenant_budgets.items():
                spending = self._tenant_spending.get(tid, 0.0)
                usage_percent = (spending / budget) * 100
                
                status["tenant_status"][tid] = {
                    "budget_usd": budget,
                    "spending_usd": spending,
                    "remaining_usd": budget - spending,
                    "usage_percent": usage_percent,
                    "status": self._get_budget_health_status(usage_percent)
                }
        
        # Project status
        if project_id:
            if project_id in self._project_budgets:
                budget = self._project_budgets[project_id]
                spending = self._project_spending.get(project_id, 0.0)
                usage_percent = (spending / budget) * 100
                
                status["project_status"][project_id] = {
                    "budget_usd": budget,
                    "spending_usd": spending,
                    "remaining_usd": budget - spending,
                    "usage_percent": usage_percent,
                    "status": self._get_budget_health_status(usage_percent)
                }
        else:
            # All projects
            for pid, budget in self._project_budgets.items():
                spending = self._project_spending.get(pid, 0.0)
                usage_percent = (spending / budget) * 100
                
                status["project_status"][pid] = {
                    "budget_usd": budget,
                    "spending_usd": spending,
                    "remaining_usd": budget - spending,
                    "usage_percent": usage_percent,
                    "status": self._get_budget_health_status(usage_percent)
                }
        
        return status
    
    def _get_budget_health_status(self, usage_percent: float) -> str:
        """Get budget health status based on usage percentage."""
        if usage_percent >= self.config.budget_critical_threshold_percent:
            return "critical"
        elif usage_percent >= self.config.budget_warning_threshold_percent:
            return "warning"
        else:
            return "healthy"
    
    async def reset_monthly_budgets(self) -> Dict[str, Any]:
        """Reset monthly spending counters (typically called at month start)."""
        reset_info = {
            "reset_at": time.time(),
            "previous_spending": {
                "global": self._global_spending,
                "tenants": dict(self._tenant_spending),
                "projects": dict(self._project_spending)
            }
        }
        
        # Reset spending counters
        self._global_spending = 0.0
        self._tenant_spending.clear()
        self._project_spending.clear()
        
        # Clear enforcement actions
        await self.cache_manager.invalidate_pattern("budget_block:*")
        await self.cache_manager.invalidate_pattern("budget_throttle:*")
        
        logger.info("Monthly budgets reset")
        return reset_info


# Global budget manager instance
_budget_manager: Optional[BudgetManager] = None


def get_budget_manager() -> BudgetManager:
    """Get the global budget manager instance."""
    global _budget_manager
    if _budget_manager is None:
        _budget_manager = BudgetManager()
    return _budget_manager