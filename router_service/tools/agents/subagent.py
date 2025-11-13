"""Subagent system for task delegation.

Implements Claude Agent SDK subagent patterns with:
- Programmatic agent definitions
- Tool restrictions per agent
- Context isolation
- Model overrides
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AgentModel(str, Enum):
    """Supported models for subagents."""

    SONNET = "sonnet"
    OPUS = "opus"
    HAIKU = "haiku"
    INHERIT = "inherit"


@dataclass
class AgentDefinition:
    """Subagent definition.

    Best practices from docs:
    - Description should clearly indicate when agent is appropriate
    - Prompt should define expertise and approach
    - Tool restrictions prevent unintended actions
    - Context isolation keeps interactions focused
    """

    name: str
    description: str  # When this agent should be used
    prompt: str  # System instructions defining expertise
    tools: list[str] | None = None  # Allowed tools (None = inherit all)
    model: AgentModel = AgentModel.INHERIT
    max_turns: int = 10
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "name": self.name,
            "description": self.description,
            "prompt": self.prompt,
            "tools": self.tools,
            "model": self.model.value,
            "max_turns": self.max_turns,
            "metadata": self.metadata,
        }


class AgentRegistry:
    """Registry for managing subagent definitions."""

    def __init__(self):
        """Initialize agent registry."""
        self._agents: dict[str, AgentDefinition] = {}

    def register(self, agent: AgentDefinition) -> None:
        """Register a subagent.

        Args:
            agent: Agent definition
        """
        self._agents[agent.name] = agent
        logger.info(f"Registered subagent: {agent.name}")

    def get(self, name: str) -> AgentDefinition | None:
        """Get agent by name."""
        return self._agents.get(name)

    def list_agents(self) -> list[AgentDefinition]:
        """List all registered agents."""
        return list(self._agents.values())

    def match_agent(self, task_description: str) -> AgentDefinition | None:
        """Match most appropriate agent for a task.

        Uses simple keyword matching. For production, use
        embedding-based semantic matching.

        Args:
            task_description: Description of task to perform

        Returns:
            Best matching agent or None
        """
        # Simple keyword matching (enhance with embeddings in production)
        task_lower = task_description.lower()
        best_match = None
        best_score = 0

        for agent in self._agents.values():
            desc_lower = agent.description.lower()
            keywords = desc_lower.split()

            score = sum(1 for keyword in keywords if keyword in task_lower)
            if score > best_score:
                best_score = score
                best_match = agent

        return best_match if best_score > 0 else None


# Predefined expert subagents
EXPERT_AGENTS = [
    AgentDefinition(
        name="code_analyst",
        description="Analyzes code for bugs, security issues, and performance problems. Use for code review, static analysis, and quality assessment tasks.",
        prompt="""You are an expert code analyst specializing in finding bugs, security vulnerabilities, and performance issues.

Your approach:
1. Read and understand the code structure
2. Identify potential issues systematically
3. Provide specific, actionable feedback
4. Explain the impact of each finding
5. Suggest concrete fixes

Focus on:
- Security vulnerabilities (SQL injection, XSS, etc.)
- Logic errors and edge cases
- Performance bottlenecks
- Code quality and maintainability
- Best practice violations""",
        tools=["read", "glob", "grep"],  # Read-only access
        model=AgentModel.SONNET,
    ),
    AgentDefinition(
        name="test_engineer",
        description="Writes and executes tests for code validation. Use for creating unit tests, integration tests, and running test suites.",
        prompt="""You are an expert test engineer specializing in comprehensive test coverage.

Your approach:
1. Understand the code being tested
2. Identify critical paths and edge cases
3. Write clear, maintainable tests
4. Execute tests and analyze failures
5. Iterate until full coverage

Focus on:
- Unit tests for individual functions
- Integration tests for component interaction
- Edge cases and error handling
- Test coverage metrics
- Clear test documentation""",
        tools=["read", "write", "bash", "grep", "glob"],
        model=AgentModel.SONNET,
    ),
    AgentDefinition(
        name="refactoring_specialist",
        description="Refactors code to improve quality, maintainability, and performance. Use for code cleanup, optimization, and architectural improvements.",
        prompt="""You are an expert refactoring specialist focused on code quality and maintainability.

Your approach:
1. Understand existing code thoroughly
2. Identify improvement opportunities
3. Plan refactoring strategy
4. Make incremental, safe changes
5. Validate changes don't break functionality

Focus on:
- Reducing code duplication
- Improving naming and clarity
- Extracting reusable functions
- Optimizing performance
- Following best practices""",
        tools=["read", "write", "edit", "bash", "grep", "glob"],
        model=AgentModel.SONNET,
    ),
    AgentDefinition(
        name="documentation_writer",
        description="Creates comprehensive documentation for code, APIs, and systems. Use for writing docstrings, README files, and technical documentation.",
        prompt="""You are an expert technical writer specializing in clear, comprehensive documentation.

Your approach:
1. Understand the code/system deeply
2. Identify documentation needs
3. Write clear, accurate documentation
4. Include examples and use cases
5. Organize for easy navigation

Focus on:
- Clear, concise explanations
- Practical examples
- API reference documentation
- Architecture diagrams (Mermaid)
- User guides and tutorials""",
        tools=["read", "write", "grep", "glob"],
        model=AgentModel.SONNET,
    ),
    AgentDefinition(
        name="security_auditor",
        description="Performs security audits and vulnerability assessments. Use for finding security issues, analyzing attack surfaces, and recommending fixes.",
        prompt="""You are an expert security auditor specializing in application security.

Your approach:
1. Map the attack surface
2. Identify security vulnerabilities
3. Assess risk and impact
4. Provide remediation guidance
5. Verify fixes

Focus on:
- OWASP Top 10 vulnerabilities
- Authentication and authorization
- Input validation and sanitization
- Cryptography usage
- Secure configuration""",
        tools=["read", "grep", "glob"],  # Read-only
        model=AgentModel.OPUS,  # Use most capable model for security
    ),
]


def register_expert_agents(registry: AgentRegistry) -> None:
    """Register all expert subagents.

    Args:
        registry: Agent registry
    """
    for agent in EXPERT_AGENTS:
        registry.register(agent)


# Global registry instance
_global_registry = AgentRegistry()


def get_agent_registry() -> AgentRegistry:
    """Get the global agent registry."""
    return _global_registry


# Auto-register expert agents
register_expert_agents(_global_registry)
