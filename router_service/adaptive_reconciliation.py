"""GAP-116: Adaptive reconciliation (future RL switching)

Implements adaptive switching between reconciliation strategies based on
performance metrics and contextual factors. Currently uses heuristic-based
switching as a POC until RL training (GAP-183) is complete.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from metrics.registry import REGISTRY

_CTR_STRATEGY_SWITCHES = REGISTRY.counter("agp_reconciliation_strategy_switches_total")


@dataclass
class ReconciliationPerformance:
    """Performance metrics for a reconciliation strategy."""

    strategy_name: str
    success_rate: float  # 0.0 to 1.0
    avg_latency_ms: float
    avg_cost_usd: float
    quality_score: float  # 0.0 to 1.0
    sample_count: int
    last_updated: float


@dataclass
class SwitchingContext:
    """Context information for strategy switching decisions."""

    request_complexity: float  # 0.0 to 1.0 (based on prompt length, etc.)
    time_pressure: bool  # True if low latency required
    cost_sensitivity: float  # 0.0 to 1.0 (higher = more cost sensitive)
    quality_requirement: float  # 0.0 to 1.0 (higher = better quality needed)
    persona_count: int
    convergence_history: list[bool]  # Recent convergence outcomes


class AdaptiveReconciliationSwitcher:
    """Adaptive switcher for reconciliation strategies.

    Currently implements heuristic-based switching as POC.
    Will be enhanced with RL-based switching once GAP-183 is complete.
    """

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.performance_history: dict[str, ReconciliationPerformance] = {}
        self.current_strategy = "first-win"  # Default fallback
        self.last_switch_time = 0.0
        self.min_switch_interval = 300.0  # 5 minutes between switches

    def should_switch_strategy(self, context: SwitchingContext) -> bool:
        """Determine if strategy switching is recommended.

        Args:
            context: Current switching context

        Returns:
            True if strategy switch is recommended
        """
        if not self.enabled:
            return False

        # Don't switch too frequently
        if time.time() - self.last_switch_time < self.min_switch_interval:
            return False

        # Simple heuristic-based switching logic
        return self._heuristic_switching_logic(context)

    def select_optimal_strategy(self, context: SwitchingContext) -> str:
        """Select the optimal reconciliation strategy for the given context.

        Args:
            context: Current switching context

        Returns:
            Name of the recommended strategy
        """
        if not self.enabled:
            return self.current_strategy

        # For now, use simple heuristic selection
        # This will be replaced with RL-based selection in GAP-183
        recommended = self._heuristic_strategy_selection(context)

        if recommended != self.current_strategy:
            self._record_strategy_switch(self.current_strategy, recommended, context)

        self.current_strategy = recommended
        return recommended

    def update_performance(
        self, strategy_name: str, success: bool, latency_ms: float, cost_usd: float, quality_score: float
    ) -> None:
        """Update performance metrics for a strategy.

        Args:
            strategy_name: Name of the strategy
            success: Whether reconciliation was successful
            latency_ms: Latency in milliseconds
            cost_usd: Cost in USD
            quality_score: Quality score (0.0 to 1.0)
        """
        if strategy_name not in self.performance_history:
            self.performance_history[strategy_name] = ReconciliationPerformance(
                strategy_name=strategy_name,
                success_rate=0.0,
                avg_latency_ms=0.0,
                avg_cost_usd=0.0,
                quality_score=0.0,
                sample_count=0,
                last_updated=time.time(),
            )

        perf = self.performance_history[strategy_name]

        # Update running averages
        alpha = 0.1  # Learning rate
        perf.sample_count += 1
        perf.success_rate = (1 - alpha) * perf.success_rate + alpha * (1.0 if success else 0.0)
        perf.avg_latency_ms = (1 - alpha) * perf.avg_latency_ms + alpha * latency_ms
        perf.avg_cost_usd = (1 - alpha) * perf.avg_cost_usd + alpha * cost_usd
        perf.quality_score = (1 - alpha) * perf.quality_score + alpha * quality_score
        perf.last_updated = time.time()

    def get_strategy_performance(self, strategy_name: str) -> ReconciliationPerformance | None:  # noqa: UP007
        """Get performance metrics for a strategy."""
        return self.performance_history.get(strategy_name)

    def _heuristic_switching_logic(self, context: SwitchingContext) -> bool:
        """Simple heuristic logic for determining if switching is needed."""
        # Switch if:
        # 1. Current strategy has poor performance (< 70% success rate)
        # 2. High time pressure and current strategy is slow
        # 3. High quality requirement and current strategy has poor quality

        current_perf = self.performance_history.get(self.current_strategy)
        if not current_perf or current_perf.sample_count < 5:
            return False  # Not enough data

        reasons_to_switch = []

        # Check success rate
        if current_perf.success_rate < 0.7:
            reasons_to_switch.append("low_success_rate")

        # Check latency for time-sensitive requests
        if context.time_pressure and current_perf.avg_latency_ms > 2000:
            reasons_to_switch.append("high_latency_time_pressure")

        # Check quality for quality-sensitive requests
        if context.quality_requirement > 0.8 and current_perf.quality_score < 0.7:
            reasons_to_switch.append("low_quality_high_requirement")

        return len(reasons_to_switch) > 0

    def _heuristic_strategy_selection(self, context: SwitchingContext) -> str:
        """Simple heuristic strategy selection."""
        # Priority-based selection
        if context.time_pressure:
            return "first-win"  # Fastest
        elif context.quality_requirement > 0.8:
            return "consensus"  # Best quality
        elif context.cost_sensitivity > 0.7:
            return "weighted-merge"  # Balanced cost/quality
        elif context.persona_count > 3:
            return "arbiter"  # Good for many personas
        else:
            return "first-win"  # Default

    def _record_strategy_switch(self, old_strategy: str, new_strategy: str, context: SwitchingContext) -> None:
        """Record a strategy switch event."""
        self.last_switch_time = time.time()
        _CTR_STRATEGY_SWITCHES.inc()

        # In production, this would log detailed switching context
        print(
            f"Strategy switch: {old_strategy} -> {new_strategy} "
            f"(time_pressure={context.time_pressure}, "
            f"quality_req={context.quality_requirement:.2f})"
        )


# Global adaptive switcher instance
_ADAPTIVE_SWITCHER = AdaptiveReconciliationSwitcher()


def get_adaptive_reconciliation_strategy(context: SwitchingContext) -> str:
    """Get the recommended reconciliation strategy for the given context.

    This is the main entry point for adaptive reconciliation switching.
    """
    return _ADAPTIVE_SWITCHER.select_optimal_strategy(context)


def update_reconciliation_performance(
    strategy_name: str, success: bool, latency_ms: float, cost_usd: float, quality_score: float
) -> None:
    """Update performance metrics for reconciliation strategy."""
    _ADAPTIVE_SWITCHER.update_performance(strategy_name, success, latency_ms, cost_usd, quality_score)


def enable_adaptive_reconciliation(enabled: bool = True) -> None:
    """Enable or disable adaptive reconciliation switching."""
    _ADAPTIVE_SWITCHER.enabled = enabled
