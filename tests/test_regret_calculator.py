"""Tests for GAP-214: Request-level cost/regret savings KPI."""

from router_service.choose_model import Candidate, choose
from router_service.regret_calculator import RegretAnalysis, RegretCalculator, get_regret_calculator


class TestRegretCalculator:
    """Test regret calculation functionality."""

    def setup_method(self):
        """Set up test instance."""
        self.calculator = RegretCalculator()

    def teardown_method(self):
        """Clean up global instance."""
        import router_service.regret_calculator as rc

        rc._regret_calculator = None

    def test_calculate_regret_perfect_choice(self):
        """Test regret calculation when optimal model is chosen."""
        candidates = [
            Candidate("cheap-model", 0.4, 0.70, 900, "us-west"),
            Candidate("mid-model", 1.0, 0.80, 1100, "eu-west"),
        ]
        registry = {
            "cheap-model": {"status": "active", "safety_grade": "A"},
            "mid-model": {"status": "active", "safety_grade": "A"},
        }

        # Choose mid-model for balanced quality (cheap-model doesn't meet quality threshold)
        chosen = candidates[1]  # mid-model
        analysis = self.calculator.calculate_regret(
            chosen=chosen,
            all_candidates=candidates,
            quality="balanced",
            latency_slo_ms=1200,
            registry=registry,
            total_tokens=1000,
        )

        assert analysis.chosen_model == "mid-model"
        assert analysis.optimal_model == "mid-model"  # Only viable option
        assert analysis.regret_amount == 0.0
        assert analysis.regret_percentage == 0.0
        assert analysis.chosen_cost == 1.0  # 1.0 * 1000 / 1000
        assert analysis.optimal_cost == 1.0

    def test_calculate_regret_suboptimal_choice(self):
        """Test regret calculation when suboptimal model is chosen."""
        candidates = [
            Candidate("cheap-model", 0.4, 0.70, 900, "us-west"),
            Candidate("mid-model", 1.0, 0.80, 1100, "eu-west"),
            Candidate("premium-model", 2.0, 0.90, 1400, "asia-east"),
        ]
        registry = {
            "cheap-model": {"status": "active", "safety_grade": "A"},
            "mid-model": {"status": "active", "safety_grade": "A"},
            "premium-model": {"status": "active", "safety_grade": "A"},
        }

        # Choose premium-model when mid-model is optimal for balanced quality
        chosen = candidates[2]  # premium-model
        analysis = self.calculator.calculate_regret(
            chosen=chosen,
            all_candidates=candidates,
            quality="balanced",
            latency_slo_ms=1500,  # All models meet latency
            registry=registry,
            total_tokens=1000,
        )

        assert analysis.chosen_model == "premium-model"
        assert analysis.optimal_model == "mid-model"  # Cheapest viable model
        assert analysis.regret_amount == 1.0  # 2.0 - 1.0
        assert analysis.regret_percentage == 100.0  # (1.0 / 1.0) * 100
        assert analysis.chosen_cost == 2.0
        assert analysis.optimal_cost == 1.0

    def test_calculate_regret_with_constraints(self):
        """Test regret calculation respects quality and latency constraints."""
        candidates = [
            Candidate("cheap-model", 0.4, 0.60, 900, "us-west"),  # Below quality threshold
            Candidate("mid-model", 1.0, 0.80, 1100, "eu-west"),  # Below quality threshold
            Candidate("premium-model", 2.0, 0.90, 1100, "asia-east"),  # Meets requirements
        ]
        registry = {
            "cheap-model": {"status": "active", "safety_grade": "A"},
            "mid-model": {"status": "active", "safety_grade": "A"},
            "premium-model": {"status": "active", "safety_grade": "A"},
        }

        # Choose premium-model for high quality
        chosen = candidates[2]  # premium-model
        analysis = self.calculator.calculate_regret(
            chosen=chosen,
            all_candidates=candidates,
            quality="high",  # Requires 0.85 quality
            latency_slo_ms=1200,  # All models meet latency
            registry=registry,
            total_tokens=1000,
        )

        # Only premium-model meets quality requirement
        assert analysis.chosen_model == "premium-model"
        assert analysis.optimal_model == "premium-model"  # Only viable option
        assert analysis.regret_amount == 0.0
        assert analysis.regret_percentage == 0.0

    def test_calculate_regret_safety_filtering(self):
        """Test regret calculation filters by safety grade."""
        candidates = [
            Candidate("cheap-model", 0.4, 0.70, 900, "us-west"),  # Below quality threshold
            Candidate("unsafe-model", 0.3, 0.75, 950, "us-east"),  # Cheaper but unsafe
        ]
        registry = {
            "cheap-model": {"status": "active", "safety_grade": "A"},
            "unsafe-model": {"status": "active", "safety_grade": "C"},  # Below requirement
        }

        chosen = candidates[0]  # cheap-model
        analysis = self.calculator.calculate_regret(
            chosen=chosen,
            all_candidates=candidates,
            quality="balanced",
            latency_slo_ms=1200,
            registry=registry,
            total_tokens=1000,
        )

        # Unsafe model should be filtered out, cheap-model doesn't meet quality, so no viable candidates
        assert analysis.chosen_model == "cheap-model"
        assert analysis.optimal_model == "none"
        assert analysis.viable_candidates == 0

    def test_calculate_regret_no_viable_candidates(self):
        """Test regret calculation when no candidates meet requirements."""
        candidates = [
            Candidate("slow-model", 0.4, 0.80, 2000, "us-west"),  # Too slow
        ]
        registry = {
            "slow-model": {"status": "active", "safety_grade": "A"},
        }

        chosen = candidates[0]
        analysis = self.calculator.calculate_regret(
            chosen=chosen,
            all_candidates=candidates,
            quality="balanced",
            latency_slo_ms=1000,  # Model is too slow
            registry=registry,
            total_tokens=1000,
        )

        assert analysis.chosen_model == "slow-model"
        assert analysis.optimal_model == "none"
        assert analysis.regret_amount == 0.0
        assert analysis.regret_percentage == 0.0
        assert analysis.viable_candidates == 0

    def test_get_regret_summary(self):
        """Test regret summary statistics."""
        analyses = [
            RegretAnalysis("model1", 1.0, "model1", 1.0, 0.0, 0.0, "balanced", 1000, 1000, 2),
            RegretAnalysis("model2", 1.5, "model1", 1.0, 0.5, 50.0, "balanced", 1000, 1000, 2),
            RegretAnalysis("model3", 2.0, "model1", 1.0, 1.0, 100.0, "balanced", 1000, 1000, 2),
        ]

        summary = self.calculator.get_regret_summary(analyses)

        assert summary["total_analyses"] == 3
        assert summary["avg_regret_pct"] == 50.0  # (0 + 50 + 100) / 3
        assert summary["max_regret_pct"] == 100.0
        assert summary["regret_above_1pct_count"] == 2  # 50% and 100%
        assert summary["regret_above_5pct_count"] == 2  # 50% and 100%
        assert summary["perfect_decisions_pct"] == 33.33333333333333  # 1 out of 3

    def test_get_regret_summary_empty(self):
        """Test regret summary with empty list."""
        summary = self.calculator.get_regret_summary([])

        assert summary["total_analyses"] == 0
        assert summary["avg_regret_pct"] == 0.0
        assert summary["max_regret_pct"] == 0.0


