# ATP vLLM Adapter

High-performance adapter for vLLM (Very Large Language Model) inference server, providing optimized AI model interactions with advanced features for enterprise deployments.

## Features

### 🚀 High-Performance Inference
- **Batch Processing**: Intelligent batching for high-throughput scenarios
- **GPU Optimization**: Advanced GPU resource monitoring and allocation
- **Tensor Parallelism**: Support for large models across multiple GPUs
- **Streaming Responses**: Real-time response streaming with backpressure handling

### 📊 Resource Management
- **GPU Monitoring**: Real-time GPU utilization, memory, and temperature tracking
- **Optimal GPU Selection**: Automatic selection of best available GPU
- **Memory Management**: Intelligent memory allocation and cleanup
- **Performance Metrics**: Comprehensive performance and resource metrics

### 🔧 Enterprise Features
- **OpenAI Compatibility**: Compatible with OpenAI API format
- **Cost Tracking**: Accurate cost estimation and tracking
- **Health Monitoring**: Comprehensive health checks and diagnostics
- **Scalable Architecture**: Designed for high-throughput production workloads

## Supported Models

The adapter supports various open-source models through vLLM:

- **LLaMA 2**: 7B, 13B, 70B variants
- **Code Llama**: 7B, 13B, 34B variants  
- **Mistral**: 7B and Mixtral 8x7B
- **Vicuna**: 7B, 13B variants
- **Alpaca**: 7B variant
- **Custom Models**: Any model supported by vLLM

## Installation

### Prerequisites

1. **vLLM Server**: Running vLLM server instance
2. **NVIDIA GPUs**: For optimal performance (CPU fallback available)
3. **Python 3.11+**: Required for the adapter

### Docker Installation (Recommended)

```bash
# Build the adapter
docker build -t atp-vllm-adapter .

# Run with GPU support
docker run --gpus all -p 50051:50051 -p 8080:8080 \
  -e VLLM_HOST=your-vllm-server \
  -e VLLM_PORT=8000 \
  atp-vllm-adapter
```

### Manual Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export VLLM_HOST=localhost
export VLLM_PORT=8000
export GRPC_PORT=50051

# Run the adapter
python server.py
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VLLM_HOST` | `localhost` | vLLM server hostname |
| `VLLM_PORT` | `8000` | vLLM server port |
| `GRPC_PORT` | `50051` | gRPC server port |
| `VLLM_MAX_BATCH_SIZE` | `32` | Maximum batch size for processing |
| `GPU_MONITORING_INTERVAL` | `1.0` | GPU monitoring interval in seconds |

### vLLM Server Setup

The adapter requires a running vLLM server. Example vLLM server startup:

```bash
# Start vLLM server with LLaMA 2 7B
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-2-7b-chat-hf \
  --host 0.0.0.0 \
  --port 8000 \
  --tensor-parallel-size 1

# For larger models with multiple GPUs
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-2-70b-chat-hf \
  --host 0.0.0.0 \
  --port 8000 \
  --tensor-parallel-size 4
```

## Usage

### gRPC Interface

The adapter implements the standard ATP adapter gRPC interface:

```python
import grpc
import adapter_pb2
import adapter_pb2_grpc

# Connect to adapter
channel = grpc.insecure_channel('localhost:50051')
stub = adapter_pb2_grpc.AdapterStub(channel)

# Estimate request
estimate_req = adapter_pb2.EstimateRequest(
    prompt_json='{"prompt": "Hello, world!", "model": "llama-2-7b", "max_tokens": 100}'
)
estimate_resp = stub.Estimate(estimate_req)

# Stream request
stream_req = adapter_pb2.StreamRequest(
    prompt_json='{"prompt": "Tell me a story", "model": "llama-2-7b", "max_tokens": 500}'
)
for chunk in stub.Stream(stream_req):
    print(chunk.text, end='')
```

### HTTP Interface

For development and monitoring, the adapter also provides HTTP endpoints:

```bash
# Health check
curl http://localhost:8080/health

# GPU statistics
curl http://localhost:8080/gpu-stats

