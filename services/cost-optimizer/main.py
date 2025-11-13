#!/usr/bin/env python3
"""
Enterprise AI Platform - Cost Optimizer Service

Handles cost optimization and budget management for the ATP platform.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

# Add the router service to the Python path for shared components
sys.path.insert(0, str(Path(__file__).parent.parent / "router"))

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Import cost optimization components from router service
try:
    from cost_optimization.budget_manager import BudgetManager
    from cost_optimization.cost_forecaster import CostForecaster
    from cost_optimization.cost_optimizer import CostOptimizer
    from pricing.pricing_manager import PricingManager
except ImportError:
    # Fallback if components don't exist
    logging.warning("Cost optimization components not found, using mock implementations")

    class CostOptimizer:
        async def optimize_route(self, request: dict[str, Any]):
            return {"provider": "mock", "estimated_cost": 0.01}

    class BudgetManager:
        async def check_budget(self, tenant_id: str, cost: float):
            return {"allowed": True, "remaining": 100.0}

    class CostForecaster:
        async def forecast_costs(self, tenant_id: str, days: int):
            return {"forecast": [1.0] * days}

    class PricingManager:
        async def get_current_pricing(self):
            return {"providers": {}}


app = FastAPI(title="ATP Cost Optimizer Service", version="1.0.0")
cost_optimizer = CostOptimizer()
budget_manager = BudgetManager()
cost_forecaster = CostForecaster()
pricing_manager = PricingManager()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)


class OptimizationRequest(BaseModel):
    """Cost optimization request."""

    request_data: dict[str, Any]
    tenant_id: str
    max_cost: float


class BudgetCheckRequest(BaseModel):
    """Budget check request."""

    tenant_id: str
    estimated_cost: float


class ForecastRequest(BaseModel):
    """Cost forecast request."""

    tenant_id: str
    days: int = 30


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "cost-optimizer"}


@app.post("/cost/optimize")
async def optimize_cost(request: OptimizationRequest):
    """Optimize cost for a request."""
    try:
        result = await cost_optimizer.optimize_route(request.request_data)
        return result
    except Exception as e:
        logger.error(f"Cost optimization failed: {e}")
        raise HTTPException(status_code=500, detail="Cost optimization failed") from e


@app.post("/cost/budget/check")
async def check_budget(request: BudgetCheckRequest):
    """Check budget availability."""
    try:
        result = await budget_manager.check_budget(request.tenant_id, request.estimated_cost)
        return result
    except Exception as e:
        logger.error(f"Budget check failed: {e}")
        raise HTTPException(status_code=500, detail="Budget check failed") from e


@app.post("/cost/forecast")
async def forecast_costs(request: ForecastRequest):
    """Forecast costs for a tenant."""
    try:
        result = await cost_forecaster.forecast_costs(request.tenant_id, request.days)
        return result
    except Exception as e:
        logger.error(f"Cost forecasting failed: {e}")
        raise HTTPException(status_code=500, detail="Cost forecasting failed") from e


@app.get("/cost/pricing")
async def get_current_pricing():
    """Get current pricing information."""
    try:
        result = await pricing_manager.get_current_pricing()
        return result
    except Exception as e:
        logger.error(f"Failed to get pricing: {e}")
        raise HTTPException(status_code=500, detail="Failed to get pricing") from e


async def main():
    """Main entry point for the cost optimizer service."""
    logger.info("Starting ATP Cost Optimizer Service...")

    config = uvicorn.Config(app, host="0.0.0.0", port=8083, log_level="info")

    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
