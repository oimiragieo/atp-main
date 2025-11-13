"""
Per-tool cost caps and enforcement system.
"""

import logging
from dataclasses import dataclass


@dataclass
class CostCap:
    """Cost cap configuration for a tool."""

    tool_id: str
    usd_limit_micros: int
    token_limit: int
    current_usd_micros: int = 0
    current_tokens: int = 0
    enabled: bool = True


class CostCapRegistry:
    """Registry for managing per-tool cost caps."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.caps: dict[str, CostCap] = {}
        self._cap_exceeded_count = 0

    def register_cap(self, cap: CostCap) -> None:
        """Register a cost cap for a tool."""
        self.caps[cap.tool_id] = cap
        self.logger.info(f"Registered cost cap for tool {cap.tool_id}")

    def get_cap(self, tool_id: str) -> CostCap | None:
        """Get the cost cap for a tool."""
        return self.caps.get(tool_id)

    def check_and_update_cost(self, tool_id: str, usd_micros: int, tokens: int) -> bool:
        """Check if the cost is within limits and update current usage."""
        cap = self.get_cap(tool_id)
        if not cap or not cap.enabled:
            return True

        new_usd = cap.current_usd_micros + usd_micros
        new_tokens = cap.current_tokens + tokens

        if new_usd > cap.usd_limit_micros or new_tokens > cap.token_limit:
            self._cap_exceeded_count += 1
            self.logger.warning(f"Cost cap exceeded for tool {tool_id}")
            return False

        cap.current_usd_micros = new_usd
        cap.current_tokens = new_tokens
        return True

    def reset_cap(self, tool_id: str) -> None:
        """Reset the cost cap for a tool."""
        cap = self.get_cap(tool_id)
        if cap:
            cap.current_usd_micros = 0
            cap.current_tokens = 0
            self.logger.info(f"Reset cost cap for tool {tool_id}")

    def get_cap_exceeded_count(self) -> int:
        """Get the total number of cap exceeded events."""
        return self._cap_exceeded_count

    def get_remaining_budget(self, tool_id: str) -> dict[str, int] | None:
        """Get remaining budget for a tool."""
        cap = self.get_cap(tool_id)
        if not cap:
            return None

        return {
            "usd_micros_remaining": cap.usd_limit_micros - cap.current_usd_micros,
            "tokens_remaining": cap.token_limit - cap.current_tokens,
        }


# Global registry instance
_cost_cap_registry = CostCapRegistry()


def get_cost_cap_registry() -> CostCapRegistry:
    """Get the global cost cap registry."""
    return _cost_cap_registry


def register_tool_cost_cap(tool_id: str, usd_limit_micros: int, token_limit: int) -> None:
    """Register a cost cap for a tool."""
    cap = CostCap(tool_id=tool_id, usd_limit_micros=usd_limit_micros, token_limit=token_limit)
    _cost_cap_registry.register_cap(cap)


def check_tool_cost_cap(tool_id: str, usd_micros: int, tokens: int) -> bool:
    """Check if tool cost is within cap limits."""
    return _cost_cap_registry.check_and_update_cost(tool_id, usd_micros, tokens)
