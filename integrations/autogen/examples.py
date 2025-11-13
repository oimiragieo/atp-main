# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
ATP AutoGen Integration Examples
This module provides examples of using ATP with AutoGen.
"""

import asyncio
import os

from .atp_agent import (
    ATPAssistantAgent,
    ATPCodeReviewerAgent,
    ATPDataAnalystAgent,
    ATPUserProxyAgent,
)
from .code_execution import create_atp_code_executor
from .function_calling import atp_function, create_builtin_function_registry
from .group_chat import ATPGroupChatManager, create_atp_group_chat


class ATPAutoGenExamples:
    """Examples of ATP AutoGen integration."""

    def __init__(self, atp_base_url: str = "http://localhost:8000", api_key: str = None):
        self.atp_base_url = atp_base_url
        self.api_key = api_key or os.getenv("ATP_API_KEY")

        # Initialize code executor
        self.code_executor = create_atp_code_executor(atp_base_url=atp_base_url, atp_api_key=self.api_key)

        # Initialize function registry
        self.function_registry = create_builtin_function_registry()

        # Add custom functions
        self._register_custom_functions()

    def _register_custom_functions(self):
        """Register custom functions for examples."""

        @atp_function(
            self.function_registry,
            description="Generate a random number between min and max",
            parameter_descriptions={"min_val": "Minimum value (inclusive)", "max_val": "Maximum value (inclusive)"},
        )
        def generate_random_number(min_val: int, max_val: int) -> int:
            """Generate random number in range."""
            import random

            return random.randint(min_val, max_val)

        @atp_function(
            self.function_registry,
            description="Search for information on a topic",
            parameter_descriptions={"query": "Search query"},
        )
        def search_information(query: str) -> str:
            """Mock search function."""
            # In a real implementation, this would call a search API
            return f"Search results for '{query}': [Mock results - implement with real search API]"

    def basic_agent_example(self) -> str:
        """Basic agent conversation example."""
        print("=== Basic Agent Example ===")

        # Create agents
        user_proxy = ATPUserProxyAgent(
            name="User",
            atp_base_url=self.atp_base_url,
            atp_api_key=self.api_key,
            human_input_mode="TERMINATE",  # Auto-terminate for example
        )

        assistant = ATPAssistantAgent(name="Assistant", atp_base_url=self.atp_base_url, atp_api_key=self.api_key)

        # Start conversation
        message = "Hello! Can you help me understand the benefits of microservices architecture?"

        print(f"User: {message}")

        # Initiate chat
        user_proxy.initiate_chat(assistant, message=message, max_turns=2)

        print("Conversation completed!")
        return "Basic agent example completed"

    def code_review_example(self) -> str:
        """Code review with specialized agents example."""
        print("\n=== Code Review Example ===")

        # Create agents
        user_proxy = ATPUserProxyAgent(
            name="Developer", atp_base_url=self.atp_base_url, atp_api_key=self.api_key, human_input_mode="TERMINATE"
        )

        code_reviewer = ATPCodeReviewerAgent(
            name="CodeReviewer", atp_base_url=self.atp_base_url, atp_api_key=self.api_key
        )

        # Code to review
        code_to_review = """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

