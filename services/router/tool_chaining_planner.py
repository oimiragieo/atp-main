"""Tool Chaining Planner (GAP-251)

Implements intelligent planning and execution of tool chains for complex reasoning tasks.
Supports dependency resolution, parallel execution, and failure recovery for tool sequences.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from metrics.registry import REGISTRY


class ToolChainState(Enum):
    """States for tool chain execution."""

    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ToolExecutionResult(Enum):
    """Result of a tool execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"


@dataclass
class ToolDescriptor:
    """Descriptor for a tool that can be chained."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    execute_func: Callable[[dict[str, Any]], dict[str, Any]]
    cost_estimate: float = 0.0
    latency_estimate_seconds: float = 1.0
    required_permissions: list[str] = field(default_factory=list)

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        """Basic input validation against schema."""
        # Simple validation - check required fields exist
        required = self.input_schema.get("required", [])
        return all(field in input_data for field in required)

    def estimate_cost(self, input_data: dict[str, Any]) -> float:
        """Estimate execution cost based on input size."""
        # Simple heuristic: base cost + size-based multiplier
        input_size = len(str(input_data))
        return self.cost_estimate + (input_size * 0.0001)


@dataclass
class ToolStep:
    """A single step in a tool chain."""

    step_id: str
    tool_name: str
    input_data: dict[str, Any]
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None
    cost_incurred: float = 0.0

    @property
    def is_completed(self) -> bool:
        """Check if the step is completed."""
        return self.status in ["completed", "failed", "skipped"]

    @property
    def is_successful(self) -> bool:
        """Check if the step completed successfully."""
        return self.status == "completed"

    @property
    def duration(self) -> float | None:
        """Get the execution duration."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None


