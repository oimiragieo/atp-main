"""Integration between error budget enforcer and tail sampler (GAP-365).

Periodically monitors error budget status and feeds measurements to the
tail sampler to adjust sampling rates based on error budget consumption.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from metrics.registry import REGISTRY

from .error_budget_tail_sampler import record_error_budget_for_sampling

logger = logging.getLogger(__name__)


class ErrorBudgetTailSamplerIntegration:
    """Integrates error budget monitoring with tail sampling."""

    def __init__(
        self,
        error_budget_config_file: str = "tools/error_budget_config.json",
        check_interval_seconds: int = 60,  # Check every minute
        enabled: bool = True,
    ):
        self.error_budget_config_file = error_budget_config_file
        self.check_interval_seconds = check_interval_seconds
        self.enabled = enabled
        self._task: asyncio.Task[Any] | None = None
        self._running = False

        # Metrics
        self._c_integration_checks = REGISTRY.counter("error_budget_integration_checks_total")
        self._g_budget_consumption = REGISTRY.gauge("error_budget_integration_consumption_pct")
        self._g_error_rate = REGISTRY.gauge("error_budget_integration_error_rate_pct")

    async def start(self) -> None:
        """Start the integration monitoring loop."""
        if not self.enabled:
            logger.info("Error budget tail sampler integration disabled")
            return

        if self._running:
            logger.warning("Error budget tail sampler integration already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Started error budget tail sampler integration")

    async def stop(self) -> None:
        """Stop the integration monitoring loop."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped error budget tail sampler integration")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop that checks error budget status periodically."""
        while self._running:
            try:
                await self._check_and_update_sampling()
            except Exception as e:
                logger.error(f"Error in error budget monitoring loop: {e}")

            await asyncio.sleep(self.check_interval_seconds)

    async def _check_and_update_sampling(self) -> None:
        """Check error budget status and update tail sampler."""
        try:
            # Import here to avoid circular imports and handle missing dependencies
            import os
            import sys

            # Add tools directory to path for importing error_budget_enforcer
            tools_path = os.path.join(os.path.dirname(__file__), "..", "tools")
            if tools_path not in sys.path:
                sys.path.insert(0, tools_path)

            from error_budget_enforcer import ErrorBudgetEnforcer

            # Create enforcer instance
            enforcer = ErrorBudgetEnforcer(self.error_budget_config_file)

            # Get status for all SLOs
            status = enforcer.get_budget_status()

            # Calculate aggregate metrics across all SLOs
            total_budget_consumption = 0.0
            total_error_rate = 0.0
            slo_count = len(status)

            if slo_count > 0:
                for _slo_name, slo_status in status.items():
                    # Use budget remaining as inverse of consumption
                    budget_remaining = slo_status.get("budget_remaining_percent", 100.0)
                    budget_consumption = 100.0 - budget_remaining
                    total_budget_consumption += budget_consumption

                    error_rate = slo_status.get("error_rate", 0.0)
                    total_error_rate += error_rate

                # Average across SLOs
                avg_budget_consumption = total_budget_consumption / slo_count
                avg_error_rate = total_error_rate / slo_count

                # Update metrics
                self._g_budget_consumption.set(avg_budget_consumption)
                self._g_error_rate.set(avg_error_rate)
                self._c_integration_checks.inc()

                # Record for tail sampling
                record_error_budget_for_sampling(avg_budget_consumption, avg_error_rate)

                logger.debug(
                    f"Error budget integration: consumption={avg_budget_consumption:.1f}%, "
                    f"error_rate={avg_error_rate:.1f}%, SLOs={slo_count}"
                )

        except ImportError as e:
            logger.warning(f"Error budget enforcer not available: {e}")
        except Exception as e:
            logger.error(f"Error checking error budget status: {e}")


# Global instance
_integration: ErrorBudgetTailSamplerIntegration | None = None


def get_error_budget_integration() -> ErrorBudgetTailSamplerIntegration:
    """Get the global error budget integration instance."""
    global _integration
    if _integration is None:
        _integration = ErrorBudgetTailSamplerIntegration()
    return _integration


def init_error_budget_integration(
    config_file: str = "tools/error_budget_config.json",
    check_interval_seconds: int = 60,
    enabled: bool = True,
) -> ErrorBudgetTailSamplerIntegration:
    """Initialize the global error budget integration."""
    global _integration
    _integration = ErrorBudgetTailSamplerIntegration(
        error_budget_config_file=config_file,
        check_interval_seconds=check_interval_seconds,
        enabled=enabled,
    )
    return _integration