# Usage
for i in range(10):
    print(fibonacci(i))
        """

        message = f"Please review this Python code:\n\n```python\n{code_to_review}\n```"

        print(f"Developer: {message[:100]}...")

        # Start code review
        user_proxy.initiate_chat(code_reviewer, message=message, max_turns=3)

        print("Code review completed!")
        return "Code review example completed"

    def group_chat_example(self) -> str:
        """Group chat with multiple agents example."""
        print("\n=== Group Chat Example ===")

        # Create agents
        user_proxy = ATPUserProxyAgent(
            name="ProjectManager",
            atp_base_url=self.atp_base_url,
            atp_api_key=self.api_key,
            human_input_mode="TERMINATE",
        )

        developer = ATPAssistantAgent(
            name="Developer",
            atp_base_url=self.atp_base_url,
            atp_api_key=self.api_key,
            system_message="You are a senior software developer. Focus on technical implementation details.",
        )

        data_analyst = ATPDataAnalystAgent(name="DataAnalyst", atp_base_url=self.atp_base_url, atp_api_key=self.api_key)

        code_reviewer = ATPCodeReviewerAgent(
            name="CodeReviewer", atp_base_url=self.atp_base_url, atp_api_key=self.api_key
        )

        # Create group chat
        agents = [user_proxy, developer, data_analyst, code_reviewer]
        group_chat = create_atp_group_chat(agents=agents, max_round=8, speaker_selection_method="expertise_based")

        # Create group chat manager
        manager = ATPGroupChatManager(groupchat=group_chat, atp_base_url=self.atp_base_url, atp_api_key=self.api_key)

        # Start group discussion
        message = """
        We need to build a data processing pipeline that:
        1. Ingests CSV files from multiple sources
        2. Cleans and validates the data
        3. Performs statistical analysis
        4. Generates reports and visualizations
        
        Let's discuss the architecture and implementation approach.
        """

        print(f"ProjectManager: {message[:100]}...")

        # Initiate group chat
        user_proxy.initiate_chat(manager, message=message)

        # Get conversation summary
        summary = group_chat.get_conversation_summary()
        print(f"Group chat summary: {summary}")

        print("Group chat completed!")
        return "Group chat example completed"

    def code_execution_example(self) -> str:
        """Code execution with ATP sandbox example."""
        print("\n=== Code Execution Example ===")

        # Create agents with code execution
        user_proxy = ATPUserProxyAgent(
            name="User",
            atp_base_url=self.atp_base_url,
            atp_api_key=self.api_key,
            human_input_mode="TERMINATE",
            code_execution_config=self.code_executor.create_execution_config(),
        )

        assistant = ATPAssistantAgent(
            name="PythonExpert",
            atp_base_url=self.atp_base_url,
            atp_api_key=self.api_key,
            system_message="You are a Python expert. Write and execute Python code to solve problems.",
        )

        # Request code execution
        message = """
        Please write and execute Python code to:
        1. Create a list of the first 10 prime numbers
        2. Calculate their sum and average
        3. Create a simple visualization (if possible)
        """

        print(f"User: {message}")

        # Start conversation with code execution
        user_proxy.initiate_chat(assistant, message=message, max_turns=4)

        # Show execution stats
        stats = self.code_executor.get_execution_stats()
        print(f"Code execution stats: {stats}")

        print("Code execution example completed!")
        return "Code execution example completed"

    def function_calling_example(self) -> str:
        """Function calling example."""
        print("\n=== Function Calling Example ===")

        # Create agent with function calling
        assistant = ATPAssistantAgent(
            name="FunctionAgent",
            atp_base_url=self.atp_base_url,
            atp_api_key=self.api_key,
            system_message="You can call functions to help users. Use the available functions when appropriate.",
        )

        # Add function registry to agent (in a real implementation, this would be integrated)
        assistant.function_registry = self.function_registry

        # Simulate function calling
        print("Available functions:", assistant.function_registry.list_functions())

        # Example function calls
        try:
            # Call math function
            result1 = asyncio.run(
                assistant.function_registry.call_function("calculate_sum", {"numbers": [1, 2, 3, 4, 5]})
            )
            print(f"Sum calculation result: {result1}")

            # Call string function
            result2 = asyncio.run(
                assistant.function_registry.call_function(
                    "count_words", {"text": "Hello world, this is a test sentence."}
                )
            )
            print(f"Word count result: {result2}")

            # Call custom function
            result3 = asyncio.run(
                assistant.function_registry.call_function("generate_random_number", {"min_val": 1, "max_val": 100})
            )
            print(f"Random number result: {result3}")

        except Exception as e:
            print(f"Function calling error: {e}")

        # Show function execution stats
        stats = self.function_registry.get_execution_stats()
        print(f"Function execution stats: {stats}")

        print("Function calling example completed!")
        return "Function calling example completed"

    def multi_agent_collaboration_example(self) -> str:
        """Complex multi-agent collaboration example."""
        print("\n=== Multi-Agent Collaboration Example ===")

        # Create specialized agents
        project_manager = ATPUserProxyAgent(
            name="ProjectManager",
            atp_base_url=self.atp_base_url,
            atp_api_key=self.api_key,
            human_input_mode="TERMINATE",
            system_message="You coordinate the project and make final decisions.",
        )

        architect = ATPAssistantAgent(
            name="SoftwareArchitect",
            atp_base_url=self.atp_base_url,
            atp_api_key=self.api_key,
            system_message="You design system architecture and make technical decisions.",
        )

        developer = ATPAssistantAgent(
            name="Developer",
            atp_base_url=self.atp_base_url,
            atp_api_key=self.api_key,
            system_message="You implement code based on architectural decisions.",
            code_execution_config=self.code_executor.create_execution_config(),
        )

        tester = ATPAssistantAgent(
            name="QATester",
            atp_base_url=self.atp_base_url,
            atp_api_key=self.api_key,
            system_message="You create test cases and validate implementations.",
        )

        # Create group chat with load balancing
        agents = [project_manager, architect, developer, tester]
        group_chat = create_atp_group_chat(agents=agents, max_round=12, speaker_selection_method="load_balanced")

        manager = ATPGroupChatManager(groupchat=group_chat, atp_base_url=self.atp_base_url, atp_api_key=self.api_key)

        # Set conversation rules
        manager.set_conversation_rules(
            [
                "Each agent should contribute their expertise",
                "Code should be reviewed before implementation",
                "Test cases should be created for all functionality",
                "Keep responses concise and focused",
            ]
        )

        # Complex project task
        project_task = """
        Project: Build a simple REST API for a todo list application
        
        Requirements:
        1. CRUD operations for todo items
        2. User authentication
        3. Data persistence
        4. Input validation
        5. Error handling
        6. Unit tests
        
        Please collaborate to design and implement this system.
        """

        print(f"ProjectManager: {project_task[:100]}...")

        # Start collaboration
        project_manager.initiate_chat(manager, message=project_task)

        # Export conversation
        conversation_export = group_chat.export_conversation("markdown")
        print(f"Conversation exported ({len(conversation_export)} characters)")

        # Get final metrics
        manager_metrics = manager.get_manager_metrics()
        print(f"Manager metrics: {manager_metrics}")

        print("Multi-agent collaboration completed!")
        return "Multi-agent collaboration example completed"

    def streaming_example(self) -> str:
        """Streaming responses example."""
        print("\n=== Streaming Example ===")

        # Create agent with streaming enabled
        assistant = ATPAssistantAgent(
            name="StreamingAssistant",
            atp_base_url=self.atp_base_url,
            atp_api_key=self.api_key,
            streaming=True,  # Enable streaming
            system_message="You provide detailed explanations with streaming responses.",
        )

        user_proxy = ATPUserProxyAgent(
            name="User", atp_base_url=self.atp_base_url, atp_api_key=self.api_key, human_input_mode="TERMINATE"
        )

        message = "Explain the concept of machine learning and its applications in detail."

        print(f"User: {message}")
        print("Assistant (streaming): ", end="", flush=True)

        # Note: In a real implementation, streaming would be handled by the agent
        # This is a simplified example
        user_proxy.initiate_chat(assistant, message=message, max_turns=2)

        print("\nStreaming example completed!")
        return "Streaming example completed"

    def run_all_examples(self):
        """Run all examples."""
        print("Running ATP AutoGen Integration Examples")
        print("=" * 50)

        try:
            # Run examples
            self.basic_agent_example()
            self.code_review_example()
            self.group_chat_example()
            self.code_execution_example()
            self.function_calling_example()
            self.multi_agent_collaboration_example()
            self.streaming_example()

            print("\n" + "=" * 50)
            print("All examples completed successfully!")

        except Exception as e:
            print(f"Error running examples: {e}")
            raise


def main():
    """Main function to run examples."""
    # Initialize examples
    examples = ATPAutoGenExamples(atp_base_url="http://localhost:8000")

    # Run all examples
    examples.run_all_examples()


if __name__ == "__main__":
    main()