@dataclass
class ToolChain:
    """A planned sequence of tool executions."""

    chain_id: str
    goal: str
    steps: dict[str, ToolStep]
    execution_order: list[str] = field(default_factory=list)
    state: ToolChainState = ToolChainState.IDLE
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    total_cost: float = 0.0
    error: str | None = None

    @property
    def is_active(self) -> bool:
        """Check if the chain is currently active."""
        return self.state in [ToolChainState.PLANNING, ToolChainState.EXECUTING]

    @property
    def is_completed(self) -> bool:
        """Check if the chain is completed."""
        return self.state in [ToolChainState.COMPLETED, ToolChainState.FAILED, ToolChainState.CANCELLED]

    @property
    def duration(self) -> float | None:
        """Get the total execution duration."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None

    def get_pending_steps(self) -> list[ToolStep]:
        """Get all pending steps."""
        return [step for step in self.steps.values() if step.status == "pending"]

    def get_ready_steps(self) -> list[ToolStep]:
        """Get steps that are ready to execute (dependencies satisfied)."""
        ready = []
        for step in self.steps.values():
            if step.status != "pending":
                continue
            # Check if all dependencies are completed successfully
            deps_satisfied = all(
                self.steps[dep_id].is_successful for dep_id in step.dependencies if dep_id in self.steps
            )
            if deps_satisfied:
                ready.append(step)
        return ready


class ToolChainingPlanner:
    """Plans and executes sequences of tool calls for complex tasks."""

    def __init__(self):
        self.tool_registry: dict[str, ToolDescriptor] = {}
        self.chains: dict[str, ToolChain] = {}

        # Metrics
        self._chains_created = REGISTRY.counter("atp_tool_chains_created_total")
        self._chains_completed = REGISTRY.counter("atp_tool_chains_completed_total")
        self._chains_failed = REGISTRY.counter("atp_tool_chains_failed_total")
        self._steps_executed = REGISTRY.counter("atp_tool_steps_executed_total")
        self._step_failures = REGISTRY.counter("atp_tool_step_failures_total")
        self._chain_duration = REGISTRY.histogram("atp_tool_chain_duration_seconds", [1, 5, 10, 30, 60, 300])
        self._step_duration = REGISTRY.histogram("atp_tool_step_duration_seconds", [0.1, 0.5, 1, 5, 10, 30])
        self._chain_cost = REGISTRY.histogram("atp_tool_chain_cost_usd", [0.01, 0.1, 1, 10, 100])
        self._active_chains = REGISTRY.gauge("atp_tool_chains_active")
        self._chain_success_rate = REGISTRY.histogram("atp_tool_chain_success_rate", [0, 0.25, 0.5, 0.75, 1.0])

    def register_tool(self, tool: ToolDescriptor) -> None:
        """Register a tool in the registry."""
        self.tool_registry[tool.name] = tool
        logging.info(f"Registered tool: {tool.name}")

    def create_chain(self, goal: str, initial_input: dict[str, Any]) -> str:
        """Create a new tool chain for a goal."""
        chain_id = f"chain_{uuid.uuid4().hex[:8]}"
        chain = ToolChain(chain_id=chain_id, goal=goal, steps={})
        self.chains[chain_id] = chain
        self._chains_created.inc()
        self._active_chains.inc()

        # Create initial planning step
        self._plan_chain(chain, initial_input)

        logging.info(f"Created tool chain {chain_id} for goal: {goal}")
        return chain_id

    def _plan_chain(self, chain: ToolChain, initial_input: dict[str, Any]) -> None:
        """Plan the tool chain based on the goal and input."""
        # Simple planning heuristic - this could be enhanced with ML/LLM
        goal_lower = chain.goal.lower()

        if "search" in goal_lower and "memory" in goal_lower:
            # Memory search chain
            search_step = self._create_step("memory_search", {"query": initial_input.get("query", "")})
            chain.steps[search_step.step_id] = search_step
            chain.execution_order.append(search_step.step_id)

        elif "analyze" in goal_lower and "document" in goal_lower:
            # Document analysis chain
            fetch_step = self._create_step("fetch_document", {"doc_id": initial_input.get("doc_id", "")})
            analyze_step = self._create_step("analyze_text", {"text": ""}, [fetch_step.step_id])

            chain.steps[fetch_step.step_id] = fetch_step
            chain.steps[analyze_step.step_id] = analyze_step
            chain.execution_order.extend([fetch_step.step_id, analyze_step.step_id])

        elif "summarize" in goal_lower:
            # Summarization chain
            search_step = self._create_step("memory_search", {"query": initial_input.get("topic", "")})
            summarize_step = self._create_step("summarize_content", {"content": ""}, [search_step.step_id])

            chain.steps[search_step.step_id] = search_step
            chain.steps[summarize_step.step_id] = summarize_step
            chain.execution_order.extend([search_step.step_id, summarize_step.step_id])

        else:
            # Generic completion chain
            complete_step = self._create_step("complete_prompt", {"prompt": chain.goal})
            chain.steps[complete_step.step_id] = complete_step
            chain.execution_order.append(complete_step.step_id)

    def _create_step(
        self, tool_name: str, input_data: dict[str, Any], dependencies: list[str] | None = None
    ) -> ToolStep:
        """Create a tool execution step."""
        step_id = f"step_{uuid.uuid4().hex[:8]}"
        return ToolStep(step_id=step_id, tool_name=tool_name, input_data=input_data, dependencies=dependencies or [])

    def start_chain(self, chain_id: str) -> None:
        """Start execution of a tool chain."""
        if chain_id not in self.chains:
            raise ValueError(f"Chain {chain_id} not found")

        chain = self.chains[chain_id]
        if chain.state != ToolChainState.IDLE:
            raise ValueError(f"Chain {chain_id} is not in IDLE state")

        chain.state = ToolChainState.EXECUTING
        chain.started_at = time.time()

        logging.info(f"Started tool chain {chain_id}")

    def execute_step(self, chain_id: str, step_id: str) -> ToolExecutionResult:
        """Execute a single step in the chain."""
        if chain_id not in self.chains:
            raise ValueError(f"Chain {chain_id} not found")

        chain = self.chains[chain_id]
        if step_id not in chain.steps:
            raise ValueError(f"Step {step_id} not found in chain {chain_id}")

        step = chain.steps[step_id]
        if step.status != "pending":
            logging.warning(f"Step {step_id} is already {step.status}")
            return ToolExecutionResult.SKIPPED

        # Check if tool exists
        if step.tool_name not in self.tool_registry:
            step.status = "failed"
            step.error = f"Tool {step.tool_name} not found"
            step.completed_at = time.time()
            self._step_failures.inc()
            logging.error(f"Step {step_id} failed: tool {step.tool_name} not found")
            return ToolExecutionResult.FAILURE

        tool = self.tool_registry[step.tool_name]

        # Validate input
        if not tool.validate_input(step.input_data):
            step.status = "failed"
            step.error = f"Invalid input for tool {step.tool_name}"
            step.completed_at = time.time()
            self._step_failures.inc()
            logging.error(f"Step {step_id} failed: invalid input")
            return ToolExecutionResult.FAILURE

        # Execute the tool
        try:
            step.started_at = time.time()
            result = tool.execute_func(step.input_data)
            step.completed_at = time.time()
            step.result = result
            step.status = "completed"
            step.cost_incurred = tool.estimate_cost(step.input_data)
            chain.total_cost += step.cost_incurred

            self._steps_executed.inc()
            if step.duration:
                self._step_duration.observe(step.duration)

            logging.info(f"Step {step_id} completed successfully")
            return ToolExecutionResult.SUCCESS

        except Exception as e:
            step.status = "failed"
            step.error = str(e)
            step.completed_at = time.time()
            self._step_failures.inc()
            logging.error(f"Step {step_id} failed: {e}")
            return ToolExecutionResult.FAILURE

    def execute_chain(self, chain_id: str) -> None:
        """Execute all steps in a chain."""
        if chain_id not in self.chains:
            raise ValueError(f"Chain {chain_id} not found")

        chain = self.chains[chain_id]
        if chain.state != ToolChainState.EXECUTING:
            return

        # Check if any steps are already failed
        failed_steps = [step_id for step_id, step in chain.steps.items() if step.status == "failed"]
        if failed_steps:
            chain.state = ToolChainState.FAILED
            chain.error = f"Step {failed_steps[0]} failed"
            chain.completed_at = time.time()
            self._chains_failed.inc()
            self._active_chains.dec()
            if chain.duration:
                self._chain_duration.observe(chain.duration)
            self._chain_cost.observe(chain.total_cost)
            return

        # Execute steps in order
        for step_id in chain.execution_order:
            if step_id not in chain.steps:
                continue

            step = chain.steps[step_id]

            # Wait for dependencies
            if not self._are_dependencies_satisfied(chain, step):
                continue

            result = self.execute_step(chain_id, step_id)

            if result == ToolExecutionResult.FAILURE:
                # Chain failed
                chain.state = ToolChainState.FAILED
                chain.error = f"Step {step_id} failed"
                chain.completed_at = time.time()
                self._chains_failed.inc()
                self._active_chains.dec()
                if chain.duration:
                    self._chain_duration.observe(chain.duration)
                self._chain_cost.observe(chain.total_cost)
                return

        # Check if chain is complete
        pending_steps = chain.get_pending_steps()
        if not pending_steps:
            chain.state = ToolChainState.COMPLETED
            chain.completed_at = time.time()
            self._chains_completed.inc()
            self._active_chains.dec()
            if chain.duration:
                self._chain_duration.observe(chain.duration)
            self._chain_cost.observe(chain.total_cost)
            success_rate = sum(1 for s in chain.steps.values() if s.is_successful) / len(chain.steps)
            self._chain_success_rate.observe(success_rate)
            logging.info(f"Chain {chain_id} completed successfully")

    def _are_dependencies_satisfied(self, chain: ToolChain, step: ToolStep) -> bool:
        """Check if all dependencies of a step are satisfied."""
        for dep_id in step.dependencies:
            if dep_id not in chain.steps:
                continue
            dep_step = chain.steps[dep_id]
            if not dep_step.is_successful:
                return False
        return True

    def cancel_chain(self, chain_id: str) -> None:
        """Cancel a tool chain."""
        if chain_id not in self.chains:
            raise ValueError(f"Chain {chain_id} not found")

        chain = self.chains[chain_id]
        if chain.is_completed:
            return

        chain.state = ToolChainState.CANCELLED
        chain.completed_at = time.time()
        self._active_chains.dec()

        logging.info(f"Cancelled tool chain {chain_id}")

    def get_chain_status(self, chain_id: str) -> dict[str, Any] | None:
        """Get the current status of a tool chain."""
        if chain_id not in self.chains:
            return None

        chain = self.chains[chain_id]
        return {
            "chain_id": chain.chain_id,
            "goal": chain.goal,
            "state": chain.state.value,
            "created_at": chain.created_at,
            "started_at": chain.started_at,
            "completed_at": chain.completed_at,
            "duration": chain.duration,
            "total_cost": chain.total_cost,
            "steps": {
                step_id: {
                    "tool_name": step.tool_name,
                    "status": step.status,
                    "dependencies": step.dependencies,
                    "started_at": step.started_at,
                    "completed_at": step.completed_at,
                    "duration": step.duration,
                    "cost_incurred": step.cost_incurred,
                    "error": step.error,
                }
                for step_id, step in chain.steps.items()
            },
        }


# Global planner instance
_PLANNER = ToolChainingPlanner()


def get_planner() -> ToolChainingPlanner:
    """Get the global tool chaining planner instance."""
    return _PLANNER
