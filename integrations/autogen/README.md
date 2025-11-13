# ATP AutoGen Integration

This package provides comprehensive AutoGen integration for the ATP (AI Text Processing) platform, enabling multi-agent conversations and workflows with ATP's enterprise AI capabilities.

## Features

- **Multi-Agent Support**: Create and manage multiple AI agents with different roles and capabilities
- **Group Chat**: Orchestrate conversations between multiple agents with intelligent speaker selection
- **Code Execution**: Execute code in ATP's sandboxed environments with full safety
- **Function Calling**: Register and call custom functions from agents
- **Specialized Agents**: Pre-built agent types for common use cases
- **Enterprise Integration**: Full integration with ATP's authentication, monitoring, and scaling

## Installation

```bash
# Install AutoGen (required)
pip install pyautogen

# Install additional dependencies for examples
pip install matplotlib pandas numpy  # For data analysis examples
```

## Quick Start

### Basic Agent Conversation

```python
from integrations.autogen import ATPAssistantAgent, ATPUserProxyAgent

# Create agents
user_proxy = ATPUserProxyAgent(
    name="User",
    atp_base_url="http://localhost:8000",
    atp_api_key="your-api-key"
)

assistant = ATPAssistantAgent(
    name="Assistant", 
    atp_base_url="http://localhost:8000",
    atp_api_key="your-api-key"
)

# Start conversation
result = user_proxy.initiate_chat(
    assistant,
    message="Help me design a microservices architecture.",
    max_turns=5
)
```

### Group Chat with Multiple Agents

```python
from integrations.autogen import (
    ATPGroupChat, ATPGroupChatManager,
    ATPAssistantAgent, ATPCodeReviewerAgent, ATPDataAnalystAgent
)

# Create specialized agents
developer = ATPAssistantAgent(name="Developer", atp_base_url="http://localhost:8000")
reviewer = ATPCodeReviewerAgent(name="Reviewer", atp_base_url="http://localhost:8000")
analyst = ATPDataAnalystAgent(name="Analyst", atp_base_url="http://localhost:8000")

# Create group chat
agents = [developer, reviewer, analyst]
group_chat = ATPGroupChat(
    agents=agents,
    max_round=10,
    speaker_selection_method="expertise_based"
)

# Create manager
manager = ATPGroupChatManager(
    groupchat=group_chat,
    atp_base_url="http://localhost:8000"
)

# Start group discussion
result = developer.initiate_chat(
    manager,
    message="Let's build a data processing pipeline with proper code review."
)
```

### Code Execution

```python
from integrations.autogen import ATPCodeExecutor, ATPAssistantAgent

# Create code executor
code_executor = ATPCodeExecutor(
    atp_base_url="http://localhost:8000",
    work_dir="my_project"
)

# Create agent with code execution
assistant = ATPAssistantAgent(
    name="Coder",
    atp_base_url="http://localhost:8000",
    code_execution_config=code_executor.create_execution_config()
)

# Request code execution
result = assistant.generate_reply([{
    "role": "user",
    "content": "Write Python code to analyze this dataset and create visualizations."
}])
```

### Function Calling

```python
from integrations.autogen import ATPFunctionRegistry, atp_function, ATPAssistantAgent

# Create function registry
registry = ATPFunctionRegistry()

# Register custom functions
@atp_function(
    registry,
    description="Calculate compound interest",
    parameter_descriptions={
        "principal": "Initial amount",
        "rate": "Annual interest rate (as decimal)",
        "time": "Time in years"
    }
)
def calculate_compound_interest(principal: float, rate: float, time: int) -> float:
    return principal * (1 + rate) ** time

# Create agent with functions
assistant = ATPAssistantAgent(
    name="FinancialAdvisor",
    atp_base_url="http://localhost:8000",
    function_registry=registry
)

# Agent can now call the function
result = await registry.call_function(
    "calculate_compound_interest",
    {"principal": 1000, "rate": 0.05, "time": 10}
)
```

## Agent Types

### ATPAssistantAgent
General-purpose assistant agent for automated responses.

```python
assistant = ATPAssistantAgent(
    name="Assistant",
    atp_base_url="http://localhost:8000",
    system_message="You are a helpful AI assistant specialized in software development.",
    temperature=0.7,
    max_tokens=1000
)
```

### ATPUserProxyAgent
User proxy agent for human interaction and coordination.

```python
user_proxy = ATPUserProxyAgent(
    name="User",
    atp_base_url="http://localhost:8000",
    human_input_mode="ALWAYS",  # or "NEVER", "TERMINATE"
    code_execution_config={"work_dir": "coding"}
)
```

### ATPCodeReviewerAgent
Specialized agent for code review and quality assurance.

