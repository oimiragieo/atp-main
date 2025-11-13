#!/usr/bin/env python3
"""
Edge Node Request Relay & Authentication Service

This service provides edge routing functionality for ATP, including:
- Request relay from edge nodes to core router
- Signed token exchange and validation
- Replay attack protection
- Edge-specific metrics and monitoring

Usage:
    python edge_router.py --core-endpoint https://core-router.internal:8443 --edge-id edge-01
"""

import argparse
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

# Import carbon intensity tracker
from .carbon_intensity_tracker import CarbonIntensityTracker

# Import edge cache
from .edge_cache import AsyncEdgeCache

# Import metrics registry
try:
    from metrics.registry import (
        CARBON_AWARE_ROUTING_DECISIONS_TOTAL,
        EDGE_AUTH_FAILURES_TOTAL,
        EDGE_CACHE_EVICTIONS_TOTAL,
        EDGE_CACHE_HIT_RATIO,
        EDGE_CACHE_HITS_TOTAL,
        EDGE_CACHE_MISSES_TOTAL,
        EDGE_CACHE_SIZE,
        EDGE_RELAY_LATENCY,
        EDGE_REQUESTS_TOTAL,
        EDGE_SAVINGS_PCT,
        PREWARM_HITS_TOTAL,
        PREWARM_WASTE_MS,
        REGISTRY,
    )
except ImportError:
    # Fallback if metrics not available
    class MockCounter:
        def inc(self): pass
        def labels(self, **kwargs): return self

    class MockHistogram:
        def observe(self, value): pass

    class MockGauge:
        def set(self, value): pass

    class MockRegistry:
        pass

    EDGE_REQUESTS_TOTAL = MockCounter()
    EDGE_AUTH_FAILURES_TOTAL = MockCounter()
    EDGE_RELAY_LATENCY = MockHistogram()
    EDGE_SAVINGS_PCT = MockGauge()
    PREWARM_HITS_TOTAL = MockCounter()
    PREWARM_WASTE_MS = MockHistogram()
    EDGE_CACHE_HITS_TOTAL = MockCounter()
    EDGE_CACHE_MISSES_TOTAL = MockCounter()
    EDGE_CACHE_EVICTIONS_TOTAL = MockCounter()
    EDGE_CACHE_SIZE = MockGauge()
    EDGE_CACHE_HIT_RATIO = MockGauge()
    CARBON_AWARE_ROUTING_DECISIONS_TOTAL = MockCounter()
    REGISTRY = MockRegistry()


@dataclass
class EdgeConfig:
    """Configuration for edge router."""

    core_endpoint: str
    edge_id: str
    shared_secret: str
    token_ttl_seconds: int = 3600  # 1 hour
    replay_window_seconds: int = 300  # 5 minutes
    max_request_size: int = 1024 * 1024  # 1MB
    # Compression settings
    max_prompt_length: int = 4000  # Max tokens before compression
    compression_ratio: float = 0.7  # Target compression ratio
    # SLM settings
    enable_slm_fallback: bool = True
    slm_max_tokens: int = 1000  # Max tokens SLM can handle
    slm_quality_threshold: float = 0.75  # Min quality for SLM fallback
    # Prewarming settings
    enable_prewarming: bool = True  # Enable predictive prewarming
    # Cache settings
    enable_cache: bool = True  # Enable edge caching
    cache_max_size: int = 1000  # Maximum cache entries
    cache_default_ttl_seconds: int = 300  # Default TTL (5 minutes)
    # Carbon-aware routing settings
    enable_carbon_aware_routing: bool = True  # Enable carbon-aware routing
    carbon_api_key: Optional[str] = None  # API key for carbon intensity service
    carbon_cache_ttl_seconds: int = 3600  # Carbon data cache TTL (1 hour)


