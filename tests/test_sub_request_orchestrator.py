"""Tests for Sub-request Orchestrator (GAP-250)"""

import time

import pytest

from router_service.sub_request_orchestrator import (
    OrchestrationSession,
    OrchestratorState,
    SubRequest,
    SubRequestOrchestrator,
    get_orchestrator,
)


class TestSubRequestOrchestrator:
    """Test the sub-request orchestrator functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.orchestrator = SubRequestOrchestrator()

    def test_create_session(self):
        """Test session creation."""
        session_id = self.orchestrator.create_session("Test prompt")

        assert session_id in self.orchestrator.sessions
        session = self.orchestrator.sessions[session_id]

        assert session.session_id == session_id
        assert session.initial_prompt == "Test prompt"
        assert session.state == OrchestratorState.IDLE
        assert session.created_at <= time.time()

    def test_add_sub_request(self):
        """Test adding sub-requests to a session."""
        session_id = self.orchestrator.create_session("Test prompt")

        request_id = self.orchestrator.add_sub_request(
            session_id=session_id, prompt="Analyze this text", adapter_name="analyzer_adapter"
        )

        session = self.orchestrator.sessions[session_id]
        assert request_id in session.sub_requests

        sub_request = session.sub_requests[request_id]
        assert sub_request.prompt == "Analyze this text"
        assert sub_request.adapter_name == "analyzer_adapter"
        assert sub_request.status == "pending"
        assert sub_request.dependencies == []

    def test_add_sub_request_with_dependencies(self):
        """Test adding sub-requests with dependencies."""
        session_id = self.orchestrator.create_session("Test prompt")

        # Add first request
        req1_id = self.orchestrator.add_sub_request(
            session_id=session_id, prompt="Step 1", adapter_name="step1_adapter"
        )

        # Add second request with dependency on first
        req2_id = self.orchestrator.add_sub_request(
            session_id=session_id, prompt="Step 2", adapter_name="step2_adapter", dependencies=[req1_id]
        )

        session = self.orchestrator.sessions[session_id]
        assert session.sub_requests[req2_id].dependencies == [req1_id]

    def test_start_session(self):
        """Test starting a session."""
        session_id = self.orchestrator.create_session("Test prompt")

        # Add a request with no dependencies
        self.orchestrator.add_sub_request(
            session_id=session_id, prompt="Initial analysis", adapter_name="analyzer_adapter"
        )

        self.orchestrator.start_session(session_id)

        session = self.orchestrator.sessions[session_id]
        assert session.state == OrchestratorState.EXECUTING
        assert session.started_at is not None

    def test_start_session_no_ready_requests(self):
        """Test starting a session with no ready requests."""
        session_id = self.orchestrator.create_session("Test prompt")

        # Add requests with dependencies that can't be satisfied
        self.orchestrator.add_sub_request(
            session_id=session_id, prompt="Step 1", adapter_name="step1_adapter", dependencies=["nonexistent_dep1"]
        )

        self.orchestrator.add_sub_request(
            session_id=session_id, prompt="Step 2", adapter_name="step2_adapter", dependencies=["nonexistent_dep2"]
        )

        self.orchestrator.start_session(session_id)

        session = self.orchestrator.sessions[session_id]
        assert session.state == OrchestratorState.INITIALIZING  # No ready requests

    def test_complete_sub_request(self):
        """Test completing a sub-request."""
        session_id = self.orchestrator.create_session("Test prompt")

        request_id = self.orchestrator.add_sub_request(
            session_id=session_id, prompt="Test request", adapter_name="test_adapter"
        )

        result = {"response": "Test result", "confidence": 0.95}

        self.orchestrator.complete_sub_request(session_id, request_id, result)

        session = self.orchestrator.sessions[session_id]
        sub_request = session.sub_requests[request_id]

        assert sub_request.status == "completed"
        assert sub_request.result == result
        assert sub_request.completed_at is not None
        assert sub_request.is_completed
        assert sub_request.is_successful

    def test_fail_sub_request(self):
        """Test failing a sub-request."""
        session_id = self.orchestrator.create_session("Test prompt")

        request_id = self.orchestrator.add_sub_request(
            session_id=session_id, prompt="Test request", adapter_name="test_adapter"
        )

        error_msg = "Adapter timeout"

        self.orchestrator.fail_sub_request(session_id, request_id, error_msg)

        session = self.orchestrator.sessions[session_id]
        sub_request = session.sub_requests[request_id]

        assert sub_request.status == "failed"
        assert sub_request.error == error_msg
        assert sub_request.completed_at is not None
        assert sub_request.is_completed
        assert not sub_request.is_successful

    def test_session_completion_success(self):
        """Test successful session completion."""
        session_id = self.orchestrator.create_session("Test prompt")

        # Add and complete a single request
        request_id = self.orchestrator.add_sub_request(
            session_id=session_id, prompt="Test request", adapter_name="test_adapter"
        )

        self.orchestrator.complete_sub_request(session_id, request_id, {"result": "success"})

        session = self.orchestrator.sessions[session_id]
        assert session.state == OrchestratorState.COMPLETED
        assert session.completed_at is not None
        assert session.is_completed

    def test_session_completion_failure(self):
        """Test session completion with failed requests."""
        session_id = self.orchestrator.create_session("Test prompt")

        # Add and fail a request
        request_id = self.orchestrator.add_sub_request(
            session_id=session_id, prompt="Test request", adapter_name="test_adapter"
        )

        self.orchestrator.fail_sub_request(session_id, request_id, "Request failed")

        session = self.orchestrator.sessions[session_id]
        assert session.state == OrchestratorState.FAILED
        assert session.error == "1 sub-request(s) failed"
        assert session.is_completed

    def test_dependency_resolution(self):
        """Test dependency resolution for multi-step workflows."""
        session_id = self.orchestrator.create_session("Multi-step analysis")

        # Step 1: Initial analysis
        step1_id = self.orchestrator.add_sub_request(
            session_id=session_id, prompt="Analyze the input data", adapter_name="analyzer_adapter"
        )

        # Step 2: Depends on step 1
        step2_id = self.orchestrator.add_sub_request(
            session_id=session_id,
            prompt="Generate summary based on analysis",
            adapter_name="summarizer_adapter",
            dependencies=[step1_id],
        )

        # Step 3: Depends on step 2
        step3_id = self.orchestrator.add_sub_request(
            session_id=session_id,
            prompt="Validate the summary",
            adapter_name="validator_adapter",
            dependencies=[step2_id],
        )

        session = self.orchestrator.sessions[session_id]

        # Initially, only step 1 should be ready
        ready_requests = session.get_ready_requests()
        assert len(ready_requests) == 1
        assert ready_requests[0].request_id == step1_id

        # Complete step 1
        self.orchestrator.complete_sub_request(session_id, step1_id, {"analysis": "complete"})

        # Now step 2 should be ready
        ready_requests = session.get_ready_requests()
        assert len(ready_requests) == 1
        assert ready_requests[0].request_id == step2_id

        # Complete step 2
        self.orchestrator.complete_sub_request(session_id, step2_id, {"summary": "generated"})

        # Now step 3 should be ready
        ready_requests = session.get_ready_requests()
        assert len(ready_requests) == 1
        assert ready_requests[0].request_id == step3_id

        # Complete step 3
        self.orchestrator.complete_sub_request(session_id, step3_id, {"validation": "passed"})

        # Session should be completed
        assert session.state == OrchestratorState.COMPLETED

    def test_parallel_execution(self):
        """Test parallel execution of independent requests."""
        session_id = self.orchestrator.create_session("Parallel processing")

        # Add multiple independent requests
        req1_id = self.orchestrator.add_sub_request(
            session_id=session_id, prompt="Process part 1", adapter_name="processor_adapter"
        )

        req2_id = self.orchestrator.add_sub_request(
            session_id=session_id, prompt="Process part 2", adapter_name="processor_adapter"
        )

        req3_id = self.orchestrator.add_sub_request(
            session_id=session_id, prompt="Process part 3", adapter_name="processor_adapter"
        )

        session = self.orchestrator.sessions[session_id]

        # All three should be ready for parallel execution
        ready_requests = session.get_ready_requests()
        assert len(ready_requests) == 3
        ready_ids = {req.request_id for req in ready_requests}
        assert ready_ids == {req1_id, req2_id, req3_id}

        # Complete them in any order
        self.orchestrator.complete_sub_request(session_id, req2_id, {"part": 2})
        self.orchestrator.complete_sub_request(session_id, req1_id, {"part": 1})
        self.orchestrator.complete_sub_request(session_id, req3_id, {"part": 3})

        assert session.state == OrchestratorState.COMPLETED

    def test_get_session_status(self):
        """Test getting session status."""
        session_id = self.orchestrator.create_session("Status test")

        status = self.orchestrator.get_session_status(session_id)
        assert status is not None
        assert status["session_id"] == session_id
        assert status["state"] == "idle"
        assert "sub_requests" in status

    def test_get_session_status_not_found(self):
        """Test getting status for non-existent session."""
        status = self.orchestrator.get_session_status("nonexistent")
        assert status is None

    def test_cancel_session(self):
        """Test cancelling a session."""
        session_id = self.orchestrator.create_session("Cancel test")

        self.orchestrator.add_sub_request(session_id=session_id, prompt="Test request", adapter_name="test_adapter")

        self.orchestrator.start_session(session_id)
        self.orchestrator.cancel_session(session_id)

        session = self.orchestrator.sessions[session_id]
        assert session.state == OrchestratorState.CANCELLED
        assert session.completed_at is not None

    def test_error_handling_invalid_session(self):
        """Test error handling for invalid session operations."""
        with pytest.raises(ValueError, match="Session nonexistent not found"):
            self.orchestrator.add_sub_request("nonexistent", "test", "adapter")

        with pytest.raises(ValueError, match="Session nonexistent not found"):
            self.orchestrator.start_session("nonexistent")

    def test_error_handling_invalid_request(self):
        """Test error handling for invalid request operations."""
        session_id = self.orchestrator.create_session("Error test")

        with pytest.raises(ValueError, match="Request nonexistent not found"):
            self.orchestrator.complete_sub_request(session_id, "nonexistent", {})

        with pytest.raises(ValueError, match="Request nonexistent not found"):
            self.orchestrator.fail_sub_request(session_id, "nonexistent", "error")


class TestSubRequest:
    """Test SubRequest dataclass."""

    def test_sub_request_creation(self):
        """Test SubRequest creation and properties."""
        request = SubRequest(request_id="test_req", prompt="Test prompt", adapter_name="test_adapter")

        assert request.request_id == "test_req"
        assert request.prompt == "Test prompt"
        assert request.adapter_name == "test_adapter"
        assert request.status == "pending"
        assert not request.is_completed
        assert not request.is_successful

    def test_sub_request_completion(self):
        """Test SubRequest completion."""
        request = SubRequest(request_id="test_req", prompt="Test prompt", adapter_name="test_adapter")

        request.status = "completed"
        request.completed_at = time.time()

        assert request.is_completed
        assert request.is_successful

    def test_sub_request_failure(self):
        """Test SubRequest failure."""
        request = SubRequest(request_id="test_req", prompt="Test prompt", adapter_name="test_adapter")

        request.status = "failed"
        request.completed_at = time.time()
        request.error = "Test error"

        assert request.is_completed
        assert not request.is_successful

    def test_sub_request_duration(self):
        """Test SubRequest duration calculation."""
        request = SubRequest(request_id="test_req", prompt="Test prompt", adapter_name="test_adapter")

        request.started_at = time.time()
        time.sleep(0.01)  # Small delay
        request.completed_at = time.time()

        assert request.duration is not None
        assert request.duration > 0


class TestOrchestrationSession:
    """Test OrchestrationSession dataclass."""

    def test_session_creation(self):
        """Test OrchestrationSession creation."""
        session = OrchestrationSession(session_id="test_session", initial_prompt="Test prompt")

        assert session.session_id == "test_session"
        assert session.initial_prompt == "Test prompt"
        assert session.state == OrchestratorState.IDLE
        assert not session.is_active
        assert not session.is_completed

    def test_session_active_states(self):
        """Test session active state detection."""
        session = OrchestrationSession(session_id="test_session", initial_prompt="Test prompt")

        active_states = [OrchestratorState.INITIALIZING, OrchestratorState.EXECUTING, OrchestratorState.WAITING]

        for state in active_states:
            session.state = state
            assert session.is_active

    def test_session_completed_states(self):
        """Test session completed state detection."""
        session = OrchestrationSession(session_id="test_session", initial_prompt="Test prompt")

        completed_states = [OrchestratorState.COMPLETED, OrchestratorState.FAILED, OrchestratorState.CANCELLED]

        for state in completed_states:
            session.state = state
            assert session.is_completed

    def test_get_pending_requests(self):
        """Test getting pending requests."""
        session = OrchestrationSession(session_id="test_session", initial_prompt="Test prompt")

        req1 = SubRequest("req1", "prompt1", "adapter1")
        req2 = SubRequest("req2", "prompt2", "adapter2")
        req2.status = "completed"
        req3 = SubRequest("req3", "prompt3", "adapter3")

        session.sub_requests = {"req1": req1, "req2": req2, "req3": req3}

        pending = session.get_pending_requests()
        assert len(pending) == 2
        assert pending[0].request_id == "req1"
        assert pending[1].request_id == "req3"

    def test_get_ready_requests(self):
        """Test getting ready requests (dependencies satisfied)."""
        session = OrchestrationSession(session_id="test_session", initial_prompt="Test prompt")

        req1 = SubRequest("req1", "prompt1", "adapter1")
        req2 = SubRequest("req2", "prompt2", "adapter2", dependencies=["req1"])
        req3 = SubRequest("req3", "prompt3", "adapter3", dependencies=["req2"])

        session.sub_requests = {"req1": req1, "req2": req2, "req3": req3}

        # Initially only req1 should be ready
        ready = session.get_ready_requests()
        assert len(ready) == 1
        assert ready[0].request_id == "req1"

        # Complete req1
        req1.status = "completed"

        # Now req2 should be ready
        ready = session.get_ready_requests()
        assert len(ready) == 1
        assert ready[0].request_id == "req2"

        # Complete req2
        req2.status = "completed"

        # Now req3 should be ready
        ready = session.get_ready_requests()
        assert len(ready) == 1
        assert ready[0].request_id == "req3"


def test_get_orchestrator():
    """Test getting the global orchestrator instance."""
    orchestrator = get_orchestrator()
    assert isinstance(orchestrator, SubRequestOrchestrator)

    # Should return the same instance
    orchestrator2 = get_orchestrator()
    assert orchestrator is orchestrator2
