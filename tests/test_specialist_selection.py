"""Tests for GAP-346: Specialist selection routing integration."""

from unittest.mock import patch

from router_service.specialist_selection import SpecialistSelectionService


class TestSpecialistSelectionService:
    """Test specialist model selection and fallback chains."""

    def setup_method(self):
        """Reset service before each test."""
        self.service = SpecialistSelectionService()

    def test_load_model_registry(self):
        """Test loading model registry."""
        registry = self.service._model_registry
        assert isinstance(registry, dict)
        assert len(registry) > 0

        # Should have expected models
        assert "cheap-model" in registry
        assert "premium-model" in registry

    def test_select_specialist_basic(self):
        """Test basic specialist selection."""
        result = self.service.select_specialist(
            task_description="Summarize this document",
            quality_requirement="balanced",
            max_cost_usd=0.05,
            latency_slo_ms=2000,
        )

        assert "primary_model" in result
        assert "fallback_chain" in result
        assert "cluster_id" in result
        assert "specialist_hit" in result
        assert isinstance(result["fallback_chain"], list)

    def test_select_specialist_with_capabilities(self):
        """Test selection with required capabilities."""
        result = self.service.select_specialist(task_description="Write Python code", required_capabilities=["code"])

        # Should select a model with code capability
        primary = result["primary_model"]
        if primary and primary in self.service._model_registry:
            capabilities = self.service._model_registry[primary].get("capabilities", [])
            assert "code" in capabilities

    def test_score_candidates(self):
        """Test candidate scoring logic."""
        candidates = [self.service._model_registry["cheap-model"], self.service._model_registry["premium-model"]]

        scored = self.service._score_candidates(candidates, "balanced", 0.05, 2000)

        assert isinstance(scored, list)
        if len(scored) > 1:
            # Should be sorted by score descending
            assert scored[0][1] >= scored[1][1]

    def test_build_fallback_chain(self):
        """Test fallback chain construction."""
        scored_candidates = [
            (self.service._model_registry["cheap-model"], 0.8),
            (self.service._model_registry["exp-model"], 0.6),
        ]

        primary, fallbacks = self.service._build_fallback_chain(scored_candidates)

        assert primary == "cheap-model"
        assert "exp-model" in fallbacks
        assert "premium-model" in fallbacks  # Should always include premium as final fallback

    def test_estimate_quality(self):
        """Test quality estimation for models."""
        cheap_model = self.service._model_registry["cheap-model"]
        premium_model = self.service._model_registry["premium-model"]

        cheap_quality = self.service._estimate_quality(cheap_model)
        premium_quality = self.service._estimate_quality(premium_model)

        assert isinstance(cheap_quality, float)
        assert isinstance(premium_quality, float)
        assert 0.0 <= cheap_quality <= 1.0
        assert 0.0 <= premium_quality <= 1.0

        # Premium should generally have higher quality
        assert premium_quality >= cheap_quality

    def test_get_cluster_candidates(self):
        """Test getting candidates for a cluster."""
        candidates = self.service._get_cluster_candidates("cluster_0", [])

        assert isinstance(candidates, list)
        for candidate in candidates:
            assert "model" in candidate
            assert "status" in candidate

    def test_get_cluster_candidates_with_capabilities(self):
        """Test filtering candidates by capabilities."""
        candidates = self.service._get_cluster_candidates("cluster_0", ["code"])

        for candidate in candidates:
            capabilities = candidate.get("capabilities", [])
            assert "code" in capabilities

    def test_select_specialist_strict_constraints(self):
        """Test selection with very strict constraints."""
        result = self.service.select_specialist(
            task_description="Simple task",
            max_cost_usd=0.001,  # Very low cost
            latency_slo_ms=500,  # Very low latency
        )

        # May not find any candidates meeting strict constraints
        assert "primary_model" in result

    def test_fallback_when_no_candidates(self):
        """Test fallback to premium when no candidates meet constraints."""
        # Mock empty candidates
        with patch.object(self.service, "_get_cluster_candidates", return_value=[]):
            result = self.service.select_specialist("test task")

            assert result["primary_model"] == "premium-model"
            assert result["fallback_chain"] == []

    def test_metric_update(self):
        """Test that specialist hit rate metric is updated."""
        result = self.service.select_specialist("test task")

        # Metric should have been updated
        assert "specialist_hit" in result
        assert isinstance(result["specialist_hit"], bool)

    def test_different_quality_requirements(self):
        """Test selection with different quality requirements."""
        for quality in ["fast", "balanced", "high"]:
            result = self.service.select_specialist("test task", quality_requirement=quality)
            assert "primary_model" in result
            assert result["primary_model"] is not None
