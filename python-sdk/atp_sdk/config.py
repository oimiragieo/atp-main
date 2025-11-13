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

"""
ATP SDK Configuration

Configuration management for the ATP SDK.
"""

import os
from dataclasses import dataclass, field
from typing import Any

from .exceptions import ConfigurationError


@dataclass
class ATPConfig:
    """Configuration for the ATP SDK."""

    # API Configuration
    api_key: str | None = None
    base_url: str = "https://api.atp.company.com"
    version: str = "1.0.0"

    # Authentication
    tenant_id: str | None = None
    project_id: str | None = None

    # Request Configuration
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0

    # Streaming Configuration
    stream_timeout: float = 60.0
    stream_buffer_size: int = 8192

    # Logging Configuration
    log_level: str = "INFO"
    log_requests: bool = False
    log_responses: bool = False

    # Cache Configuration
    enable_cache: bool = True
    cache_ttl: int = 300  # 5 minutes

    # Default Model Preferences
    default_model: str | None = None
    quality_preference: str = "balanced"  # speed, balanced, quality
    cost_limit: float | None = None

    # Provider Preferences
    preferred_providers: list = field(default_factory=list)
    excluded_providers: list = field(default_factory=list)

    # Additional Headers
    custom_headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """Post-initialization validation and environment variable loading."""
        self._load_from_environment()
        self._validate_config()

    def _load_from_environment(self):
        """Load configuration from environment variables."""
        # API Configuration
        if not self.api_key:
            self.api_key = os.getenv("ATP_API_KEY")

        if os.getenv("ATP_BASE_URL"):
            self.base_url = os.getenv("ATP_BASE_URL")

        # Authentication
        if not self.tenant_id:
            self.tenant_id = os.getenv("ATP_TENANT_ID")

        if not self.project_id:
            self.project_id = os.getenv("ATP_PROJECT_ID")

        # Request Configuration
        if os.getenv("ATP_TIMEOUT"):
            try:
                self.timeout = float(os.getenv("ATP_TIMEOUT"))
            except ValueError:
                pass

        if os.getenv("ATP_MAX_RETRIES"):
            try:
                self.max_retries = int(os.getenv("ATP_MAX_RETRIES"))
            except ValueError:
                pass

        # Logging Configuration
        if os.getenv("ATP_LOG_LEVEL"):
            self.log_level = os.getenv("ATP_LOG_LEVEL")

        if os.getenv("ATP_LOG_REQUESTS"):
            self.log_requests = os.getenv("ATP_LOG_REQUESTS").lower() in ("true", "1", "yes")

        if os.getenv("ATP_LOG_RESPONSES"):
            self.log_responses = os.getenv("ATP_LOG_RESPONSES").lower() in ("true", "1", "yes")

        # Default Preferences
        if os.getenv("ATP_DEFAULT_MODEL"):
            self.default_model = os.getenv("ATP_DEFAULT_MODEL")

        if os.getenv("ATP_QUALITY_PREFERENCE"):
            self.quality_preference = os.getenv("ATP_QUALITY_PREFERENCE")

        if os.getenv("ATP_COST_LIMIT"):
            try:
                self.cost_limit = float(os.getenv("ATP_COST_LIMIT"))
            except ValueError:
                pass

    def _validate_config(self):
        """Validate configuration values."""
        if not self.api_key:
            raise ConfigurationError(
                "API key is required. Set ATP_API_KEY environment variable or pass api_key parameter."
            )

        if not self.base_url:
            raise ConfigurationError("Base URL is required.")

        if self.timeout <= 0:
            raise ConfigurationError("Timeout must be positive.")

        if self.max_retries < 0:
            raise ConfigurationError("Max retries must be non-negative.")

        if self.quality_preference not in ["speed", "balanced", "quality"]:
            raise ConfigurationError("Quality preference must be one of: speed, balanced, quality")

        if self.cost_limit is not None and self.cost_limit <= 0:
            raise ConfigurationError("Cost limit must be positive.")

    @classmethod
    def from_file(cls, config_file: str) -> "ATPConfig":
        """Load configuration from a file."""
        import json

        import yaml

        try:
            with open(config_file) as f:
                if config_file.endswith(".json"):
                    config_data = json.load(f)
                elif config_file.endswith((".yml", ".yaml")):
                    config_data = yaml.safe_load(f)
                else:
                    raise ConfigurationError(f"Unsupported config file format: {config_file}")

            return cls(**config_data)

        except FileNotFoundError:
            raise ConfigurationError(f"Configuration file not found: {config_file}")
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            raise ConfigurationError(f"Invalid configuration file format: {e}")

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "api_key": "***" if self.api_key else None,  # Mask API key
            "base_url": self.base_url,
            "version": self.version,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "stream_timeout": self.stream_timeout,
            "stream_buffer_size": self.stream_buffer_size,
            "log_level": self.log_level,
            "log_requests": self.log_requests,
            "log_responses": self.log_responses,
            "enable_cache": self.enable_cache,
            "cache_ttl": self.cache_ttl,
            "default_model": self.default_model,
            "quality_preference": self.quality_preference,
            "cost_limit": self.cost_limit,
            "preferred_providers": self.preferred_providers,
            "excluded_providers": self.excluded_providers,
            "custom_headers": self.custom_headers,
        }

    def update(self, **kwargs):
        """Update configuration with new values."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                raise ConfigurationError(f"Unknown configuration parameter: {key}")

        self._validate_config()


# Global configuration instance
_global_config: ATPConfig | None = None


def get_global_config() -> ATPConfig:
    """Get the global configuration instance."""
    global _global_config
    if _global_config is None:
        _global_config = ATPConfig()
    return _global_config


def set_global_config(config: ATPConfig):
    """Set the global configuration instance."""
    global _global_config
    _global_config = config


def configure(**kwargs):
    """Configure the global ATP SDK settings."""
    config = get_global_config()
    config.update(**kwargs)
