"""Tests for GAP-209: Shadow evaluation enhancements (quality & latency sampling)."""

import os
from unittest.mock import patch

from router_service.observation_schema import validate_observation
from router_service.service import _load_shadow_config


class TestShadowEvaluationConfig:
    """Test shadow evaluation configuration loading."""

    def test_default_config(self):
        """Test default shadow evaluation configuration."""
        enabled, sample_rate, strategy = _load_shadow_config()
        assert enabled is True
        assert sample_rate == 1.0
        assert strategy == "random"

    @patch.dict(os.environ, {"ENABLE_SHADOW_EVALUATION": "0"})
    def test_disabled_config(self):
        """Test disabled shadow evaluation."""
        enabled, sample_rate, strategy = _load_shadow_config()
        assert enabled is False

    @patch.dict(os.environ, {"SHADOW_SAMPLE_RATE": "0.5"})
    def test_sample_rate_config(self):
        """Test custom sample rate."""
        enabled, sample_rate, strategy = _load_shadow_config()
        assert sample_rate == 0.5

    @patch.dict(os.environ, {"SHADOW_SAMPLING_STRATEGY": "quality_threshold"})
    def test_strategy_config(self):
        """Test custom sampling strategy."""
        enabled, sample_rate, strategy = _load_shadow_config()
        assert strategy == "quality_threshold"

    @patch.dict(os.environ, {"SHADOW_SAMPLE_RATE": "-1"})
    def test_invalid_sample_rate_clamped(self):
        """Test invalid sample rate is clamped."""
        enabled, sample_rate, strategy = _load_shadow_config()
        assert sample_rate == 0.0

    @patch.dict(os.environ, {"SHADOW_SAMPLE_RATE": "2"})
    def test_sample_rate_clamped_high(self):
        """Test sample rate clamped to maximum."""
        enabled, sample_rate, strategy = _load_shadow_config()
        assert sample_rate == 1.0

    @patch.dict(os.environ, {"SHADOW_SAMPLING_STRATEGY": "invalid"})
    def test_invalid_strategy_defaults(self):
        """Test invalid strategy defaults to random."""
        enabled, sample_rate, strategy = _load_shadow_config()
        assert strategy == "random"


class TestShadowObservationSchema:
    """Test shadow evaluation observation schema validation."""

    def test_valid_shadow_observation(self):
        """Test valid shadow evaluation observation."""
        obs = {
            "ts": 1234567890.0,
            "prompt_hash": "abc123",
            "cluster_hint": "test_cluster",
            "model_plan": ["primary-model"],
            "primary_model": "primary-model",
            "latency_s": 1.0,
            "tokens_in": 10,
            "tokens_out": 20,
            "cost_usd": 0.1,
            "quality_score": 0.8,
            "phase": "active",
            "schema_version": 2,
            "shadow_of": "primary-model",
            "shadow_model": "shadow-model",
            "shadow_quality": 0.75,
            "shadow_latency_s": 1.2,
            "shadow_cost_usd": 0.08,
            "mode": "sync_seed",
        }
        assert validate_observation(obs)

    def test_shadow_observation_missing_required_fields(self):
        """Test shadow observation with missing required fields."""
        obs = {
            "ts": 1234567890.0,
            "prompt_hash": "abc123",
            "cluster_hint": "test_cluster",
            "model_plan": ["primary-model"],
            "primary_model": "primary-model",
            "latency_s": 1.0,
            "tokens_in": 10,
            "tokens_out": 20,
            "cost_usd": 0.1,
            "quality_score": 0.8,
            "phase": "active",
            "schema_version": 2,
            # Missing shadow fields
        }
        assert validate_observation(obs)  # Should still validate as shadow fields are optional

    def test_shadow_observation_with_null_fields(self):
        """Test shadow observation with null shadow fields."""
        obs = {
            "ts": 1234567890.0,
            "prompt_hash": "abc123",
            "cluster_hint": "test_cluster",
            "model_plan": ["primary-model"],
            "primary_model": "primary-model",
            "latency_s": 1.0,
            "tokens_in": 10,
            "tokens_out": 20,
            "cost_usd": 0.1,
            "quality_score": 0.8,
            "phase": "active",
            "schema_version": 2,
            "shadow_of": None,
            "shadow_model": None,
            "shadow_quality": 0.75,
            "shadow_latency_s": 1.2,
            "shadow_cost_usd": 0.08,
        }
        assert validate_observation(obs)


