"""Tests for Tool Chaining Planner (GAP-251)"""

import time
from unittest.mock import MagicMock

from router_service.tool_chaining_planner import (
    ToolChain,
    ToolChainingPlanner,
    ToolChainState,
    ToolDescriptor,
    ToolExecutionResult,
    ToolStep,
    get_planner,
)


class TestToolChainingPlanner:
    """Test the tool chaining planner functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.planner = ToolChainingPlanner()

        # Register mock tools
        self.memory_search_tool = ToolDescriptor(
            name="memory_search",
            description="Search memory for relevant information",
            input_schema={"required": ["query"]},
            output_schema={"type": "object"},
            execute_func=MagicMock(return_value={"results": ["result1", "result2"]}),
            cost_estimate=0.01,
            latency_estimate_seconds=0.5,
        )

        self.analyze_tool = ToolDescriptor(
            name="analyze_text",
            description="Analyze text content",
            input_schema={"required": ["text"]},
            output_schema={"type": "object"},
            execute_func=MagicMock(return_value={"analysis": "positive"}),
            cost_estimate=0.02,
            latency_estimate_seconds=1.0,
        )

        self.summarize_tool = ToolDescriptor(
            name="summarize_content",
            description="Summarize content",
            input_schema={"required": ["content"]},
            output_schema={"type": "object"},
            execute_func=MagicMock(return_value={"summary": "brief summary"}),
            cost_estimate=0.015,
            latency_estimate_seconds=0.8,
        )

        self.planner.register_tool(self.memory_search_tool)
        self.planner.register_tool(self.analyze_tool)
        self.planner.register_tool(self.summarize_tool)

    def test_register_tool(self):
        """Test tool registration."""
        tool = ToolDescriptor(
            name="test_tool", description="Test tool", input_schema={}, output_schema={}, execute_func=lambda x: {}
        )

        self.planner.register_tool(tool)
        assert "test_tool" in self.planner.tool_registry
        assert self.planner.tool_registry["test_tool"] == tool

    def test_create_chain_simple(self):
        """Test creating a simple tool chain."""
        chain_id = self.planner.create_chain("Complete a simple prompt", {"prompt": "Hello"})

        assert chain_id in self.planner.chains
        chain = self.planner.chains[chain_id]

        assert chain.goal == "Complete a simple prompt"
        assert chain.state == ToolChainState.IDLE
        assert len(chain.steps) > 0  # Should have at least one step

    def test_create_chain_memory_search(self):
        """Test creating a memory search chain."""
        chain_id = self.planner.create_chain("Search memory for information", {"query": "test query"})

        chain = self.planner.chains[chain_id]
        assert len(chain.steps) >= 1

        # Should contain a memory_search step
        step_names = [step.tool_name for step in chain.steps.values()]
        assert "memory_search" in step_names

    def test_create_chain_analysis(self):
        """Test creating a document analysis chain."""
        chain_id = self.planner.create_chain("Analyze document content", {"doc_id": "doc123"})

        chain = self.planner.chains[chain_id]
        assert len(chain.steps) >= 2  # Should have fetch and analyze steps

        step_names = [step.tool_name for step in chain.steps.values()]
        assert "fetch_document" in step_names or "analyze_text" in step_names

    def test_start_chain(self):
        """Test starting a chain."""
        chain_id = self.planner.create_chain("Test chain", {"input": "test"})

        self.planner.start_chain(chain_id)

        chain = self.planner.chains[chain_id]
        assert chain.state == ToolChainState.EXECUTING
        assert chain.started_at is not None

    def test_execute_step_success(self):
        """Test successful step execution."""
        chain_id = self.planner.create_chain("Search memory", {"query": "test"})
        chain = self.planner.chains[chain_id]

        # Find the memory search step
        search_step = None
        for step in chain.steps.values():
            if step.tool_name == "memory_search":
                search_step = step
                break

        assert search_step is not None

        result = self.planner.execute_step(chain_id, search_step.step_id)

        assert result == ToolExecutionResult.SUCCESS
        assert search_step.status == "completed"
        assert search_step.result == {"results": ["result1", "result2"]}
        assert search_step.completed_at is not None
        assert search_step.cost_incurred > 0

    def test_execute_step_failure_tool_not_found(self):
        """Test step execution failure when tool is not found."""
        chain_id = self.planner.create_chain("Test chain", {"input": "test"})
        chain = self.planner.chains[chain_id]

        # Manually add a step with non-existent tool
        step = ToolStep(step_id="test_step", tool_name="nonexistent_tool", input_data={})
        chain.steps[step.step_id] = step

        result = self.planner.execute_step(chain_id, step.step_id)

        assert result == ToolExecutionResult.FAILURE
        assert step.status == "failed"
        assert "not found" in step.error

    def test_execute_step_failure_invalid_input(self):
        """Test step execution failure with invalid input."""
        chain_id = self.planner.create_chain("Test chain", {"input": "test"})
        chain = self.planner.chains[chain_id]

        # Manually add a step with invalid input
        step = ToolStep(
            step_id="test_step",
            tool_name="memory_search",
            input_data={},  # Missing required 'query' field
        )
        chain.steps[step.step_id] = step

        result = self.planner.execute_step(chain_id, step.step_id)

        assert result == ToolExecutionResult.FAILURE
        assert step.status == "failed"
        assert "Invalid input" in step.error

    def test_execute_chain_success(self):
        """Test successful chain execution."""
        chain_id = self.planner.create_chain("Search and summarize", {"topic": "test topic"})
        self.planner.start_chain(chain_id)

        self.planner.execute_chain(chain_id)

        chain = self.planner.chains[chain_id]
        assert chain.state == ToolChainState.COMPLETED
        assert chain.completed_at is not None
        assert chain.total_cost > 0

    def test_execute_chain_with_dependencies(self):
        """Test chain execution with dependencies."""
        # Create a chain with dependencies
        chain_id = self.planner.create_chain("Analyze document", {"doc_id": "doc123"})
        self.planner.start_chain(chain_id)

        chain = self.planner.chains[chain_id]

        # Mock the fetch_document tool
        fetch_tool = ToolDescriptor(
            name="fetch_document",
            description="Fetch document",
            input_schema={"required": ["doc_id"]},
            output_schema={"type": "object"},
            execute_func=MagicMock(return_value={"content": "document content"}),
        )
        self.planner.register_tool(fetch_tool)

        # Update analyze step to use the fetched content
        for step in chain.steps.values():
            if step.tool_name == "analyze_text":
                step.input_data = {"text": "document content"}

        self.planner.execute_chain(chain_id)

        # Chain should complete
        assert chain.state == ToolChainState.COMPLETED

    def test_cancel_chain(self):
        """Test cancelling a chain."""
        chain_id = self.planner.create_chain("Test chain", {"input": "test"})
        self.planner.start_chain(chain_id)

        self.planner.cancel_chain(chain_id)

        chain = self.planner.chains[chain_id]
        assert chain.state == ToolChainState.CANCELLED
        assert chain.completed_at is not None

    def test_get_chain_status(self):
        """Test getting chain status."""
        chain_id = self.planner.create_chain("Test chain", {"input": "test"})

        status = self.planner.get_chain_status(chain_id)
        assert status is not None
        assert status["chain_id"] == chain_id
        assert status["goal"] == "Test chain"
        assert status["state"] == "idle"
        assert "steps" in status

    def test_get_chain_status_not_found(self):
        """Test getting status for non-existent chain."""
        status = self.planner.get_chain_status("nonexistent")
        assert status is None

    def test_chain_success_rate_calculation(self):
        """Test that success rate is calculated correctly."""
        chain_id = self.planner.create_chain("Test chain", {"input": "test"})
        chain = self.planner.chains[chain_id]

        # Add multiple steps
        step1 = ToolStep("step1", "memory_search", {"query": "test"})
        step2 = ToolStep("step2", "analyze_text", {"text": "test"})
        step3 = ToolStep("step3", "summarize_content", {"content": "test"})

        chain.steps = {"step1": step1, "step2": step2, "step3": step3}
        chain.execution_order = ["step1", "step2", "step3"]

        # Simulate execution
        step1.status = "completed"
        step2.status = "completed"
        step3.status = "failed"

        self.planner.start_chain(chain_id)
        self.planner.execute_chain(chain_id)

        # Should be failed due to step3 failure
        assert chain.state == ToolChainState.FAILED


class TestToolDescriptor:
    """Test ToolDescriptor functionality."""

    def test_validate_input_valid(self):
        """Test input validation with valid input."""
        tool = ToolDescriptor(
            name="test_tool",
            description="Test tool",
            input_schema={"required": ["field1", "field2"]},
            output_schema={},
            execute_func=lambda x: {},
        )

        valid_input = {"field1": "value1", "field2": "value2"}
        assert tool.validate_input(valid_input)

    def test_validate_input_invalid(self):
        """Test input validation with invalid input."""
        tool = ToolDescriptor(
            name="test_tool",
            description="Test tool",
            input_schema={"required": ["field1", "field2"]},
            output_schema={},
            execute_func=lambda x: {},
        )

        invalid_input = {"field1": "value1"}  # Missing field2
        assert not tool.validate_input(invalid_input)

    def test_estimate_cost(self):
        """Test cost estimation."""
        tool = ToolDescriptor(
            name="test_tool",
            description="Test tool",
            input_schema={},
            output_schema={},
            execute_func=lambda x: {},
            cost_estimate=0.1,
        )

        input_data = {"field": "short"}
        cost = tool.estimate_cost(input_data)

        # Should be base cost + size-based addition
        assert cost >= 0.1


class TestToolStep:
    """Test ToolStep dataclass."""

    def test_step_creation(self):
        """Test ToolStep creation."""
        step = ToolStep(step_id="test_step", tool_name="test_tool", input_data={"input": "test"})

        assert step.step_id == "test_step"
        assert step.tool_name == "test_tool"
        assert step.status == "pending"
        assert not step.is_completed
        assert not step.is_successful

    def test_step_completion(self):
        """Test step completion."""
        step = ToolStep("test_step", "test_tool", {})

        step.status = "completed"
        step.completed_at = time.time()

        assert step.is_completed
        assert step.is_successful

    def test_step_failure(self):
        """Test step failure."""
        step = ToolStep("test_step", "test_tool", {})

        step.status = "failed"
        step.completed_at = time.time()
        step.error = "Test error"

        assert step.is_completed
        assert not step.is_successful

    def test_step_duration(self):
        """Test step duration calculation."""
        step = ToolStep("test_step", "test_tool", {})

        step.started_at = time.time()
        time.sleep(0.01)  # Small delay
        step.completed_at = time.time()

        assert step.duration is not None
        assert step.duration > 0


class TestToolChain:
    """Test ToolChain dataclass."""

    def test_chain_creation(self):
        """Test ToolChain creation."""
        chain = ToolChain(chain_id="test_chain", goal="Test goal", steps={})

        assert chain.chain_id == "test_chain"
        assert chain.goal == "Test goal"
        assert chain.state == ToolChainState.IDLE
        assert not chain.is_active
        assert not chain.is_completed

    def test_chain_active_states(self):
        """Test chain active state detection."""
        chain = ToolChain("test_chain", "Test goal", {})

        active_states = [ToolChainState.PLANNING, ToolChainState.EXECUTING]

        for state in active_states:
            chain.state = state
            assert chain.is_active

    def test_chain_completed_states(self):
        """Test chain completed state detection."""
        chain = ToolChain("test_chain", "Test goal", {})

        completed_states = [ToolChainState.COMPLETED, ToolChainState.FAILED, ToolChainState.CANCELLED]

        for state in completed_states:
            chain.state = state
            assert chain.is_completed

    def test_get_pending_steps(self):
        """Test getting pending steps."""
        chain = ToolChain("test_chain", "Test goal", {})

        step1 = ToolStep("step1", "tool1", {})
        step2 = ToolStep("step2", "tool2", {})
        step2.status = "completed"
        step3 = ToolStep("step3", "tool3", {})

        chain.steps = {"step1": step1, "step2": step2, "step3": step3}

        pending = chain.get_pending_steps()
        assert len(pending) == 2
        assert pending[0].step_id == "step1"
        assert pending[1].step_id == "step3"

    def test_get_ready_steps(self):
        """Test getting ready steps."""
        chain = ToolChain("test_chain", "Test goal", {})

        step1 = ToolStep("step1", "tool1", {})
        step2 = ToolStep("step2", "tool2", {}, ["step1"])
        step3 = ToolStep("step3", "tool3", {}, ["step2"])

        chain.steps = {"step1": step1, "step2": step2, "step3": step3}

        # Initially only step1 should be ready
        ready = chain.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].step_id == "step1"

        # Complete step1
        step1.status = "completed"

        # Now step2 should be ready
        ready = chain.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].step_id == "step2"

        # Complete step2
        step2.status = "completed"

        # Now step3 should be ready
        ready = chain.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].step_id == "step3"


def test_get_planner():
    """Test getting the global planner instance."""
    planner = get_planner()
    assert isinstance(planner, ToolChainingPlanner)

    # Should return the same instance
    planner2 = get_planner()
    assert planner is planner2
