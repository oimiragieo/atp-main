# Cross-platform Makefile with Windows support
.PHONY: lint type format precommit coverage coverage-core test build validate clean help

# Detect OS and set appropriate commands
ifeq ($(OS),Windows_NT)
    PYTHON := python
    RM := del /Q
    RMDIR := rmdir /S /Q
    MKDIR := mkdir
    NULL := nul
else
    PYTHON := python3
    RM := rm -f
    RMDIR := rm -rf
    MKDIR := mkdir -p
    NULL := /dev/null
endif

# Default target
help:
	@echo "ATP System Build & Development Tools"
	@echo ""
	@echo "Available targets:"
	@echo "  lint       - Run ruff linter"
	@echo "  type       - Run mypy type checker"
	@echo "  format     - Format code with ruff"
	@echo "  precommit  - Run lint and type checks"
	@echo "  test       - Run test suite"
	@echo "  coverage   - Run tests with coverage"
	@echo "  build      - Build all components"
	@echo "  validate   - Run production build validation"
	@echo "  clean      - Clean build artifacts"
	@echo "  install    - Install development dependencies"
	@echo "  docker     - Build Docker images"

# Lint & Type targets
lint:
	$(PYTHON) -m ruff check .

type:
	$(PYTHON) -m mypy router_service tools memory-gateway || true

format:
	$(PYTHON) -m ruff format .

precommit: lint type

# Test targets
test:
	$(PYTHON) tests/test_adapters_health.py
	$(PYTHON) tests/test_memory_gateway.py
	$(PYTHON) tests/test_ws_end_to_end.py

coverage:
	$(PYTHON) -m pytest --cov=router_service --cov=memory-gateway --cov-report=term-missing --cov-fail-under=60

coverage-core:
	$(PYTHON) -m pytest -k "frame or service" --cov=router_service --cov-report=term-missing --cov-fail-under=60

# Build targets
build: validate
	@echo "Building all components..."
	$(PYTHON) tools/build_validator.py

validate:
	$(PYTHON) tools/build_validator.py

# Docker targets
docker:
	@echo "Building Docker images..."
	docker build -f memory-gateway/Dockerfile -t atp-memory-gateway .
	docker build -f adapters/python/persona_adapter/Dockerfile -t atp-persona-adapter .
	docker build -f adapters/python/ollama_adapter/Dockerfile -t atp-ollama-adapter .

docker-memory-gateway:
	docker build -f memory-gateway/Dockerfile -t atp-memory-gateway .

docker-persona-adapter:
	docker build -f adapters/python/persona_adapter/Dockerfile -t atp-persona-adapter .

docker-ollama-adapter:
	docker build -f adapters/python/ollama_adapter/Dockerfile -t atp-ollama-adapter .

# Development setup
install:
	$(PYTHON) -m pip install -r requirements_optimized.txt
	$(PYTHON) -m pip install -r requirements-dev.txt

# Cleanup
clean:
	@echo "Cleaning build artifacts..."
	-$(RMDIR) .build_cache
	-$(RMDIR) __pycache__
	-$(RMDIR) *.pyc
	-$(RMDIR) .pytest_cache
	-$(RMDIR) .mypy_cache
	-$(RMDIR) .ruff_cache
	-$(RM) requirements_temp.txt

# Rust build (if protoc is available)
rust-build:
	@echo "Building Rust router..."
	cd atp-router && cargo build --release

# Quick validation (skip slow operations)
quick-validate:
	$(PYTHON) -c "import tools.build_validator; v = tools.build_validator.BuildValidator(); print('✅ Quick validation passed' if v.validate()[0] else '❌ Validation failed')"
