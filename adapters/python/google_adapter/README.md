# Google AI Adapter for ATP

This adapter provides integration with Google's Generative AI (Gemini) models for the ATP (Autonomous Task Processor) system. It supports all Gemini model families including Gemini Pro, Flash, and Ultra.

## Features

- **Model Support**: Gemini 1.5 Pro, Flash, and legacy Gemini 1.0 models
- **Multi-modal**: Full support for text, vision, and audio inputs
- **Function Calling**: Support for Google AI's function calling capabilities
- **Streaming**: Real-time streaming responses with proper backpressure handling
- **Cost Tracking**: Accurate token counting and cost estimation
- **Error Handling**: Robust error handling with fallback mechanisms
- **Health Monitoring**: Built-in health checks and monitoring

## Configuration

### Environment Variables

- `GOOGLE_API_KEY` (required): Your Google AI API key

### Supported Models

The adapter supports the following Google AI models with accurate pricing:

- `gemini-1.5-pro`: $0.0035/$0.0105 per 1K input/output tokens
- `gemini-1.5-flash`: $0.000075/$0.0003 per 1K input/output tokens
- `gemini-1.0-pro`: $0.0005/$0.0015 per 1K input/output tokens
- `gemini-1.0-pro-vision`: $0.00025/$0.0005 per 1K input/output tokens
- `gemini-pro`: $0.0005/$0.0015 per 1K input/output tokens (alias)
- `gemini-pro-vision`: $0.00025/$0.0005 per 1K input/output tokens (alias)
- `text-embedding-004`: $0.00001 per 1K tokens
- `embedding-001`: $0.00001 per 1K tokens (legacy)

## Usage

### Running the Adapter

```bash
# Install dependencies
pip install -r requirements.txt

# Set your Google AI API key
export GOOGLE_API_KEY="your-api-key-here"

# Generate gRPC code
python -m grpc_tools.protoc --proto_path=. --python_out=. --grpc_python_out=. adapter.proto

# Run the adapter
python server.py
```

### Docker

```bash
# Build the image
docker build -t atp-google-adapter .

# Run the container
docker run -e GOOGLE_API_KEY="your-api-key-here" -p 7070:7070 -p 8080:8080 atp-google-adapter
```

## API Examples

### Basic Chat Completion

```json
{
  "model": "gemini-1.5-flash",
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
  "model": "gemini-1.5-pro",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What's the weather like?"}
  ],
  "max_tokens": 200
}
```

### Multi-modal (Vision)

```json
{
  "model": "gemini-1.5-pro",
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

### Function Calling

```json
{
  "model": "gemini-1.5-pro",
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
  ],
  "max_tokens": 300
}
```

### Multi-turn Conversation

```json
{
  "model": "gemini-1.5-flash",
  "messages": [
    {"role": "user", "content": "Hello!"},
    {"role": "assistant", "content": "Hi there! How can I help you today?"},
    {"role": "user", "content": "Can you explain quantum computing?"}
  ],
  "max_tokens": 500
}
```

## Architecture

The adapter implements the standard ATP adapter protocol with three main endpoints:

1. **Estimate**: Provides token and cost estimates before making API calls
2. **Stream**: Handles streaming chat completions with real-time token tracking
3. **Health**: Monitors adapter and Google AI API health

### Message Format Conversion

The adapter automatically converts between OpenAI-style messages and Google AI's format:

- **System messages** are prepended to the first user message
- **User/Assistant messages** are converted to Google's `user`/`model` roles
- **Multi-modal content** is converted to Google's `parts` format
- **Images** are handled as `inline_data` with proper MIME types

### Token Counting

Since Google AI doesn't provide a public tokenizer for all models, the adapter uses approximation:

- Roughly 4 characters per token (similar to other models)
- Adds safety buffers for accuracy
- Tracks actual usage from API responses when available

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
- Supports Google AI's security best practices
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
   Error: GOOGLE_API_KEY environment variable is required
   ```
   Solution: Set your Google AI API key as an environment variable

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

4. **Image Format Issues**
   ```
   Error: Invalid image format
   ```
   Solution: Ensure images are properly base64 encoded with correct MIME types

### Debug Mode

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
python server.py
```

## Contributing

When contributing to the Google AI adapter:

1. Maintain compatibility with the ATP adapter protocol
2. Add tests for new functionality
3. Update pricing information when Google changes rates
4. Follow the existing code style and patterns
5. Update documentation for new features

## License

Copyright 2025 ATP Project Contributors. Licensed under the Apache License, Version 2.0.