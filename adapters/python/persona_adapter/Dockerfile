
# Multi-stage build for optimized gRPC adapter
FROM python:3.11-alpine AS builder

# Install build dependencies
RUN apk add --no-cache \
    build-base \
    protobuf-dev \
    && pip install --no-cache-dir grpcio-tools

WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy proto files and generate gRPC code
COPY adapter.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. adapter.proto

# Production stage - using distroless for security
FROM gcr.io/distroless/python3-debian12:nonroot

# Copy installed packages and generated code
COPY --from=builder /root/.local /home/nonroot/.local
COPY --from=builder /app/*.py ./
COPY server.py .

# Set environment
ENV PATH=/home/nonroot/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

EXPOSE 7070

# Health check - using distroless compatible syntax
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["/usr/bin/python3", "-c", "import grpc; print('gRPC OK')"]

CMD ["python", "server.py"]