```python
reviewer = ATPCodeReviewerAgent(
    name="CodeReviewer",
    atp_base_url="http://localhost:8000"
)
```

### ATPDataAnalystAgent
Specialized agent for data analysis and visualization.

```python
analyst = ATPDataAnalystAgent(
    name="DataAnalyst",
    atp_base_url="http://localhost:8000",
    code_execution_config={"work_dir": "data_analysis"}
)
```

## Group Chat Features

### Speaker Selection Methods

```python
# Automatic selection based on context
group_chat = ATPGroupChat(agents=agents, speaker_selection_method="auto")

# Round-robin selection
group_chat = ATPGroupChat(agents=agents, speaker_selection_method="round_robin")

# Random selection
group_chat = ATPGroupChat(agents=agents, speaker_selection_method="random")

# Expertise-based selection
group_chat = ATPGroupChat(agents=agents, speaker_selection_method="expertise_based")

# Load-balanced selection
group_chat = ATPGroupChat(agents=agents, speaker_selection_method="load_balanced")
```

### Conversation Management

```python
# Set conversation rules
manager.set_conversation_rules([
    "Keep responses under 200 words",
    "Always provide code examples",
    "Review code before implementation"
])

# Enforce turn limits
manager.enforce_turn_limit("Chatty_Agent", max_turns=3)

# Get conversation summary
summary = group_chat.get_conversation_summary()

# Export conversation
markdown_export = group_chat.export_conversation("markdown")
json_export = group_chat.export_conversation("json")
```

## Code Execution

### Supported Languages

- Python
- JavaScript
- Bash/Shell
- SQL
- R

### Execution Configuration

```python
code_executor = ATPCodeExecutor(
    atp_base_url="http://localhost:8000",
    work_dir="execution_workspace",
    timeout=30,  # seconds
    allowed_languages=["python", "javascript"],
    max_retries=3
)

# Get execution statistics
stats = code_executor.get_execution_stats()
print(f"Total executions: {stats['total_executions']}")
print(f"Success rates: {stats['success_rates']}")
```

### File Management

```python
# Save code to file
code_executor.save_code_to_file(
    code="print('Hello, World!')",
    filename="hello.py",
    language="python"
)

# Load code from file
code = code_executor.load_code_from_file("hello.py")

# List files
files = code_executor.list_files()
```

## Function Calling

### Built-in Functions

The integration includes built-in utility functions:

- **Math**: `calculate_sum`, `calculate_average`
- **String**: `count_words`, `to_uppercase`, `to_lowercase`
- **File**: `read_file`, `write_file`
- **Time**: `get_current_timestamp`, `format_timestamp`

```python
# Create registry with built-in functions
from integrations.autogen import create_builtin_function_registry

registry = create_builtin_function_registry()
```

### Custom Functions

```python
@atp_function(
    registry,
    name="weather_lookup",
    description="Get weather information for a city",
    parameter_descriptions={"city": "Name of the city"}
)
def get_weather(city: str) -> str:
    # Implementation here
    return f"Weather in {city}: Sunny, 25°C"

# Async functions are also supported
@atp_function(registry)
async def async_api_call(endpoint: str) -> dict:
    # Async implementation
    pass
```

### Function Validation

Functions are automatically validated against their schemas:

```python
# This will validate parameter types and required fields
result = await registry.call_function(
    "calculate_sum",
    {"numbers": [1, 2, 3, 4, 5]}  # Must be a list of numbers
)
```

## Advanced Features

### Streaming Responses

```python
assistant = ATPAssistantAgent(
    name="StreamingAssistant",
    atp_base_url="http://localhost:8000",
    streaming=True  # Enable streaming
)

# Responses will be streamed in real-time
```

### Error Handling and Retries

```python
agent = ATPAssistantAgent(
    name="RobustAgent",
    atp_base_url="http://localhost:8000",
    max_retries=5,
    retry_delay=2.0,
    request_timeout=120
)
```

### Conversation Memory

```python
# Get conversation history
history = agent.get_conversation_history(sender=other_agent)

# Clear conversation history
agent.clear_conversation_history()

# Update system message
agent.update_system_message("You are now a Python expert.")
```

### Metrics and Monitoring

```python
# Agent information
info = agent.get_agent_info()

# Group chat metrics
metrics = manager.get_manager_metrics()

# Code execution statistics
exec_stats = code_executor.get_execution_stats()

# Function call statistics
func_stats = registry.get_execution_stats()
```

## Configuration

### Environment Variables

```bash
# ATP Configuration
export ATP_BASE_URL="http://localhost:8000"
export ATP_API_KEY="your-api-key"

# Model Configuration
export ATP_DEFAULT_MODEL="gpt-4"
export ATP_DEFAULT_TEMPERATURE="0.7"
```