class TestRegretIntegration:
    """Test regret calculation integration with routing."""

    def setup_method(self):
        """Set up test registry."""
        self.registry = {
            "cheap-model": {"status": "active", "safety_grade": "A"},
            "exp-model": {"status": "active", "safety_grade": "A"},
            "mid-model": {"status": "active", "safety_grade": "A"},
            "premium-model": {"status": "active", "safety_grade": "A"},
        }

    def test_routing_with_regret_calculation(self):
        """Test that routing includes regret calculation."""
        plan, regret, energy = choose(
            quality="balanced",
            latency_slo_ms=1200,
            registry=self.registry,
            carbon_aware=False,  # Disable carbon for predictable results
            total_tokens=1000,
        )

        assert len(plan) > 0
        assert regret is not None
        assert isinstance(regret, RegretAnalysis)
        assert regret.total_tokens == 1000
        assert regret.quality_requirement == "balanced"
        assert regret.latency_requirement_ms == 1200

        # Check energy attribution is included
        assert energy is not None
        assert "energy_kwh" in energy
        assert "co2e_grams" in energy
        assert energy["total_tokens"] == 1000

    def test_routing_regret_zero_for_optimal_choice(self):
        """Test that regret is zero when optimal model is chosen."""
        # Force selection of cheapest model by setting strict latency
        plan, regret, energy = choose(
            quality="fast",  # Lower quality requirement
            latency_slo_ms=950,  # Cheap model meets this
            registry=self.registry,
            carbon_aware=False,
            total_tokens=1000,
        )

        assert len(plan) > 0
        assert regret is not None
        # Should choose cheap-model as it's optimal and meets requirements
        if regret.chosen_model == "cheap-model":
            assert regret.regret_percentage == 0.0

        # Check energy attribution
        assert energy is not None
        assert energy["energy_kwh"] > 0
        assert energy["co2e_grams"] > 0

    def test_routing_regret_with_different_token_counts(self):
        """Test regret calculation scales with token count."""
        plan1, regret1, energy1 = choose(
            quality="balanced", latency_slo_ms=1200, registry=self.registry, carbon_aware=False, total_tokens=1000
        )

        plan2, regret2, energy2 = choose(
            quality="balanced", latency_slo_ms=1200, registry=self.registry, carbon_aware=False, total_tokens=2000
        )

        assert regret1 is not None
        assert regret2 is not None

        # Costs should scale with token count
        if regret1.chosen_cost > 0:
            assert abs((regret2.chosen_cost / regret1.chosen_cost) - 2.0) < 0.01

        # Energy should also scale with token count
        assert energy1["energy_kwh"] > 0
        assert energy2["energy_kwh"] > 0
        assert abs((energy2["energy_kwh"] / energy1["energy_kwh"]) - 2.0) < 0.01


class TestGlobalRegretCalculator:
    """Test global regret calculator instance."""

    def teardown_method(self):
        """Clean up global instance."""
        import router_service.regret_calculator as rc

        rc._regret_calculator = None

    def test_get_global_calculator(self):
        """Test getting global calculator instance."""
        calc1 = get_regret_calculator()
        calc2 = get_regret_calculator()

        # Should return same instance
        assert calc1 is calc2
        assert isinstance(calc1, RegretCalculator)
