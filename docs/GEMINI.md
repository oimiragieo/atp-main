# ATP/AGP Proof of Concept Bundle

## Project Overview

This project is a sophisticated routing and management layer for large language models (LLMs), referred to as the "ATP/AGP Proof of Concept Bundle". It is designed to provide intelligent routing, model selection, and a unified interface for interacting with various LLM adapters.

**Core Components:**

*   **ATP Router (`atp-router`):** A high-performance router written in Rust. It manages incoming requests, selects the optimal LLM based on various factors, and communicates with the appropriate adapter. It includes features like weighted fair scheduling, bandit model selection for adaptive routing, and OpenTelemetry for tracing.
*   **Memory Gateway (`memory-gateway`):** A FastAPI-based service that provides a key-value store with search capabilities, likely for caching or session management.
*   **Adapters:** Python-based components that act as bridges to different LLMs (e.g., Ollama, custom "Persona" models). They advertise their capabilities to the router, allowing for dynamic discovery.
*   **SDKs:** Software Development Kits in Python and Go are available to facilitate interaction with the ATP/AGP ecosystem.
*   **Observability:** The project is integrated with Prometheus for metrics collection and Grafana for visualization.
*   **Model Context Protocol (MCP):** A WebSocket-based protocol for discovering and invoking tools, including the `route.complete` tool for adaptive completion.

**Technologies:**

*   **Backend:** Rust, Python (FastAPI)
*   **Frontend:** Next.js (for a proof-of-concept admin dashboard)
*   **Containerization:** Docker, Docker Compose, and Kubernetes are supported for deployment.
*   **Observability:** Prometheus, Grafana, and OpenTelemetry.
*   **Databases:** Redis is mentioned as a potential backend for state management.

## Building and Running

**Primary Method (Docker Compose):**

The recommended way to build and run the entire application stack is using Docker Compose.

1.  **Build the containers:**
    ```bash
    docker compose build
    ```
2.  **Start the services in detached mode:**
    ```bash
    docker compose up -d
    ```

**Development Setup:**

For development, you can set up the components individually.

1.  **Install Python dependencies:**
    ```bash
    pip install -r requirements-dev.txt
    ```
2.  **Build the Rust-based router:**
    ```bash
    cd atp-router
    cargo build
    ```
3.  **Start services individually using Docker Compose:**
    ```bash
    docker compose up memory-gateway -d
    docker compose up router -d
    ```

**Testing:**

Several scripts are provided to verify the health and functionality of the system.

*   **Health Check:**
    ```bash
    python client/health_check.py
    ```
*   **Memory Gateway Test:**
    ```bash
    python client/memory_put_get.py
    ```
*   **Tracing Tests:**
    ```bash
    pytest -q tests/test_tracing_spans.py
    ```

## Development Conventions

*   **Configuration:** The application is configured primarily through environment variables. Key variables include `ROUTER_RPS_LIMIT`, `MEMORY_QUOTA_MB`, and `OLLAMA_BASE_URL`.
*   **API:** The system exposes a WebSocket-based API for adapter communication and the Model Context Protocol (MCP). HTTP endpoints are also available for health checks and metrics.
*   **Documentation:** The `docs/` directory contains extensive design documents and specifications for various aspects of the system.
*   **Modularity:** The project is architected in a modular fashion, with clear separation of concerns between the router, memory gateway, and adapters. This allows for independent development and scaling of components.
*   **Code Style:** While not explicitly stated, the presence of `ruff.toml` and `mypy.ini` suggests that the Python code is expected to adhere to specific linting and typing standards.
