# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Central configuration (towards alpha hardening)."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    promote_min_calls: int = int(os.getenv("PROMOTE_MIN_CALLS", "5"))
    promote_cost_improve: float = float(os.getenv("PROMOTE_COST_IMPROVE", "0.9"))
    demote_min_calls: int = int(os.getenv("DEMOTE_MIN_CALLS", "6"))
    demote_cost_regress: float = float(os.getenv("DEMOTE_COST_REGRESS", "1.25"))
    hysteresis_seconds: float = float(os.getenv("PROMO_DEMO_HYSTERESIS_SEC", "5"))
    bandit_strategy: str = os.getenv("BANDIT_STRATEGY", "ucb").lower()
    ucb_explore_factor: float = float(os.getenv("UCB_EXPLORE_FACTOR", "1.4"))
    cluster_hash_buckets: int = int(os.getenv("CLUSTER_HASH_BUCKETS", "0"))
    service_version: str = os.getenv("ROUTER_SERVICE_VERSION", "0.1.0-alpha")
    api_key: str = os.getenv("ROUTER_ADMIN_API_KEY", "")
    enable_pii_scrub: bool = os.getenv("ROUTER_PII_SCRUB", "1") != "0"
    rps_limit: int = int(os.getenv("ROUTER_RPS_LIMIT", "50"))
    quality_eval_mode: str = os.getenv("ROUTER_QUALITY_EVAL", "placeholder")  # placeholder|off
    max_prompt_chars: int = int(os.getenv("ROUTER_MAX_PROMPT_CHARS", "6000"))
    rps_burst: int = int(os.getenv("ROUTER_RPS_BURST", os.getenv("ROUTER_RPS_LIMIT", "50")))
    enable_metrics: bool = os.getenv("ROUTER_ENABLE_METRICS", "1") != "0"
    max_concurrent: int = int(os.getenv("ROUTER_MAX_CONCURRENT", "200"))
    persist_interval_seconds: int = int(os.getenv("ROUTER_PERSIST_INTERVAL_SEC", "10"))
    enable_latency_histogram: bool = os.getenv("ROUTER_ENABLE_LAT_HIST", "1") != "0"
    enable_tracing: bool = os.getenv("ROUTER_ENABLE_TRACING", "0") == "1"
    otlp_endpoint: str = os.getenv("ROUTER_OTLP_ENDPOINT", "http://localhost:4317")
    state_backend: str = os.getenv("ROUTER_STATE_BACKEND", "memory").lower()  # memory|redis
    redis_url: str = os.getenv("ROUTER_REDIS_URL", "redis://localhost:6379/0")

    def __post_init__(self):
        if not self.api_key:
            raise ValueError("ROUTER_ADMIN_API_KEY environment variable must be set")

    def get_tenant_sampling_config(self) -> dict:
        """Get tenant sampling configuration from environment variables."""
        import json
        import logging

        logger = logging.getLogger(__name__)

        # Try to load from environment variable first
        config_json = os.getenv("ROUTER_TENANT_SAMPLING_CONFIG", "")
        if config_json:
            try:
                return json.loads(config_json)
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON in ROUTER_TENANT_SAMPLING_CONFIG: %s", e)
                return {}

        # Fallback to individual tenant environment variables
        tenant_config = {}
        tenant_vars = [var for var in os.environ.keys() if var.startswith("ROUTER_TENANT_") and var.endswith("_SAMPLING")]

        for var in tenant_vars:
            tenant_id = var.replace("ROUTER_TENANT_", "").replace("_SAMPLING", "").lower()
            try:
                policy_data = json.loads(os.environ[var])
                tenant_config[tenant_id] = policy_data
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Invalid sampling config for tenant %s: %s", tenant_id, e)
                continue

        return {"tenant_sampling_policies": tenant_config} if tenant_config else {}


settings = Settings()
