# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Per-tenant rate limiting service with Redis."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as redis

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration for a tenant."""

    tenant_id: str
    tier: str  # "free", "pro", "enterprise"

    # Request limits
    requests_per_second: int = 10
    requests_per_minute: int = 600
    requests_per_hour: int = 36000

    # Token limits
    tokens_per_day: int = 1_000_000

    # Cost limits
    cost_per_day_usd: float = 100.0

    # Burst multiplier
    burst_multiplier: float = 1.5


class RateLimitService:
    """
    Multi-level rate limiting service.

    Supports:
    - Requests per second/minute/hour (sliding window)
    - Token quotas per day
    - Cost quotas per day
    - Per-tenant configuration
    """

    def __init__(self, redis_client: redis.Redis | None = None):
        """
        Initialize rate limit service.

        Args:
            redis_client: Redis client for distributed rate limiting
        """
        self.redis = redis_client
        self._local_cache: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def check_rate_limit(
        self,
        tenant_id: str,
        config: RateLimitConfig,
    ) -> tuple[bool, dict]:
        """
        Check if request is within rate limits.

        Args:
            tenant_id: The tenant making the request
            config: Rate limit configuration

        Returns:
            Tuple of (allowed, info_dict)
        """
        if self.redis is None:
            # Fallback to local in-memory rate limiting
            return await self._check_local_rate_limit(tenant_id, config)

        # Check multiple windows
        checks = [
            ("rps", config.requests_per_second, 1),
            ("rpm", config.requests_per_minute, 60),
            ("rph", config.requests_per_hour, 3600),
        ]

        for window_name, limit, window_seconds in checks:
            allowed, remaining = await self._check_sliding_window(
                tenant_id=tenant_id,
                window_name=window_name,
                limit=limit,
                window_seconds=window_seconds,
            )

            if not allowed:
                return False, {
                    "allowed": False,
                    "window": window_name,
                    "limit": limit,
                    "remaining": 0,
                    "reset_at": (datetime.now() + timedelta(seconds=window_seconds)).isoformat(),
                }

        return True, {
            "allowed": True,
            "remaining": remaining,
        }

    async def _check_sliding_window(
        self,
        tenant_id: str,
        window_name: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """
        Check sliding window rate limit using Redis.

        Args:
            tenant_id: The tenant ID
            window_name: Window name (rps, rpm, rph)
            limit: Request limit for window
            window_seconds: Window duration in seconds

        Returns:
            Tuple of (allowed, remaining_requests)
        """
        if self.redis is None:
            raise RuntimeError("Redis client not available")

        key = f"ratelimit:{tenant_id}:{window_name}"
        now = time.time()
        window_start = now - window_seconds

        # Redis pipeline for atomic operations
        pipe = self.redis.pipeline()

        # Remove old entries outside window
        pipe.zremrangebyscore(key, 0, window_start)

        # Count current requests in window
        pipe.zcard(key)

        # Add current request timestamp
        pipe.zadd(key, {str(now): now})

        # Set expiry on key
        pipe.expire(key, window_seconds)

        # Execute pipeline
        results = await pipe.execute()

        # Get count (from zcard operation)
        current_count = results[1]

        # Check if within limit
        allowed = current_count < limit
        remaining = max(0, limit - current_count - 1)

        if not allowed:
            logger.debug(
                "Rate limit exceeded",
                tenant=tenant_id,
                window=window_name,
                current=current_count,
                limit=limit,
            )

        return allowed, remaining

    async def _check_local_rate_limit(
        self,
        tenant_id: str,
        config: RateLimitConfig,
    ) -> tuple[bool, dict]:
        """Fallback local rate limiting (in-memory)."""
        async with self._lock:
            now = time.time()

            if tenant_id not in self._local_cache:
                self._local_cache[tenant_id] = {
                    "requests": [],
                }

            cache = self._local_cache[tenant_id]
            requests = cache["requests"]

            # Remove old requests (older than 1 hour)
            requests = [r for r in requests if now - r < 3600]
            cache["requests"] = requests

            # Check limits
            rps_requests = sum(1 for r in requests if now - r < 1)
            if rps_requests >= config.requests_per_second:
                return False, {"allowed": False, "window": "rps"}

            rpm_requests = sum(1 for r in requests if now - r < 60)
            if rpm_requests >= config.requests_per_minute:
                return False, {"allowed": False, "window": "rpm"}

            rph_requests = len(requests)
            if rph_requests >= config.requests_per_hour:
                return False, {"allowed": False, "window": "rph"}

            # Add current request
            requests.append(now)

            return True, {"allowed": True, "remaining": config.requests_per_second - rps_requests}

    async def check_token_quota(
        self,
        tenant_id: str,
        tokens: int,
        config: RateLimitConfig,
    ) -> tuple[bool, dict]:
        """
        Check token quota.

        Args:
            tenant_id: The tenant ID
            tokens: Number of tokens to use
            config: Rate limit configuration

        Returns:
            Tuple of (allowed, info_dict)
        """
        if self.redis is None:
            return True, {"allowed": True}  # Fallback

        key = f"quota:tokens:{tenant_id}:daily"

        # Get current usage
        current = await self.redis.get(key)
        current_usage = int(current) if current else 0

        remaining = config.tokens_per_day - current_usage

        if current_usage + tokens > config.tokens_per_day:
            return False, {
                "allowed": False,
                "quota_type": "tokens",
                "limit": config.tokens_per_day,
                "current": current_usage,
                "remaining": remaining,
            }

        # Increment usage
        pipe = self.redis.pipeline()
        pipe.incrby(key, tokens)
        pipe.expire(key, 86400)  # 24 hours
        await pipe.execute()

        return True, {
            "allowed": True,
            "current": current_usage + tokens,
            "remaining": remaining - tokens,
        }

    async def check_cost_quota(
        self,
        tenant_id: str,
        cost_usd: float,
        config: RateLimitConfig,
    ) -> tuple[bool, dict]:
        """
        Check cost quota.

        Args:
            tenant_id: The tenant ID
            cost_usd: Cost in USD
            config: Rate limit configuration

        Returns:
            Tuple of (allowed, info_dict)
        """
        if self.redis is None:
            return True, {"allowed": True}  # Fallback

        key = f"quota:cost:{tenant_id}:daily"

        # Use hash for precise float tracking
        current = await self.redis.hget(key, "cost")
        current_cost = float(current) if current else 0.0

        remaining = config.cost_per_day_usd - current_cost

        if current_cost + cost_usd > config.cost_per_day_usd:
            return False, {
                "allowed": False,
                "quota_type": "cost",
                "limit_usd": config.cost_per_day_usd,
                "current_usd": current_cost,
                "remaining_usd": remaining,
            }

        # Increment cost
        pipe = self.redis.pipeline()
        pipe.hincrbyfloat(key, "cost", cost_usd)
        pipe.expire(key, 86400)
        await pipe.execute()

        return True, {
            "allowed": True,
            "current_usd": current_cost + cost_usd,
            "remaining_usd": remaining - cost_usd,
        }

    async def reset_quota(self, tenant_id: str, quota_type: str = "all") -> None:
        """
        Reset quotas for a tenant.

        Args:
            tenant_id: The tenant ID
            quota_type: Type to reset (tokens, cost, all)
        """
        if self.redis is None:
            return

        if quota_type in ("tokens", "all"):
            await self.redis.delete(f"quota:tokens:{tenant_id}:daily")

        if quota_type in ("cost", "all"):
            await self.redis.delete(f"quota:cost:{tenant_id}:daily")

        logger.info(f"Quota reset for tenant: {tenant_id}, type: {quota_type}")