### Agent Configuration

```python
agent_config = {
    "atp_base_url": "http://localhost:8000",
    "atp_api_key": "your-api-key",
    "model": "gpt-4",
    "temperature": 0.7,
    "max_tokens": 1000,
    "request_timeout": 60,
    "max_retries": 3
}

agent = ATPAssistantAgent(name="ConfiguredAgent", **agent_config)
```

## Examples

### Software Development Team

```python
# Create a software development team
product_manager = ATPUserProxyAgent(name="PM", atp_base_url="http://localhost:8000")
architect = ATPAssistantAgent(name="Architect", atp_base_url="http://localhost:8000")
developer = ATPAssistantAgent(name="Developer", atp_base_url="http://localhost:8000")
tester = ATPAssistantAgent(name="Tester", atp_base_url="http://localhost:8000")
reviewer = ATPCodeReviewerAgent(name="Reviewer", atp_base_url="http://localhost:8000")

team = [product_manager, architect, developer, tester, reviewer]
group_chat = ATPGroupChat(agents=team, speaker_selection_method="expertise_based")
manager = ATPGroupChatManager(groupchat=group_chat, atp_base_url="http://localhost:8000")

# Start project discussion
result = product_manager.initiate_chat(
    manager,
    message="We need to build a new user authentication system. Let's discuss the requirements and implementation."
)
```

### Data Science Pipeline

```python
# Create data science team
data_engineer = ATPAssistantAgent(
    name="DataEngineer",
    system_message="You specialize in data pipelines and ETL processes."
)
data_scientist = ATPDataAnalystAgent(name="DataScientist")
ml_engineer = ATPAssistantAgent(
    name="MLEngineer", 
    system_message="You specialize in machine learning model deployment."
)

# Add data processing functions
@atp_function(registry, description="Load dataset from file")
def load_dataset(filename: str) -> str:
    # Implementation
    return f"Loaded dataset from {filename}"

@atp_function(registry, description="Train ML model")
def train_model(algorithm: str, features: list) -> dict:
    # Implementation
    return {"model_id": "model_123", "accuracy": 0.95}
```

### Customer Support System

```python
# Multi-agent customer support
support_agent = ATPAssistantAgent(
    name="SupportAgent",
    system_message="You provide friendly customer support."
)
technical_expert = ATPAssistantAgent(
    name="TechnicalExpert", 
    system_message="You handle complex technical issues."
)
escalation_manager = ATPUserProxyAgent(
    name="Manager",
    human_input_mode="ALWAYS"
)

# Route conversations based on complexity
```

## Best Practices

### Agent Design

1. **Clear Roles**: Give each agent a specific role and expertise area
2. **Appropriate System Messages**: Craft system messages that define behavior clearly
3. **Temperature Settings**: Use lower temperatures (0.3-0.5) for consistent behavior
4. **Token Limits**: Set appropriate max_tokens to control response length

### Group Chat Management

1. **Speaker Selection**: Choose appropriate speaker selection methods for your use case
2. **Turn Limits**: Prevent any single agent from dominating conversations
3. **Conversation Rules**: Set clear rules for productive discussions
4. **Monitoring**: Track conversation metrics and agent participation

### Code Execution Safety

1. **Sandboxing**: Always use ATP's sandboxed execution environment
2. **Timeouts**: Set reasonable execution timeouts
3. **Language Restrictions**: Limit allowed programming languages as needed
4. **File Management**: Organize code files in appropriate directories

### Function Calling

1. **Clear Descriptions**: Provide detailed function and parameter descriptions
2. **Input Validation**: Implement proper input validation in functions
3. **Error Handling**: Handle errors gracefully in custom functions
4. **Documentation**: Document function behavior and expected inputs/outputs

## Troubleshooting

### Common Issues

1. **Connection Errors**: Verify ATP services are running and accessible
2. **Authentication Errors**: Check API key configuration
3. **Agent Timeouts**: Increase timeout values for complex operations
4. **Memory Issues**: Clear conversation history periodically for long-running chats

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# This will show detailed request/response information
```

### Performance Optimization

```python
# Use connection pooling
agent = ATPAssistantAgent(
    name="OptimizedAgent",
    atp_base_url="http://localhost:8000",
    request_timeout=30,  # Shorter timeout for faster failure detection
    max_retries=2  # Fewer retries for faster response
)

# Batch operations when possible
results = await asyncio.gather(*[
    agent.generate_reply(msg) for msg in messages
])
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

Licensed under the Apache License, Version 2.0. See LICENSE file for details.