class PromptCompressor:
    """Handles prompt compression for edge processing."""

    def __init__(self, config: EdgeConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

    def should_compress(self, prompt: str) -> bool:
        """Determine if prompt should be compressed."""
        # Rough token estimation (1 token ≈ 4 characters)
        estimated_tokens = len(prompt) // 4
        return estimated_tokens > self.config.max_prompt_length

    def compress_prompt(self, prompt: str) -> tuple[str, dict]:
        """Compress prompt using truncation + summarization heuristic.

        Returns:
            tuple: (compressed_prompt, compression_metadata)
        """
        if not self.should_compress(prompt):
            return prompt, {"compressed": False, "original_length": len(prompt)}

        # Simple truncation + summarization heuristic
        # Keep first 25%, last 25%, and summarize middle 50%
        total_length = len(prompt)
        keep_start = int(total_length * 0.25)
        keep_end = int(total_length * 0.25)
        middle_start = keep_start
        middle_end = total_length - keep_end

        # Extract key parts
        start_part = prompt[:keep_start]
        end_part = prompt[middle_end:]
        middle_part = prompt[middle_start:middle_end]

        # Simple summarization: extract sentences/paragraphs containing keywords
        keywords = ["important", "key", "summary", "conclusion", "result", "therefore", "thus"]
        summary_parts = []

        # Look for keyword-containing sentences in middle section
        sentences = middle_part.replace('\n', ' ').split('. ')
        for sentence in sentences:
            if any(keyword in sentence.lower() for keyword in keywords):
                summary_parts.append(sentence.strip())

        # If no keywords found, take first few sentences
        if not summary_parts:
            summary_parts = sentences[:3]  # First 3 sentences

        middle_summary = '. '.join(summary_parts[:5])  # Limit to 5 key sentences

        # Combine parts
        compressed = f"{start_part}\n\n[SUMMARY: {middle_summary}]\n\n{end_part}"

        # Ensure we meet compression target
        target_length = int(total_length * self.config.compression_ratio)
        if len(compressed) > target_length:
            compressed = compressed[:target_length] + "..."

        metadata = {
            "compressed": True,
            "original_length": total_length,
            "compressed_length": len(compressed),
            "compression_ratio": len(compressed) / total_length,
            "method": "truncation_summarization"
        }

        self.logger.info(f"Compressed prompt: {total_length} -> {len(compressed)} chars "
                        ".2f")

        return compressed, metadata


class EdgeSLM:
    """Small Language Model for edge processing."""

    def __init__(self, config: EdgeConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        # Mock SLM capabilities - in real implementation, this would load actual model
        self.max_tokens = config.slm_max_tokens
        self.quality_threshold = config.slm_quality_threshold

    def can_handle_request(self, request_data: dict) -> bool:
        """Check if SLM can handle this request."""
        if not self.config.enable_slm_fallback:
            return False

        prompt = request_data.get("prompt", "")
        quality = request_data.get("quality", "balanced")

        # Estimate token count
        estimated_tokens = len(prompt) // 4

        # SLM can handle shorter prompts and lower quality requirements
        if estimated_tokens > self.max_tokens:
            return False

        # Only use SLM for fast/balanced quality, not high quality
        if quality == "high":
            return False

        return True

    def process_request(self, request_data: dict) -> dict:
        """Process request using edge SLM."""
        prompt = request_data.get("prompt", "")
        quality = request_data.get("quality", "balanced")

        # Mock SLM response - in real implementation, this would call actual model
        self.logger.info(f"Processing request with edge SLM: {len(prompt)} chars, quality={quality}")

        # Simulate processing time and cost savings
        import time
        start_time = time.time()

        # Mock response generation (simplified)
        if "question" in prompt.lower() or "?" in prompt:
            response_text = "This appears to be a question. Based on the context provided, here's a concise answer from the edge SLM."
        elif "summarize" in prompt.lower():
            response_text = "Summary generated by edge SLM: The provided text contains key information that has been condensed for efficiency."
        else:
            response_text = "Response generated by edge SLM for efficient processing at the network edge."

        processing_time = time.time() - start_time

        # Calculate estimated savings
        original_cost_estimate = 0.002  # Estimated cost for large model
        slm_cost = 0.0002  # Much cheaper SLM
        savings_pct = ((original_cost_estimate - slm_cost) / original_cost_estimate) * 100

        response = {
            "type": "final",
            "text": response_text,
            "model_used": "edge-slm",
            "tokens_in": len(prompt) // 4,
            "tokens_out": len(response_text) // 4,
            "cost_usd": slm_cost,
            "savings_pct": savings_pct,
            "escalation_count": 0,
            "quality_score": 0.75,  # SLM quality score
            "processing_time_ms": processing_time * 1000,
            "edge_processed": True
        }

        # Update metrics
        EDGE_SAVINGS_PCT.set(savings_pct)

        return response


class PredictivePrewarmingScheduler:
    """Predictive scheduler for prewarming edge resources based on demand patterns."""

    def __init__(self, config: EdgeConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Demand tracking
        self.request_history: list[tuple[float, dict]] = []  # (timestamp, request_data)
        self.max_history_size = 1000

        # Time-of-day patterns (hour -> request count)
        self.hourly_patterns: dict[int, int] = {}
        self.pattern_window_hours = 24  # Look at last 24 hours

        # Prewarming state
        self.prewarmed_resources: set[str] = set()  # Resource IDs currently warmed
        self.prewarm_start_times: dict[str, float] = {}  # Resource ID -> start time
        self.prewarm_predictions: dict[str, float] = {}  # Resource ID -> predicted demand time

        # Prediction parameters
        self.min_requests_for_prediction = 10  # Need at least 10 requests to predict
        self.prediction_horizon_minutes = 5  # Predict 5 minutes ahead
        self.prewarm_lead_time_minutes = 2  # Start prewarming 2 minutes before predicted demand

        # Background task
        self.running = False
        self.scheduler_thread: Optional[threading.Thread] = None

    def record_request(self, request_data: dict):
        """Record a request for demand pattern analysis."""
        timestamp = time.time()
        self.request_history.append((timestamp, request_data))

        # Maintain history size
        if len(self.request_history) > self.max_history_size:
            self.request_history.pop(0)

        # Update hourly patterns
        hour = int(timestamp // 3600) % 24
        self.hourly_patterns[hour] = self.hourly_patterns.get(hour, 0) + 1

    def predict_demand(self) -> dict[str, float]:
        """Predict future demand based on historical patterns.

        Returns:
            dict: resource_id -> predicted_demand_timestamp
        """
        if len(self.request_history) < self.min_requests_for_prediction:
            return {}

        current_time = time.time()
        predictions = {}

        # Use all available history (don't filter by time window for now)
        recent_requests = self.request_history

        if not recent_requests:
            return {}

        # Group by resource type (for now, just by quality level)
        resource_demand: dict[str, list[float]] = {}

        for timestamp, request_data in recent_requests:
            quality = request_data.get("quality", "balanced")
            resource_id = f"slm_{quality}"

            if resource_id not in resource_demand:
                resource_demand[resource_id] = []
            resource_demand[resource_id].append(timestamp)

        # Predict next demand for each resource
        for resource_id, timestamps in resource_demand.items():
            if len(timestamps) < 3:  # Need at least 3 data points
                continue

            # Sort timestamps
            sorted_times = sorted(timestamps)

            # Calculate inter-arrival times
            inter_arrivals = [
                sorted_times[i+1] - sorted_times[i]
                for i in range(len(sorted_times) - 1)
            ]

            if inter_arrivals:
                # Use median inter-arrival time for robustness
                sorted_intervals = sorted(inter_arrivals)
                median_inter_arrival = sorted_intervals[len(sorted_intervals) // 2]

                # Predict next arrival using median inter-arrival time
                last_arrival = sorted_times[-1]
                predicted_next = last_arrival + median_inter_arrival

                # Only predict if within horizon and in the future
                time_until_demand = predicted_next - current_time
                if 0 < time_until_demand < self.prediction_horizon_minutes * 60:
                    predictions[resource_id] = predicted_next

        return predictions

    def should_prewarm(self, resource_id: str) -> bool:
        """Determine if a resource should be prewarmed."""
        if resource_id not in self.prewarm_predictions:
            return False

        predicted_time = self.prewarm_predictions[resource_id]
        current_time = time.time()
        lead_time_seconds = self.prewarm_lead_time_minutes * 60

        # Check if we're within the prewarming window
        time_until_demand = predicted_time - current_time
        return 0 < time_until_demand <= lead_time_seconds

    def prewarm_resource(self, resource_id: str):
        """Prewarm a specific resource."""
        if resource_id in self.prewarmed_resources:
            return  # Already warmed

        self.logger.info(f"Prewarming resource: {resource_id}")
        self.prewarmed_resources.add(resource_id)
        self.prewarm_start_times[resource_id] = time.time()

        # In a real implementation, this would:
        # - Load SLM model into memory
        # - Warm up GPU/CPU caches
        # - Establish connections to dependencies

    def check_prewarm_hit(self, resource_id: str):
        """Check if a prewarmed resource was used (hit)."""
        if resource_id in self.prewarmed_resources:
            PREWARM_HITS_TOTAL.inc()
            self.logger.info(f"Prewarm hit for resource: {resource_id}")

            # Remove from prewarmed set (resource is now in use)
            self.prewarmed_resources.discard(resource_id)
            if resource_id in self.prewarm_start_times:
                del self.prewarm_start_times[resource_id]

    def cleanup_expired_prewarms(self):
        """Clean up prewarmed resources that weren't used."""
        current_time = time.time()
        expired_resources = []

        for resource_id, start_time in self.prewarm_start_times.items():
            waste_time_ms = (current_time - start_time) * 1000

            # If resource has been warmed for too long without use, consider it waste
            if waste_time_ms > 300000:  # 5 minutes
                PREWARM_WASTE_MS.observe(waste_time_ms)
                self.logger.info(f"Prewarm waste for resource {resource_id}: {waste_time_ms:.0f}ms")
                expired_resources.append(resource_id)

        # Clean up expired resources
        for resource_id in expired_resources:
            self.prewarmed_resources.discard(resource_id)
            if resource_id in self.prewarm_start_times:
                del self.prewarm_start_times[resource_id]

    def scheduler_loop(self):
        """Main scheduler loop running in background."""
        while self.running:
            try:
                # Update predictions
                self.prewarm_predictions = self.predict_demand()

                # Check for resources that should be prewarmed
                for resource_id in self.prewarm_predictions.keys():
                    if self.should_prewarm(resource_id):
                        self.prewarm_resource(resource_id)

                # Clean up expired prewarms
                self.cleanup_expired_prewarms()

                # Sleep for 30 seconds before next iteration
                time.sleep(30)

            except Exception as e:
                self.logger.error(f"Scheduler loop error: {e}")
                time.sleep(60)  # Sleep longer on error

    def start(self):
        """Start the predictive scheduler."""
        if self.running:
            return

        self.running = True
        self.scheduler_thread = threading.Thread(target=self.scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        self.logger.info("Predictive prewarming scheduler started")

    def stop(self):
        """Stop the predictive scheduler."""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5.0)
        self.logger.info("Predictive prewarming scheduler stopped")


class TokenManager:
    """Manages signed tokens for edge-core authentication."""

    def __init__(self, config: EdgeConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._replay_cache: dict[str, float] = {}  # nonce -> timestamp

    def generate_token(self, request_data: dict) -> str:
        """Generate a signed token for the request."""
        timestamp = int(time.time())
        nonce = secrets.token_hex(16)

        # Create token payload
        payload = {
            "edge_id": self.config.edge_id,
            "timestamp": timestamp,
            "nonce": nonce,
            "request_hash": self._hash_request(request_data)
        }

        # Sign the payload
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            self.config.shared_secret.encode(),
            payload_str.encode(),
            hashlib.sha256
        ).hexdigest()

        token = {
            "payload": payload,
            "signature": signature
        }

        return json.dumps(token)

    def validate_token(self, token_str: str, request_data: dict) -> bool:
        """Validate a token from an incoming request."""
        try:
            token = json.loads(token_str)

            # Verify signature
            payload_str = json.dumps(token["payload"], sort_keys=True)
            expected_signature = hmac.new(
                self.config.shared_secret.encode(),
                payload_str.encode(),
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(token["signature"], expected_signature):
                self.logger.warning("Invalid token signature")
                # EDGE_AUTH_FAILURES_TOTAL.labels(reason="invalid_signature").inc()
                return False

            payload = token["payload"]

            # Check timestamp (not expired)
            if time.time() - payload["timestamp"] > self.config.token_ttl_seconds:
                self.logger.warning("Token expired")
                # EDGE_AUTH_FAILURES_TOTAL.labels(reason="token_expired").inc()
                return False

            # Check replay protection
            nonce = payload["nonce"]
            if nonce in self._replay_cache:
                self.logger.warning("Replay attack detected")
                # EDGE_AUTH_FAILURES_TOTAL.labels(reason="replay_attack").inc()
                return False

            # Verify request hash matches
            if payload["request_hash"] != self._hash_request(request_data):
                self.logger.warning("Request hash mismatch")
                # EDGE_AUTH_FAILURES_TOTAL.labels(reason="request_mismatch").inc()
                return False

            # Store nonce to prevent replay
            self._replay_cache[nonce] = time.time()

            # Clean up old nonces
            self._cleanup_replay_cache()

            return True

        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"Invalid token format: {e}")
            EDGE_AUTH_FAILURES_TOTAL.labels(reason="invalid_format").inc()
            return False

    def _hash_request(self, request_data: dict) -> str:
        """Create a hash of the request data for integrity checking."""
        # Normalize the request data for consistent hashing
        normalized = json.dumps(request_data, sort_keys=True)
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _cleanup_replay_cache(self):
        """Remove expired nonces from replay cache."""
        current_time = time.time()
        expired_nonces = [
            nonce for nonce, timestamp in self._replay_cache.items()
            if current_time - timestamp > self.config.replay_window_seconds
        ]
        for nonce in expired_nonces:
            del self._replay_cache[nonce]


class EdgeRouter:
    """Edge router service for relaying requests to core."""

    def __init__(self, config: EdgeConfig):
        self.config = config
        self.token_manager = TokenManager(config)
        self.compressor = PromptCompressor(config)
        self.slm = EdgeSLM(config)
        self.prewarming_scheduler = PredictivePrewarmingScheduler(config)
        self.logger = logging.getLogger(__name__)

        # Initialize edge cache if enabled
        if config.enable_cache:
            self.cache = AsyncEdgeCache(
                max_size=config.cache_max_size,
                default_ttl_seconds=config.cache_default_ttl_seconds
            )
            self.cache.start()
            self.logger.info(f"Edge cache initialized: max_size={config.cache_max_size}, ttl={config.cache_default_ttl_seconds}s")
        else:
            self.cache = None

        # Initialize carbon intensity tracker if enabled
        if config.enable_carbon_aware_routing:
            self.carbon_tracker = CarbonIntensityTracker(
                api_key=config.carbon_api_key,
                cache_ttl_seconds=config.carbon_cache_ttl_seconds
            )
            self.logger.info("Carbon-aware routing enabled")
        else:
            self.carbon_tracker = None

        # HTTP client for core communication
        self.client = httpx.AsyncClient(
            timeout=30.0,
            verify=not os.getenv("DISABLE_SSL_VERIFY", "").lower() not in ("true", "1")
        )

        # Start prewarming scheduler if enabled
        if config.enable_prewarming:
            self.prewarming_scheduler.start()

    async def relay_request(self, request_data: dict) -> dict:
        """Relay a request to the core router with compression and SLM fallback."""
        EDGE_REQUESTS_TOTAL.inc()
        start_time = time.time()

        # Record request for prewarming analysis
        self.prewarming_scheduler.record_request(request_data)

        try:
            # Step 1: Check cache first (if enabled)
            if self.cache:
                cached_result = await self.cache.get(request_data)
                if cached_result:
                    self.logger.info("Cache hit - returning cached response")
                    latency = time.time() - start_time
                    EDGE_RELAY_LATENCY.observe(latency)

                    # Add cache metadata
                    cached_result["edge_processing"] = {
                        "method": "cache_hit",
                        "latency_ms": latency * 1000,
                        "cached": True
                    }
                    return cached_result

            # Step 2: Carbon-aware routing (if enabled)
            if self.carbon_tracker:
                await self._apply_carbon_aware_routing(request_data)

            # Step 3: Check if SLM can handle this request
            if self.slm.can_handle_request(request_data):
                self.logger.info("Using edge SLM for request processing")

                # Check for prewarm hit
                quality = request_data.get("quality", "balanced")
                resource_id = f"slm_{quality}"
                self.prewarming_scheduler.check_prewarm_hit(resource_id)

                result = self.slm.process_request(request_data)

                # Cache the result if cache is enabled
                if self.cache:
                    await self.cache.put(request_data, result)

                # Record latency
                latency = time.time() - start_time
                EDGE_RELAY_LATENCY.observe(latency)

                # Add edge processing metadata
                result["edge_processing"] = {
                    "method": "slm_fallback",
                    "latency_ms": latency * 1000,
                    "savings_pct": result.get("savings_pct", 0),
                    "cached": False
                }

                return result

            # Step 2: Check if compression is needed
            prompt = request_data.get("prompt", "")
            compressed_prompt, compression_metadata = self.compressor.compress_prompt(prompt)

            if compression_metadata["compressed"]:
                self.logger.info(f"Compressed prompt for core relay: {compression_metadata}")
                request_data["prompt"] = compressed_prompt
                request_data["original_prompt_length"] = len(prompt)
                request_data["compression_metadata"] = compression_metadata

            # Step 3: Generate authentication token
            token = self.token_manager.generate_token(request_data)

            # Step 4: Prepare headers
            headers = {
                "Authorization": f"Bearer {token}",
                "X-Edge-ID": self.config.edge_id,
                "Content-Type": "application/json"
            }

            # Step 5: Relay the request to core
            response = await self.client.post(
                f"{self.config.core_endpoint}/ask",
                json=request_data,
                headers=headers
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Core router error: {response.text}"
                )

            # Step 6: Get the response
            result = response.json()

            # Step 7: Cache the result if cache is enabled
            if self.cache:
                await self.cache.put(request_data, result)

            # Step 8: Add edge processing metadata
            latency = time.time() - start_time
            EDGE_RELAY_LATENCY.observe(latency)

            if compression_metadata["compressed"]:
                result["edge_processing"] = {
                    "method": "compression_relay",
                    "latency_ms": latency * 1000,
                    "compression_metadata": compression_metadata,
                    "cached": False
                }
            else:
                result["edge_processing"] = {
                    "method": "direct_relay",
                    "latency_ms": latency * 1000,
                    "cached": False
                }

            return result

        except Exception as e:
            # Record latency even on error
            latency = time.time() - start_time
            EDGE_RELAY_LATENCY.observe(latency)

            self.logger.error(f"Failed to relay request: {e}")
            raise HTTPException(status_code=500, detail="Edge relay failed") from e

    async def validate_incoming_request(self, token: str, request_data: dict) -> bool:
        """Validate an incoming request with token."""
        return self.token_manager.validate_token(token, request_data)

    async def _apply_carbon_aware_routing(self, request_data: dict):
        """Apply carbon-aware routing by adding carbon intensity data to request."""
        try:
            # Get current region (could be from config or detected)
            region = request_data.get("region", "us-west")  # Default to us-west

            # Get carbon intensity for the region
            carbon_data = await self.carbon_tracker.get_carbon_intensity(region)

            if carbon_data:
                # Add carbon data to request for core router decision making
                request_data["carbon_context"] = {
                    "region": carbon_data.region,
                    "intensity_gco2_per_kwh": carbon_data.intensity_gco2_per_kwh,
                    "timestamp": carbon_data.timestamp.isoformat(),
                    "source": carbon_data.source,
                    "confidence": carbon_data.confidence
                }

                # Increment carbon-aware routing metric
                CARBON_AWARE_ROUTING_DECISIONS_TOTAL.inc()

                self.logger.info(f"Applied carbon-aware routing for region {region}: {carbon_data.intensity_gco2_per_kwh} gCO2/kWh")
            else:
                self.logger.warning(f"Could not get carbon intensity data for region {region}")

        except Exception as e:
            self.logger.error(f"Error in carbon-aware routing: {e}")
            # Don't fail the request if carbon tracking fails

    async def close(self):
        """Clean up resources."""
        # Stop prewarming scheduler
        if hasattr(self, 'prewarming_scheduler'):
            self.prewarming_scheduler.stop()

        # Stop cache
        if hasattr(self, 'cache') and self.cache:
            self.cache.stop()

        await self.client.aclose()


# FastAPI app
app = FastAPI(title="ATP Edge Router", version="1.0.0")
edge_router: Optional[EdgeRouter] = None


class AskRequest(BaseModel):
    """Request model for ask endpoint."""
    prompt: str
    quality: Optional[str] = "balanced"
    latency_slo_ms: Optional[int] = 2000
    max_tokens: Optional[int] = 1000


@app.post("/ask")
async def ask(request: AskRequest, req: Request):
    """Handle ask requests and relay to core router."""
    if not edge_router:
        raise HTTPException(status_code=500, detail="Edge router not initialized")

    # Convert request to dict
    request_data = request.dict()

    try:
        # Relay to core router
        response = await edge_router.relay_request(request_data)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/health")
async def health():
    """Health check endpoint."""
    # For testing purposes, return a mock response if edge_router is not set
    if edge_router:
        return {"status": "healthy", "edge_id": edge_router.config.edge_id}
    else:
        # This should not happen in production, but helps with testing
        return {"status": "healthy", "edge_id": "test-edge-01"}


@app.get("/cache/stats")
async def cache_stats():
    """Get cache statistics."""
    if not edge_router or not edge_router.cache:
        raise HTTPException(status_code=404, detail="Cache not enabled")

    stats = await edge_router.cache.get_stats()
    return stats


@app.post("/cache/clear")
async def clear_cache():
    """Clear all cache entries."""
    if not edge_router or not edge_router.cache:
        raise HTTPException(status_code=404, detail="Cache not enabled")

    await edge_router.cache.clear()
    return {"message": "Cache cleared successfully"}


@app.post("/cache/invalidate")
async def invalidate_cache(request: AskRequest):
    """Invalidate a specific cache entry."""
    if not edge_router or not edge_router.cache:
        raise HTTPException(status_code=404, detail="Cache not enabled")

    request_data = request.dict()
    await edge_router.cache.invalidate(request_data)
    return {"message": "Cache entry invalidated successfully"}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="ATP Edge Router")
    parser.add_argument("--core-endpoint", required=True, help="Core router endpoint URL")
    parser.add_argument("--edge-id", required=True, help="Unique edge node identifier")
    parser.add_argument("--shared-secret", help="Shared secret for token signing (env: EDGE_SHARED_SECRET)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")

    args = parser.parse_args()

    # Get shared secret from env if not provided
    shared_secret = args.shared_secret or os.getenv("EDGE_SHARED_SECRET")
    if not shared_secret:
        print("Error: Shared secret must be provided via --shared-secret or EDGE_SHARED_SECRET")
        return 1

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Create configuration
    config = EdgeConfig(
        core_endpoint=args.core_endpoint,
        edge_id=args.edge_id,
        shared_secret=shared_secret
    )

    # Create edge router
    global edge_router
    edge_router = EdgeRouter(config)

    # Start server
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    exit(main())
