# ATP vLLM Adapter
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    nvidia-ml-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy protobuf files from parent directory
COPY ../openai_adapter/adapter.proto .
COPY ../openai_adapter/adapter_pb2.py .
COPY ../openai_adapter/adapter_pb2_grpc.py .

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 adapter && chown -R adapter:adapter /app
USER adapter

# Environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV GRPC_PORT=50051
ENV VLLM_HOST=localhost
ENV VLLM_PORT=8000
ENV VLLM_MAX_BATCH_SIZE=32

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Expose ports
EXPOSE 50051 8080

# Default command (gRPC server)
CMD ["python", "server.py"]