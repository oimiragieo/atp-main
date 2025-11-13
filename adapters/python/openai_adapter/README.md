# OpenAI Adapter for ATP

This adapter provides integration with OpenAI's API for the ATP (Autonomous Task Processor) system. It supports all major OpenAI models including GPT-4, GPT-3.5, and embedding models.

## Features

- **Model Support**: GPT-4, GPT-4 Turbo, GPT-3.5 Turbo, and embedding models
- **Function Calling**: Full support for OpenAI's function calling and tools
- **Vision Models**: Support for GPT-4V with image inputs
- **Streaming**: Real-time streaming responses with proper backpressure handling
- **Cost Tracking**: Accurate token counting and cost estimation using tiktoken
- **Error Handling**: Robust error handling with fallback mechanisms
- **Health Monitoring**: Built-in health checks and monitoring

## Configuration

### Environment Variables

- `OPENAI_API_KEY` (required): Your OpenAI API key

### Supported Models

The adapter supports the following OpenAI models with accurate pricing:

- `gpt-4`: $0.03/$0.06 per 1K input/output tokens
- `gpt-4-32k`: $0.06/$0.12 per 1K input/output tokens  
- `gpt-4-turbo`: $0.01/$0.03 per 1K input/output tokens
- `gpt-4-vision-preview`: $0.01/$0.03 per 1K input/output tokens
- `gpt-3.5-turbo`: $0.0005/$0.0015 per 1K input/output tokens
- `gpt-3.5-turbo-16k`: $0.003/$0.004 per 1K input/output tokens
- `text-embedding-ada-002`: $0.0001 per 1K tokens
- `text-embedding-3-small`: $0.00002 per 1K tokens
- `text-embedding-3-large`: $0.00013 per 1K tokens

## Usage

### Running the Adapter

```bash
# Install dependencies
pip install -r requirements.txt

# Set your OpenAI API key
export OPENAI_API_KEY="your-api-key-here"

# Generate gRPC code
python -m grpc_tools.protoc --proto_path=. --python_out=. --grpc_python_out=. adapter.proto

# Run the adapter
python server.py
```

### Docker

```bash
# Build the image
docker build -t atp-openai-adapter .

# Run the container
docker run -e OPENAI_API_KEY="your-api-key-here" -p 7070:7070 -p 8080:8080 atp-openai-adapter
```

### Testing

```bash
# Run unit tests
python test_adapter.py

# Run with pytest for more detailed output
pytest test_adapter.py -v

# Integration tests (requires OPENAI_API_KEY)
OPENAI_API_KEY="your-key" python test_adapter.py
```

## API Examples

### Basic Chat Completion

```json
{
  "model": "gpt-3.5-turbo",
  "messages": [
    {"role": "user", "content": "Hello, how are you?"}
  ],
  "temperature": 0.7,
  "max_tokens": 150
}
```

### Function Calling

```json
{
  "model": "gpt-4",
  "messages": [
    {"role": "user", "content": "What's the weather in San Francisco?"}
  ],
  "functions": [
    {
      "name": "get_weather",
      "description": "Get current weather information",
      "parameters": {
        "type": "object",
        "properties": {
          "location": {
            "type": "string",
            "description": "The city and state, e.g. San Francisco, CA"
          }
        },
        "required": ["location"]
      }
    }
  ]
}
```

### Vision Model (GPT-4V)

```json
{
  "model": "gpt-4-vision-preview",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "What's in this image?"},
        {
          "type": "image_url",
          "image_url": {
            "url": "https://example.com/image.jpg"
          }
        }
      ]
    }
  ],
  "max_tokens": 300
}
```

### Tools (New Function Calling Format)

```json
{
  "model": "gpt-4",
  "messages": [
    {"role": "user", "content": "Calculate 15 * 7"}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "calculate",
        "description": "Perform mathematical calculations",
        "parameters": {
          "type": "object",
          "properties": {
            "expression": {
              "type": "string",
              "description": "Mathematical expression to evaluate"
            }
          },
          "required": ["expression"]
        }
      }
    }
  ]
}
```

## Architecture

The adapter implements the standard ATP adapter protocol with three main endpoints:

1. **Estimate**: Provides token and cost estimates before making API calls
2. **Stream**: Handles streaming chat completions with real-time token tracking
3. **Health**: Monitors adapter and OpenAI API health

### Token Counting

The adapter uses OpenAI's `tiktoken` library for accurate token counting, which matches OpenAI's billing exactly. It handles:

- Text content in messages
- Function/tool definitions
- Multi-modal content (images in vision models)
- System messages and conversation history

### Cost Calculation

Costs are calculated in USD micros (1 USD = 1,000,000 micros) for precision. The adapter:

- Uses up-to-date pricing for all supported models
- Separates input and output token costs
- Includes function definition overhead
- Provides detailed cost breakdowns

### Error Handling

The adapter includes comprehensive error handling:

- API key validation
- Network error recovery
- Rate limit handling
- Fallback token estimation
- Graceful degradation

## Monitoring

### Health Endpoints

- **gRPC Health**: `Health()` method tests API connectivity
- **HTTP Health**: `GET /health` provides quick status check

### Metrics

The adapter tracks:

- Response times (P95 latency)
- Error rates
- Token usage
- Cost attribution
- Model usage patterns

## Integration with ATP

The adapter integrates seamlessly with the ATP system:

- **Adapter Registry**: Automatically registers supported models and capabilities
- **Cost Optimization**: Provides accurate cost data for intelligent routing
- **Pricing Monitor**: Integrates with real-time pricing updates
- **Analytics**: Contributes usage data for business intelligence

## Security

- API keys are handled securely through environment variables
- No sensitive data is logged
- Supports OpenAI's security best practices
- Input validation and sanitization

## Performance

- Async/await throughout for high concurrency
- Connection pooling and reuse
- Efficient token counting with caching
- Minimal memory footprint
- Optimized for high-throughput scenarios

## Troubleshooting

### Common Issues

1. **API Key Not Set**
   ```
   Error: OPENAI_API_KEY environment variable is required
   ```
   Solution: Set your OpenAI API key as an environment variable

2. **Rate Limiting**
   ```
   Error: Rate limit exceeded
   ```
   Solution: The adapter handles rate limits automatically with exponential backoff

3. **Model Not Found**
   ```
   Error: Model not found
   ```
   Solution: Check that you're using a supported model name

4. **Token Counting Issues**
   ```
   Warning: Failed to count tokens for model
   ```
   Solution: The adapter will fall back to estimation, but check model name spelling

### Debug Mode

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
python server.py
```

## Contributing

When contributing to the OpenAI adapter:

1. Maintain compatibility with the ATP adapter protocol
2. Add tests for new functionality
3. Update pricing information when OpenAI changes rates
4. Follow the existing code style and patterns
5. Update documentation for new features

## License

Copyright 2025 ATP Project Contributors. Licensed under the Apache License, Version 2.0.