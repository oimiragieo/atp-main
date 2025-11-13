"""Tests for GAP-340: SLM observation hook & anonymization."""

import json
import os
import tempfile
from datetime import date
from unittest.mock import patch

from metrics.registry import REGISTRY

from router_service.observation_schema import validate_observation
from router_service.service import _record_observation


class TestSLMObservationHook:
    """Test SLM observation hook functionality."""

    def test_slm_observation_includes_task_type(self):
        """Test that SLM observations include task_type field."""
        obs = {
            "ts": 1234567890.0,
            "prompt_hash": "abc123",
            "cluster_hint": "test_cluster",
            "task_type": "test_cluster",  # GAP-340: Task type for SLM training
            "model_plan": ["gpt-4"],
            "primary_model": "gpt-4",
            "latency_s": 1.5,
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": 0.01,
            "phase": "active",
            "schema_version": 2,
        }
        assert validate_observation(obs)
        assert obs["task_type"] == "test_cluster"

    def test_slm_observation_redaction_integration(self):
        """Test that SLM observations are properly redacted."""

        obs_with_pii = {
            "ts": 1735689600.0,  # 2025-01-01 timestamp
            "prompt_hash": "abc123",
            "cluster_hint": "test_cluster",
            "task_type": "test_cluster",
            "model_plan": ["gpt-4"],
            "primary_model": "gpt-4",
            "latency_s": 1.5,
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": 0.01,
            "phase": "active",
            "email": "test@example.com",
            "schema_version": 2,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("router_service.service._DATA_DIR", temp_dir):
                _record_observation(obs_with_pii)

                today = date.today().isoformat()
                obs_file = os.path.join(temp_dir, f"slm_observations-{today}.jsonl")
                with open(obs_file) as f:
                    persisted_obs = json.loads(f.read().strip())

                assert persisted_obs["email"] == "[redacted-email]"
                assert persisted_obs["task_type"] == "test_cluster"

    def test_slm_observation_metrics_increment(self):
        """Test that SLM observation metrics are incremented."""
        obs = {
            "ts": 1234567890.0,
            "prompt_hash": "abc123",
            "cluster_hint": "test_cluster",
            "task_type": "test_cluster",
            "model_plan": ["gpt-4"],
            "primary_model": "gpt-4",
            "latency_s": 1.5,
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": 0.01,
            "phase": "active",
            "schema_version": 2,
        }

        initial_count = REGISTRY.counter("atp_router_slm_observations_total")._value

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("router_service.service._DATA_DIR", temp_dir):
                _record_observation(obs)

        final_count = REGISTRY.counter("atp_router_slm_observations_total")._value
        assert final_count == initial_count + 1

    def test_slm_observation_with_null_task_type(self):
        """Test SLM observation with null task_type."""
        obs = {
            "ts": 1234567890.0,
            "prompt_hash": "abc123",
            "cluster_hint": None,
            "task_type": None,
            "model_plan": ["gpt-4"],
            "primary_model": "gpt-4",
            "latency_s": 1.5,
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": 0.01,
            "phase": "active",
            "schema_version": 2,
        }
        assert validate_observation(obs)
        assert obs["task_type"] is None
