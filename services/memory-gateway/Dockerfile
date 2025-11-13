
# Multi-stage build for optimized FastAPI memory gateway
FROM python:3.11-alpine AS builder

# Install build dependencies
RUN apk add --no-cache build-base

WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage - using distroless for security
FROM gcr.io/distroless/python3-debian12:nonroot

# Copy installed packages from builder stage
COPY --from=builder /root/.local /home/nonroot/.local

# Copy SBOM generation tool and generate SBOM
COPY tools/sbom_poc.py /tmp/
COPY requirements.txt /tmp/
RUN ["/usr/bin/python3", "/tmp/sbom_poc.py", "/tmp", "/tmp/sbom.json"]

# Copy application code
COPY app.py .

# Set environment
ENV PATH=/home/nonroot/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

EXPOSE 8080

# Health check - using distroless compatible syntax
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["/usr/bin/python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')"]

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
