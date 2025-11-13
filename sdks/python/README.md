# ATP Python SDK

The official Python SDK for the ATP (AI Traffic Platform) - an enterprise-grade AI routing and management platform.

## Features

- **Async/Sync Support**: Both synchronous and asynchronous client implementations
- **Streaming Responses**: Real-time streaming for chat completions and other endpoints
- **Enterprise Authentication**: JWT tokens, API keys, and service account authentication
- **Cost Management**: Built-in cost tracking and budget management
- **Multi-Provider**: Seamless routing across multiple AI providers
- **Type Safety**: Full type hints and Pydantic models for all API interactions
- **Retry Logic**: Intelligent retry with exponential backoff
- **Caching**: Optional response caching for improved performance

## Installation

```bash
pip install atp-sdk
```

For development:
```bash
pip install atp-sdk[dev]
```

## Quick Start

### Basic Usage

```python
from atp_sdk import ATPClient, ChatMessage

# Initialize client
client = ATPClient(api_key="your-api-key")

# Create a chat completion
messages = [
    ChatMessage(role="user", content="Hello, how are you?")
]

response = client.chat_completion(messages=messages)
print(response.choices[0].message.content)
```

### Async Usage

```python
import asyncio
from atp_sdk import AsyncATPClient, ChatMessage

async def main():
    async with AsyncATPClient(api_key="your-api-key") as client:
        messages = [
            ChatMessage(role="user", content="Hello, how are you?")
        ]
        
        response = await client.chat_completion(messages=messages)
        print(response.choices[0].message.content)

asyncio.run(main())
```

### Streaming Responses

```python
from atp_sdk import ATPClient, ChatMessage

client = ATPClient(api_key="your-api-key")

messages = [
    ChatMessage(role="user", content="Tell me a story")
]

# Stream the response
for chunk in client.chat_completion(messages=messages, stream=True):
    for choice in chunk.choices:
        if choice.delta.content:
            print(choice.delta.content, end="", flush=True)
```

### Configuration

```python
from atp_sdk import ATPClient, ATPConfig

# Create custom configuration
config = ATPConfig(
    api_key="your-api-key",
    base_url="https://api.atp.company.com",
    tenant_id="your-tenant-id",
    project_id="your-project-id",
    timeout=60.0,
    max_retries=5,
    quality_preference="balanced"  # speed, balanced, quality
)

client = ATPClient(config=config)
```

### Environment Variables

The SDK automatically loads configuration from environment variables:

```bash
export ATP_API_KEY="your-api-key"
export ATP_BASE_URL="https://api.atp.company.com"
export ATP_TENANT_ID="your-tenant-id"
export ATP_PROJECT_ID="your-project-id"
export ATP_TIMEOUT="30.0"
export ATP_MAX_RETRIES="3"
export ATP_QUALITY_PREFERENCE="balanced"
```

## Advanced Features

### Cost Management

```python
# Get cost information
cost_info = client.get_cost_info(
    start_date="2024-01-01",
    end_date="2024-01-31"
)

print(f"Total cost: ${cost_info.total_cost}")
print(f"Breakdown: {cost_info.breakdown}")

# Set cost limits for requests
response = client.chat_completion(
    messages=messages,
    cost_limit=0.10  # Maximum $0.10 for this request
)
```

### Model and Provider Management

```python
# List available models
models = client.list_models()
for model in models:
    print(f"{model.name}: {model.provider} - ${model.pricing.input_cost_per_token}/token")

# Get specific model info
model_info = client.get_model_info("gpt-4")
print(f"Context length: {model_info.context_length}")

# List providers
providers = client.list_providers()
for provider in providers:
    print(f"{provider.name}: {provider.status.available}")
```

### Policy Management

```python
# List policies
policies = client.list_policies()

# Create a new policy
policy_data = {
    "name": "Cost Control Policy",
    "rules": [
        {
            "condition": "cost > 1.0",
            "action": "block",
            "parameters": {"message": "Cost limit exceeded"}
        }
    ]
}

policy = client.create_policy(policy_data)
print(f"Created policy: {policy.id}")
```

### Service Account Authentication

```python
from atp_sdk import ATPClient
from atp_sdk.auth import ServiceAccountAuth

# Use service account for server-to-server authentication
auth = ServiceAccountAuth(
    service_account_key="/path/to/service-account.json",
    scopes=["atp:read", "atp:write"]
)

client = ATPClient(auth_manager=auth)
```

## Error Handling

```python
from atp_sdk import ATPClient, ChatMessage
from atp_sdk.exceptions import (
    AuthenticationError,
    RateLimitError,
    ModelNotFoundError,
    InsufficientCreditsError
)

client = ATPClient(api_key="your-api-key")

try:
    response = client.chat_completion(messages=messages)
except AuthenticationError:
    print("Invalid API key")
except RateLimitError as e:
    print(f"Rate limited. Retry after: {e.retry_after} seconds")
except ModelNotFoundError:
    print("Requested model not available")
except InsufficientCreditsError as e:
    print(f"Insufficient credits. Required: {e.required_credits}")
```

## Examples

See the `examples/` directory for more comprehensive examples:

- [Basic Chat](examples/basic_chat.py)
- [Streaming Chat](examples/streaming_chat.py)
- [Async Operations](examples/async_example.py)
- [Cost Management](examples/cost_management.py)
- [Multi-Provider Routing](examples/multi_provider.py)
- [Enterprise Features](examples/enterprise_features.py)

## Development

### Setup Development Environment

```bash
git clone https://github.com/atp-project/python-sdk.git
cd python-sdk
pip install -e ".[dev]"
pre-commit install
```

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black atp_sdk/
isort atp_sdk/
flake8 atp_sdk/
mypy atp_sdk/
```

## Documentation

- [API Documentation](https://docs.atp.company.com/api)
- [SDK Documentation](https://docs.atp.company.com/sdk/python)
- [Examples](https://github.com/atp-project/python-sdk/tree/main/examples)

## Support

- [GitHub Issues](https://github.com/atp-project/python-sdk/issues)
- [Documentation](https://docs.atp.company.com)
- [Community Forum](https://community.atp.company.com)
- Email: support@atp.company.com

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a list of changes and version history.