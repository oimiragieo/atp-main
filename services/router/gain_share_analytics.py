"""GAP-335B: Gain-share cost analytics module.

Provides comprehensive analytics for cost savings achieved through routing optimization,
including baseline frontier model repository and realized savings computation for
gain-share billing arrangements and ROI reporting.
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

from metrics.registry import REGISTRY


@dataclass
class BaselineEntry:
    """Historical baseline cost entry for gain-share analytics."""

    timestamp: int  # Unix timestamp
    model: str
    tokens_used: int
    baseline_cost_usd: float
    actual_cost_usd: float
    savings_usd: float
    tenant: str
    adapter: str


@dataclass
class FrontierModel:
    """Frontier model baseline for cost comparison."""

    model_name: str
    cost_per_1k_tokens_usd: float
    capabilities: list[str]
    last_updated: int


class GainShareAnalytics:
    """Analytics service for gain-share cost optimization and ROI reporting."""

    def __init__(self, data_dir: Optional[str] = None) -> None:
        # Metrics for gain-share analytics
        self._gain_share_savings_usd_total = REGISTRY.counter("gain_share_savings_usd_total")
        self._baseline_entries_count = REGISTRY.gauge("gain_share_baseline_entries_total")
        self._avg_savings_pct = REGISTRY.gauge("gain_share_avg_savings_pct")

        # Data directory for persistence
        self._data_dir = data_dir or os.path.dirname(__file__)

        # Frontier model repository
        self._frontier_models: dict[str, FrontierModel] = {}
        self._baseline_history: list[BaselineEntry] = []

        # Load existing data
        self._load_frontier_models()
        self._load_baseline_history()

    def _load_frontier_models(self) -> None:
        """Load frontier model repository from disk."""
        frontier_file = os.path.join(self._data_dir, "frontier_models.json")

        try:
            with open(frontier_file) as f:
                data = json.load(f)
                for item in data:
                    model = FrontierModel(
                        model_name=item["model_name"],
                        cost_per_1k_tokens_usd=item["cost_per_1k_tokens_usd"],
                        capabilities=item.get("capabilities", []),
                        last_updated=item.get("last_updated", int(time.time())),
                    )
                    self._frontier_models[model.model_name] = model
        except (FileNotFoundError, json.JSONDecodeError):
            # Initialize with default frontier models
            self._initialize_default_frontier_models()

    def _initialize_default_frontier_models(self) -> None:
        """Initialize default frontier models if file doesn't exist."""
        defaults = [
            FrontierModel(
                model_name="premium-model",
                cost_per_1k_tokens_usd=0.03,
                capabilities=["reasoning", "code", "dialog"],
                last_updated=int(time.time()),
            ),
            FrontierModel(
                model_name="openrouter:anthropic/claude-3.5-sonnet",
                cost_per_1k_tokens_usd=0.002,
                capabilities=["reasoning"],
                last_updated=int(time.time()),
            ),
        ]

        for model in defaults:
            self._frontier_models[model.model_name] = model

        self._save_frontier_models()

    def _save_frontier_models(self) -> None:
        """Save frontier models to disk."""
        frontier_file = os.path.join(self._data_dir, "frontier_models.json")

        data = []
        for model in self._frontier_models.values():
            data.append({
                "model_name": model.model_name,
                "cost_per_1k_tokens_usd": model.cost_per_1k_tokens_usd,
                "capabilities": model.capabilities,
                "last_updated": model.last_updated,
            })

        with open(frontier_file, "w") as f:
            json.dump(data, f, indent=2)

    def _load_baseline_history(self) -> None:
        """Load baseline history from disk."""
        history_file = os.path.join(self._data_dir, "baseline_history.jsonl")

        try:
            with open(history_file) as f:
                for line in f:
                    if line.strip():
                        entry_data = json.loads(line.strip())
                        entry = BaselineEntry(
                            timestamp=entry_data["timestamp"],
                            model=entry_data["model"],
                            tokens_used=entry_data["tokens_used"],
                            baseline_cost_usd=entry_data["baseline_cost_usd"],
                            actual_cost_usd=entry_data["actual_cost_usd"],
                            savings_usd=entry_data["savings_usd"],
                            tenant=entry_data["tenant"],
                            adapter=entry_data["adapter"],
                        )
                        self._baseline_history.append(entry)
        except FileNotFoundError:
            # No history file yet, start empty
            pass

        # Update metrics
        self._baseline_entries_count.set(len(self._baseline_history))

    def _save_baseline_entry(self, entry: BaselineEntry) -> None:
        """Save baseline entry to history file."""
        history_file = os.path.join(self._data_dir, "baseline_history.jsonl")

        entry_data = {
            "timestamp": entry.timestamp,
            "model": entry.model,
            "tokens_used": entry.tokens_used,
            "baseline_cost_usd": entry.baseline_cost_usd,
            "actual_cost_usd": entry.actual_cost_usd,
            "savings_usd": entry.savings_usd,
            "tenant": entry.tenant,
            "adapter": entry.adapter,
        }

        with open(history_file, "a") as f:
            f.write(json.dumps(entry_data) + "\n")

    def update_frontier_model(
        self,
        model_name: str,
        cost_per_1k_tokens_usd: float,
        capabilities: Optional[list[str]] = None,
    ) -> None:
        """Update or add a frontier model baseline."""
        if capabilities is None:
            capabilities = []

        model = FrontierModel(
            model_name=model_name,
            cost_per_1k_tokens_usd=cost_per_1k_tokens_usd,
            capabilities=capabilities,
            last_updated=int(time.time()),
        )

        self._frontier_models[model_name] = model
        self._save_frontier_models()

    def get_frontier_model(self, model_name: str) -> Optional[FrontierModel]:
        """Get frontier model by name."""
        return self._frontier_models.get(model_name)

    def get_all_frontier_models(self) -> dict[str, FrontierModel]:
        """Get all frontier models."""
        return dict(self._frontier_models)

    def calculate_realized_savings(
        self,
        chosen_model: str,
        tokens_used: int,
        actual_cost_usd: float,
        tenant: str,
        adapter: str,
    ) -> dict[str, Any]:
        """Calculate realized savings vs frontier baseline and record for analytics.

        Args:
            chosen_model: The model that was selected
            tokens_used: Number of tokens consumed
            actual_cost_usd: Actual cost incurred
            tenant: Tenant identifier
            adapter: Adapter identifier

        Returns:
            Dict with savings metrics and baseline comparison
        """
        # Find the most expensive frontier model as baseline
        frontier_model = None
        max_cost = 0.0

        for model in self._frontier_models.values():
            if model.cost_per_1k_tokens_usd > max_cost:
                max_cost = model.cost_per_1k_tokens_usd
                frontier_model = model

        if not frontier_model:
            # Fallback if no frontier models
            frontier_model = FrontierModel(
                model_name="fallback-frontier",
                cost_per_1k_tokens_usd=0.03,
                capabilities=[],
                last_updated=int(time.time()),
            )

        # Calculate baseline cost (what frontier would cost)
        baseline_cost_usd = (tokens_used / 1000) * frontier_model.cost_per_1k_tokens_usd

        # Calculate savings
        savings_usd = baseline_cost_usd - actual_cost_usd

        # Calculate savings percentage
        savings_pct = (savings_usd / baseline_cost_usd * 100) if baseline_cost_usd > 0 else 0.0

        # Create baseline entry
        entry = BaselineEntry(
            timestamp=int(time.time()),
            model=chosen_model,
            tokens_used=tokens_used,
            baseline_cost_usd=baseline_cost_usd,
            actual_cost_usd=actual_cost_usd,
            savings_usd=savings_usd,
            tenant=tenant,
            adapter=adapter,
        )

        # Record the entry
        self._baseline_history.append(entry)
        self._save_baseline_entry(entry)

        # Update metrics
        self._gain_share_savings_usd_total.inc(int(savings_usd * 1_000_000))  # Micros
        self._baseline_entries_count.set(len(self._baseline_history))
        self._update_avg_savings_pct()

        return {
            "savings_usd": savings_usd,
            "savings_pct": savings_pct,
            "baseline_cost_usd": baseline_cost_usd,
            "actual_cost_usd": actual_cost_usd,
            "frontier_model": frontier_model.model_name,
            "frontier_cost_per_1k": frontier_model.cost_per_1k_tokens_usd,
        }

    def _update_avg_savings_pct(self) -> None:
        """Update average savings percentage metric."""
        if not self._baseline_history:
            self._avg_savings_pct.set(0.0)
            return

        total_baseline = sum(entry.baseline_cost_usd for entry in self._baseline_history)
        total_savings = sum(entry.savings_usd for entry in self._baseline_history)

        if total_baseline > 0:
            avg_savings_pct = (total_savings / total_baseline) * 100
            self._avg_savings_pct.set(avg_savings_pct)
        else:
            self._avg_savings_pct.set(0.0)

    def get_savings_summary(
        self,
        tenant: Optional[str] = None,
        since_timestamp: Optional[int] = None,
    ) -> dict[str, Any]:
        """Get savings summary for analytics and reporting.

        Args:
            tenant: Filter by specific tenant (optional)
            since_timestamp: Filter entries since this timestamp (optional)

        Returns:
            Dict with savings summary statistics
        """
        # Filter entries
        filtered_entries = self._baseline_history

        if tenant:
            filtered_entries = [e for e in filtered_entries if e.tenant == tenant]

        if since_timestamp:
            filtered_entries = [e for e in filtered_entries if e.timestamp >= since_timestamp]

        if not filtered_entries:
            return {
                "total_entries": 0,
                "total_savings_usd": 0.0,
                "avg_savings_pct": 0.0,
                "total_baseline_cost_usd": 0.0,
                "total_actual_cost_usd": 0.0,
            }

        total_savings = sum(e.savings_usd for e in filtered_entries)
        total_baseline = sum(e.baseline_cost_usd for e in filtered_entries)
        total_actual = sum(e.actual_cost_usd for e in filtered_entries)

        avg_savings_pct = (total_savings / total_baseline * 100) if total_baseline > 0 else 0.0

        return {
            "total_entries": len(filtered_entries),
            "total_savings_usd": total_savings,
            "avg_savings_pct": avg_savings_pct,
            "total_baseline_cost_usd": total_baseline,
            "total_actual_cost_usd": total_actual,
            "time_range": {
                "oldest": min(e.timestamp for e in filtered_entries),
                "newest": max(e.timestamp for e in filtered_entries),
            } if filtered_entries else None,
        }

    def get_gain_share_report(
        self,
        tenant: str,
        gain_share_pct: float = 30.0,  # 30% gain-share by default
    ) -> dict[str, Any]:
        """Generate gain-share report for a tenant.

        Args:
            tenant: Tenant identifier
            gain_share_pct: Percentage of savings to share (default 30%)

        Returns:
            Dict with gain-share billing information
        """
        summary = self.get_savings_summary(tenant=tenant)

        if summary["total_entries"] == 0:
            return {
                "tenant": tenant,
                "total_savings_usd": 0.0,
                "gain_share_amount_usd": 0.0,
                "gain_share_pct": gain_share_pct,
                "period_entries": 0,
            }

        gain_share_amount = summary["total_savings_usd"] * (gain_share_pct / 100)

        return {
            "tenant": tenant,
            "total_savings_usd": summary["total_savings_usd"],
            "gain_share_amount_usd": gain_share_amount,
            "gain_share_pct": gain_share_pct,
            "period_entries": summary["total_entries"],
            "avg_savings_pct": summary["avg_savings_pct"],
        }


# Global instance
gain_share_analytics = GainShareAnalytics()
