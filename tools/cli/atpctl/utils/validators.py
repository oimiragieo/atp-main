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

"""Validators for atpctl CLI"""

from typing import Any


def validate_provider_config(provider_data: dict[str, Any]) -> list[str]:
    """Validate provider configuration.

    Args:
        provider_data: Provider configuration data

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Validate required fields
    if not provider_data.get("name"):
        errors.append("Provider name is required")

    if not provider_data.get("type"):
        errors.append("Provider type is required")

    # Validate provider type
    valid_types = {"openai", "anthropic", "google", "ollama", "huggingface", "azure", "cohere"}
    provider_type = provider_data.get("type", "").lower()
    if provider_type and provider_type not in valid_types:
        errors.append(f"Invalid provider type: {provider_type}. Must be one of {valid_types}")

    # Validate configuration
    config = provider_data.get("config", {})
    if not isinstance(config, dict):
        errors.append("Provider config must be a dictionary")

    # Validate priority
    priority = provider_data.get("priority")
    if priority is not None and (not isinstance(priority, int) or priority < 0):
        errors.append("Priority must be a non-negative integer")

    return errors


def validate_policy_config(policy_data: dict[str, Any]) -> list[str]:
    """Validate policy configuration.

    Args:
        policy_data: Policy configuration data

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Validate required fields
    if not policy_data.get("name"):
        errors.append("Policy name is required")

    if not policy_data.get("type"):
        errors.append("Policy type is required")

    # Validate policy type
    valid_types = {"rate_limit", "cost_limit", "content_filter", "access_control", "routing"}
    policy_type = policy_data.get("type", "").lower()
    if policy_type and policy_type not in valid_types:
        errors.append(f"Invalid policy type: {policy_type}. Must be one of {valid_types}")

    # Validate rules
    rules = policy_data.get("rules", [])
    if not isinstance(rules, list):
        errors.append("Policy rules must be a list")

    return errors
