#!/usr/bin/env python3
"""
Environment Configuration Validator for ATP System

This script validates that all required environment variables are set
and have valid values for production deployment.
"""

import json
import os
import sys
from pathlib import Path


class EnvValidator:
    """Validates environment configuration for ATP system."""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.required_vars = {
            # Critical security variables
            "ROUTER_ADMIN_API_KEY": self._validate_admin_key,
            "AUDIT_SECRET": self._validate_secret,
            # Data paths
            "ROUTER_DATA_DIR": self._validate_path,
            # Tracing configuration
            "ROUTER_ENABLE_TRACING": self._validate_boolean,
            "ROUTER_TEST_TRACING_MODE": self._validate_tracing_mode,
            # Specialist selection
            "SPECIALIST_MAX_COST_PER_1K": self._validate_float,
            "SPECIALIST_MIN_QUALITY": self._validate_quality_score,
            "SPECIALIST_MAX_LATENCY_MS": self._validate_positive_int,
        }

        self.optional_vars = {
            # Optional but recommended
            "ROUTER_ADMIN_KEYS": self._validate_admin_keys_json,
            "ROUTER_SAMPLING_QOS": self._validate_sampling_qos,
            "ROUTER_REDIS_URL": self._validate_redis_url,
            "ROUTER_DISABLE_OTLP_EXPORT": self._validate_boolean,
            "SHADOW_MIN_SAMPLE_WINDOW": self._validate_positive_int,
            "SHADOW_WIN_RATE_THRESHOLD": self._validate_percentage,
            "SHADOW_COST_SAVINGS_THRESHOLD": self._validate_percentage,
            "ENABLE_SHADOW_EVALUATION": self._validate_boolean,
            "ENABLE_QOS_PRIORITY": self._validate_boolean,
            "ROUTER_ENABLE_METRICS": self._validate_boolean,
            "ROUTER_MAX_PROMPT_CHARS": self._validate_positive_int,
        }

    def _validate_admin_key(self, value: str) -> bool:
        """Validate admin API key format."""
        if not value or value == "your-admin-api-key-here":
            self.errors.append("ROUTER_ADMIN_API_KEY must be set to a secure value")
            return False
        if len(value) < 16:
            self.warnings.append("ROUTER_ADMIN_API_KEY should be at least 16 characters long")
        return True

    def _validate_secret(self, value: str) -> bool:
        """Validate secret format."""
        if not value or value == "your-audit-secret-here":
            self.errors.append("AUDIT_SECRET must be set to a secure value")
            return False
        if len(value) < 16:
            self.warnings.append("AUDIT_SECRET should be at least 16 characters long")
        return True

    def _validate_path(self, value: str) -> bool:
        """Validate path exists."""
        path = Path(value)
        if not path.exists():
            self.warnings.append(f"ROUTER_DATA_DIR path does not exist: {value}")
        return True

    def _validate_boolean(self, value: str) -> bool:
        """Validate boolean values (1, 0, true, false)."""
        valid_values = ["0", "1", "true", "false", "yes", "no"]
        if value.lower() not in valid_values:
            self.errors.append(f"Invalid boolean value: {value}. Must be one of {valid_values}")
            return False
        return True

    def _validate_tracing_mode(self, value: str) -> bool:
        """Validate tracing mode."""
        valid_modes = ["dummy", "otel", ""]
        if value not in valid_modes:
            self.errors.append(f"Invalid ROUTER_TEST_TRACING_MODE: {value}. Must be one of {valid_modes}")
            return False
        return True

    def _validate_float(self, value: str) -> bool:
        """Validate float value."""
        try:
            float(value)
            return True
        except ValueError:
            self.errors.append(f"Invalid float value: {value}")
            return False

    def _validate_quality_score(self, value: str) -> bool:
        """Validate quality score (0.0 to 1.0)."""
        try:
            score = float(value)
            if not 0.0 <= score <= 1.0:
                self.errors.append(f"Quality score must be between 0.0 and 1.0: {value}")
                return False
            return True
        except ValueError:
            self.errors.append(f"Invalid quality score: {value}")
            return False

    def _validate_positive_int(self, value: str) -> bool:
        """Validate positive integer."""
        try:
            num = int(value)
            if num <= 0:
                self.errors.append(f"Must be positive integer: {value}")
                return False
            return True
        except ValueError:
            self.errors.append(f"Invalid integer: {value}")
            return False

    def _validate_admin_keys_json(self, value: str) -> bool:
        """Validate admin keys JSON format."""
        try:
            keys = json.loads(value)
            if not isinstance(keys, list):
                self.errors.append("ROUTER_ADMIN_KEYS must be a JSON array")
                return False
            if not all(isinstance(k, str) for k in keys):
                self.errors.append("All admin keys must be strings")
                return False
            return True
        except json.JSONDecodeError:
            self.errors.append(f"Invalid JSON in ROUTER_ADMIN_KEYS: {value}")
            return False

    def _validate_sampling_qos(self, value: str) -> bool:
        """Validate QoS sampling format (tier:ratio,tier:ratio)."""
        if not value:
            return True  # Empty is valid

        parts = value.split(",")
        for part in parts:
            if ":" not in part:
                self.errors.append(f"Invalid QoS sampling format: {value}. Use tier:ratio,tier:ratio")
                return False
            tier, ratio_str = part.split(":", 1)
            try:
                ratio = float(ratio_str)
                if not 0.0 <= ratio <= 1.0:
                    self.errors.append(f"QoS ratio must be between 0.0 and 1.0: {ratio}")
                    return False
            except ValueError:
                self.errors.append(f"Invalid QoS ratio: {ratio_str}")
                return False
        return True

    def _validate_redis_url(self, value: str) -> bool:
        """Validate Redis URL format."""
        if not value.startswith(("redis://", "rediss://", "unix://")):
            self.warnings.append(f"Redis URL should start with redis://, rediss://, or unix://: {value}")
        return True

    def _validate_percentage(self, value: str) -> bool:
        """Validate percentage (0.0 to 1.0)."""
        return self._validate_quality_score(value)  # Same validation

    def validate(self) -> tuple[bool, list[str], list[str]]:
        """Validate all environment variables."""
        # Check required variables
        for var_name, validator in self.required_vars.items():
            value = os.getenv(var_name)
            if value is None:
                self.errors.append(f"Required environment variable not set: {var_name}")
            else:
                validator(value)

        # Check optional variables
        for var_name, validator in self.optional_vars.items():
            value = os.getenv(var_name)
            if value is not None:
                validator(value)

        # Check for conflicting settings
        self._check_conflicts()

        return len(self.errors) == 0, self.errors, self.warnings

    def _check_conflicts(self):
        """Check for conflicting configuration settings."""
        # Check tracing conflicts
        enable_tracing = os.getenv("ROUTER_ENABLE_TRACING", "0")
        test_mode = os.getenv("ROUTER_TEST_TRACING_MODE", "")

        if enable_tracing in ("1", "true", "yes") and test_mode == "dummy":
            self.warnings.append("ROUTER_ENABLE_TRACING=1 conflicts with ROUTER_TEST_TRACING_MODE=dummy")

        # Check admin key conflicts
        single_key = os.getenv("ROUTER_ADMIN_API_KEY")
        multi_keys = os.getenv("ROUTER_ADMIN_KEYS")

        if single_key and multi_keys:
            self.warnings.append(
                "Both ROUTER_ADMIN_API_KEY and ROUTER_ADMIN_KEYS are set. ROUTER_ADMIN_KEYS takes precedence"
            )


def main():
    """Main validation function."""
    print("Validating ATP Environment Configuration...")
    print("=" * 60)

    validator = EnvValidator()
    is_valid, errors, warnings = validator.validate()

    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"   - {warning}")
        print()

    if errors:
        print("Errors:")
        for error in errors:
            print(f"   - {error}")
        print()

    if is_valid:
        print("Environment configuration is valid!")
        return 0
    else:
        print("Environment configuration has errors. Please fix them before deployment.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
