# Anthropic Adapter for ATP

This adapter provides integration with Anthropic's Claude models for the ATP (Autonomous Task Processor) system. It supports all Claude model families including Claude-3 Haiku, Sonnet, and Opus.

## Features

- **Model Support**: Claude-3 Haiku, Sonnet, Opus, and Claude-3.5 models
- **Tool Use**: Full support for Anthropic's tool use capabilities
- **Vision**: Support for image inputs with Claude-3 models
- **Streaming**: Real-time streaming responses with proper backpressure handling
- **Cost Tracking**: Accurate token counting and cost estimation
- **Error Handling**: Robust error handling with fallback mechanisms
- **Health Monitoring**: Built-in health checks and monitoring

## Configuration

### Environment Variables

- `ANTHROPIC_API_KEY` (required): Your Anthropic API key

### Supported Models

The adapter supports the following Anthropic models with accurate pricing:

- `claude-3-haiku-20240307`: $0.00025/$0.00125 per 1K input/output tokens
- `claude-3-sonnet-20240229`: $0.003/$0.015 per 1K input/output tokens
- `claude-3-opus-20240229`: $0.015/$0.075 per 1K input/output tokens
- `claude-3-5-sonnet-20241022`: $0.003/$0.015 per 1K input/output tokens
- `claude-3-5-haiku-20241022`: $0.001/$0.005 per 1K input/output tokens
- `claude-2.1`: $0.008/$0.024 per 1K input/output tokens (legacy)
- `claude-2.0`: $0.008/$0.024 per 1K input/output tokens (legacy)
- `claude-instant-1.2`: $0.0008/$0.0024 per 1K input/output tokens (legacy)

## Usage

### Running the Adapter

```bash
# Install dependencies
pip install -r requirements.txt

# Set your Anthropic API key
export ANTHROPIC_API_KEY="your-api-key-here"

# Generate gRPC code
python -m grpc_tools.protoc --proto_path=. --python_out=. --grpc_python_out=. adapter.proto

# Run the adapter
python server.py
```

### Docker

```bash
# Build the image
docker build -t atp-anthropic-adapter .

# Run the container
docker run -e ANTHROPIC_API_KEY="your-api-key-here" -p 7070:7070 -p 8080:8080 atp-anthropic-adapter
```

## API Examples

### Basic Chat Completion

```json
{
  "model": "claude-3-haiku-20240307",
  "messages": [
    {"role": "user", "content": "Hello, how are you?"}
  ],
  "max_tokens": 150,
  "temperature": 0.7
}
```

### With System Prompt

```json
{
  "model": "claude-3-sonnet-20240229",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What's the weather like?"}
  ],
  "max_tokens": 200
}
```

### Tool Use

```json
{
  "model": "claude-3-opus-20240229",
  "messages": [
    {"role": "user", "content": "What's the weather in San Francisco?"}
  ],
  "tools": [
    {
      "name": "get_weather",
      "description": "Get current weather information",
      "input_schema": {
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
  ],
  "max_tokens": 300
}
```

### Vision (Image Analysis)

```json
{
  "model": "claude-3-sonnet-20240229",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "What's in this image?"},
        {
          "type": "image",
          "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": "base64-encoded-image-data"
          }
        }
      ]
    }
  ],
  "max_tokens": 300
}
```

## Architecture

The adapter implements the standard ATP adapter protocol with three main endpoints:

1. **Estimate**: Provides token and cost estimates before making API calls
2. **Stream**: Handles streaming chat completions with real-time token tracking
3. **Health**: Monitors adapter and Anthropic API health

### Message Format Conversion

The adapter automatically converts between OpenAI-style messages and Anthropic's format:

- **System messages** are extracted and passed as the `system` parameter
- **User/Assistant messages** are converted to Anthropic's alternating format
- **Multi-modal content** is properly formatted for vision capabilities

### Token Counting

Since Anthropic doesn't provide a public tokenizer, the adapter uses approximation:

- Roughly 4 characters per token (similar to GPT models)
- Adds safety buffers for accuracy
- Tracks actual usage from API responses when available

### Cost Calculation

Costs are calculated in USD micros (1 USD = 1,000,000 micros) for precision. The adapter:

- Uses up-to-date pricing for all supported models
- Separates input and output token costs
- Includes tool definition overhead
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
- Supports Anthropic's security best practices
- Input validation and sanitization

## Performance

- Async/await throughout for high concurrency
- Connection pooling and reuse
- Efficient token counting with approximation
- Minimal memory footprint
- Optimized for high-throughput scenarios

## Troubleshooting

### Common Issues

1. **API Key Not Set**
   ```
   Error: ANTHROPIC_API_KEY environment variable is required
   ```
   Solution: Set your Anthropic API key as an environment variable

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

4. **Message Format Issues**
   ```
   Error: Invalid message format
   ```
   Solution: Ensure messages alternate between user and assistant roles

### Debug Mode

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
python server.py
```

## Contributing

When contributing to the Anthropic adapter:

1. Maintain compatibility with the ATP adapter protocol
2. Add tests for new functionality
3. Update pricing information when Anthropic changes rates
4. Follow the existing code style and patterns
5. Update documentation for new features

## License

Copyright 2025 ATP Project Contributors. Licensed under the Apache License, Version 2.0.