#!/usr/bin/env python3
"""
Enterprise AI Platform - Policy Service

Handles policy evaluation and enforcement for the ATP platform.
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

# Import policy components from router service
try:
    from compliance_validator import ComplianceValidator
    from policy_engine import PolicyEngine
except ImportError:
    # Fallback if components don't exist
    logging.warning("Policy components not found, using mock implementations")

    class PolicyEngine:
        async def evaluate_policy(self, request: dict[str, Any], context: dict[str, Any]):
            return {"allowed": True, "reason": "mock_policy"}

    class ComplianceValidator:
        async def validate_compliance(self, request: dict[str, Any]):
            return {"compliant": True, "issues": []}


app = FastAPI(title="ATP Policy Service", version="1.0.0")
policy_engine = PolicyEngine()
compliance_validator = ComplianceValidator()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

logger = logging.getLogger(__name__)


class PolicyRequest(BaseModel):
    """Policy evaluation request."""

    request_data: dict[str, Any]
    context: dict[str, Any]


class ComplianceRequest(BaseModel):
    """Compliance validation request."""

    request_data: dict[str, Any]
    tenant_id: str


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "policy"}


@app.post("/policy/evaluate")
async def evaluate_policy(request: PolicyRequest):
    """Evaluate a request against policies."""
    try:
        result = await policy_engine.evaluate_policy(request.request_data, request.context)
        return result
    except Exception as e:
        logger.error(f"Policy evaluation failed: {e}")
        raise HTTPException(status_code=500, detail="Policy evaluation failed")


@app.post("/policy/compliance")
async def validate_compliance(request: ComplianceRequest):
    """Validate compliance for a request."""
    try:
        result = await compliance_validator.validate_compliance(request.request_data)
        return result
    except Exception as e:
        logger.error(f"Compliance validation failed: {e}")
        raise HTTPException(status_code=500, detail="Compliance validation failed")


@app.get("/policy/list")
async def list_policies():
    """List all active policies."""
    try:
        # Implementation would return actual policies
        return {"policies": [], "count": 0}
    except Exception as e:
        logger.error(f"Failed to list policies: {e}")
        raise HTTPException(status_code=500, detail="Failed to list policies")


async def main():
    """Main entry point for the policy service."""
    logger.info("Starting ATP Policy Service...")

    config = uvicorn.Config(app, host="0.0.0.0", port=8082, log_level="info")

    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