# Available models
curl http://localhost:8080/models
```

### Batch Processing

For high-throughput scenarios, enable batch processing:

```json
{
  "prompt": "Your prompt here",
  "model": "llama-2-7b",
  "max_tokens": 100,
  "use_batch": true
}
```

## Performance Optimization

### GPU Configuration

1. **Tensor Parallelism**: For large models, use multiple GPUs
   ```bash
   # 70B model across 4 GPUs
   --tensor-parallel-size 4
   ```

2. **Memory Optimization**: Adjust GPU memory fraction
   ```bash
   # Use 90% of GPU memory
   --gpu-memory-utilization 0.9
   ```

3. **Batch Size Tuning**: Optimize batch size for your hardware
   ```bash
   export VLLM_MAX_BATCH_SIZE=64  # Increase for more throughput
   ```

### Performance Monitoring

The adapter provides comprehensive performance metrics:

- **GPU Utilization**: Real-time GPU usage monitoring
- **Memory Usage**: GPU and system memory tracking
- **Throughput**: Requests per second and tokens per second
- **Latency**: Request processing time distribution
- **Batch Efficiency**: Batch utilization and processing time

## API Reference

### Prompt JSON Format

```json
{
  "prompt": "Your input prompt",
  "model": "llama-2-7b",
  "max_tokens": 512,
  "temperature": 0.7,
  "top_p": 0.9,
  "stop": ["</s>", "\n\n"],
  "use_batch": false
}
```

### Response Format

Streaming responses provide:
- `text`: Generated text chunk
- `is_final`: Whether this is the last chunk
- `error`: Error message if generation failed

### Health Check Response

```json
{
  "healthy": true,
  "details": {
    "vllm_server": "healthy",
    "vllm_host": "localhost:8000",
    "cpu_usage": "25.3%",
    "memory_usage": "45.2%",
    "gpu_count": 2,
    "batch_processor": "running",
    "gpu_monitor": "running",
    "gpu_0": {
      "name": "NVIDIA A100-SXM4-40GB",
      "memory_used": "15360MB",
      "memory_total": "40960MB",
      "utilization": "85.2%",
      "temperature": "65°C"
    }
  }
}
```

## Cost Estimation

The adapter provides cost estimates based on model size and compute requirements:

| Model | Input Cost (per 1K tokens) | Output Cost (per 1K tokens) |
|-------|----------------------------|------------------------------|
| LLaMA 2 7B | $0.0002 | $0.0004 |
| LLaMA 2 13B | $0.0004 | $0.0008 |
| LLaMA 2 70B | $0.002 | $0.004 |
| Mistral 7B | $0.00015 | $0.0003 |
| Mixtral 8x7B | $0.0006 | $0.0012 |

*Note: Costs are estimates based on compute requirements and may vary based on actual infrastructure costs.*

## Troubleshooting

### Common Issues

#### vLLM Server Connection Failed
```bash
# Check vLLM server status
curl http://localhost:8000/health

# Verify network connectivity
telnet localhost 8000
```

#### GPU Memory Issues
```bash
# Check GPU memory usage
nvidia-smi

# Reduce batch size
export VLLM_MAX_BATCH_SIZE=16
```

#### High Latency
```bash
# Check GPU utilization
curl http://localhost:8080/gpu-stats

# Monitor system resources
htop
```

### Debugging

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
python server.py
```

Check adapter health:
```bash
curl http://localhost:8080/health
```

Monitor GPU usage:
```bash
watch -n 1 nvidia-smi
```

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-mock

# Run tests
pytest test_adapter.py -v
```

### Building from Source

```bash
# Clone repository
git clone <repository-url>
cd adapters/python/vllm_adapter

# Install in development mode
pip install -e .

# Run adapter
python server.py
```

## Integration with ATP

The vLLM adapter integrates seamlessly with the ATP router service:

1. **Registration**: Adapter automatically registers with ATP router
2. **Load Balancing**: Router distributes requests across adapter instances
3. **Health Monitoring**: Router monitors adapter health and availability
4. **Cost Optimization**: Router uses cost estimates for optimal routing

## Security Considerations

- **Network Security**: Use TLS for production deployments
- **Access Control**: Implement proper authentication and authorization
- **Resource Limits**: Set appropriate resource limits to prevent abuse
- **Monitoring**: Monitor for unusual usage patterns

## Performance Benchmarks

Typical performance on NVIDIA A100:

| Model | Batch Size | Throughput (tokens/sec) | Latency (ms) |
|-------|------------|-------------------------|--------------|
| LLaMA 2 7B | 1 | 150 | 100 |
| LLaMA 2 7B | 32 | 3200 | 800 |
| LLaMA 2 13B | 1 | 100 | 150 |
| LLaMA 2 13B | 16 | 1200 | 1200 |
| LLaMA 2 70B | 1 | 25 | 600 |
| LLaMA 2 70B | 4 | 80 | 2000 |

## License

Licensed under the Apache License 2.0. See LICENSE file for details.