class TestSchemaVersionValidation:
    """Test schema version validation for GAP-219."""

    def test_schema_version_mismatch_rejection(self):
        """Test that observations with wrong schema version are rejected."""
        obs = {
            "ts": 1234567890.0,
            "prompt_hash": "abc123",
            "cluster_hint": "test_cluster",
            "model_plan": ["primary-model"],
            "primary_model": "primary-model",
            "latency_s": 1.0,
            "tokens_in": 10,
            "tokens_out": 20,
            "cost_usd": 0.1,
            "phase": "active",
            "schema_version": 1,  # Wrong version
        }
        assert not validate_observation(obs)

    def test_schema_version_missing_rejection(self):
        """Test that observations without schema version are rejected."""
        obs = {
            "ts": 1234567890.0,
            "prompt_hash": "abc123",
            "cluster_hint": "test_cluster",
            "model_plan": ["primary-model"],
            "primary_model": "primary-model",
            "latency_s": 1.0,
            "tokens_in": 10,
            "tokens_out": 20,
            "cost_usd": 0.1,
            "phase": "active",
            # Missing schema_version
        }
        assert not validate_observation(obs)


class TestShadowSamplingStrategy:
    """Test shadow evaluation sampling strategies."""

    @patch("router_service.service.SHADOW_ENABLED", True)
    @patch("router_service.service.SHADOW_SAMPLE_RATE", 1.0)
    @patch("router_service.service.SHADOW_SAMPLING_STRATEGY", "random")
    @patch("random.random")
    def test_random_sampling_enabled(self, mock_random):
        """Test random sampling when enabled."""
        from router_service.service import should_sample_shadow

        mock_random.return_value = 0.5  # Below sample rate
        assert should_sample_shadow(0.8, 500)

    @patch("router_service.service.SHADOW_ENABLED", True)
    @patch("router_service.service.SHADOW_SAMPLE_RATE", 0.5)
    @patch("router_service.service.SHADOW_SAMPLING_STRATEGY", "random")
    @patch("random.random")
    def test_random_sampling_disabled_by_rate(self, mock_random):
        """Test random sampling disabled by sample rate."""
        from router_service.service import should_sample_shadow

        mock_random.return_value = 0.7  # Above sample rate
        assert not should_sample_shadow(0.8, 500)

    @patch("router_service.service.SHADOW_ENABLED", False)
    def test_sampling_disabled(self):
        """Test sampling disabled when SHADOW_ENABLED is False."""
        from router_service.service import should_sample_shadow

        assert not should_sample_shadow(0.8, 500)

    @patch("router_service.service.SHADOW_ENABLED", True)
    @patch("router_service.service.SHADOW_SAMPLE_RATE", 1.0)
    @patch("router_service.service.SHADOW_SAMPLING_STRATEGY", "quality_threshold")
    @patch.dict(os.environ, {"SHADOW_QUALITY_THRESHOLD": "0.8"})
    @patch("random.random")
    def test_quality_threshold_sampling(self, mock_random):
        """Test quality threshold sampling."""
        from router_service.service import should_sample_shadow

        mock_random.return_value = 0.3  # Below sample rate

        # Quality below threshold should sample
        assert should_sample_shadow(0.7, 500)

        # Quality above threshold should not sample
        assert not should_sample_shadow(0.9, 500)

    @patch("router_service.service.SHADOW_ENABLED", True)
    @patch("router_service.service.SHADOW_SAMPLE_RATE", 1.0)
    @patch("router_service.service.SHADOW_SAMPLING_STRATEGY", "latency_threshold")
    @patch.dict(os.environ, {"SHADOW_LATENCY_THRESHOLD_MS": "1000"})
    @patch("random.random")
    def test_latency_threshold_sampling(self, mock_random):
        """Test latency threshold sampling."""
        from router_service.service import should_sample_shadow

        mock_random.return_value = 0.3  # Below sample rate

        # Latency above threshold should sample
        assert should_sample_shadow(0.8, 1500)

        # Latency below threshold should not sample
        assert not should_sample_shadow(0.8, 500)


class TestShadowMetrics:
    """Test shadow evaluation metrics."""

    def test_shadow_metrics_initialization(self):
        """Test that shadow metrics are properly initialized."""
        from router_service.service import _ctr_shadow_evals, _g_shadow_quality_gap

        # Metrics should be initialized
        assert _ctr_shadow_evals is not None
        assert _g_shadow_quality_gap is not None

        # Should be able to increment counter
        _ctr_shadow_evals.inc()

        # Should be able to set gauge
        _g_shadow_quality_gap.set(0.1)
