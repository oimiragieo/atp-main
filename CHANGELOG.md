# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **MCP CLI Reference Client (GAP-132)**: Complete MCP CLI with WebSocket connectivity, tool invocation, and streaming support
  - Fixed streaming test with proper ConnectionClosedError handling
  - Added comprehensive test coverage (13/13 unit tests passing)
  - Integrated with existing MCP WebSocket endpoint
- **Containerization Optimization**: Migrated all Python services to optimized Docker images
  - Switched from python:3.11-slim to python:3.11-alpine for ~50% smaller images
  - Implemented proper multi-stage builds with separate builder/runtime stages
  - Added .dockerignore files to exclude unnecessary build context
  - Fixed Alpine package names and FROM keyword casing
  - Added health checks and proper non-root user setup
  - Verified all Dockerfiles build successfully
- **Documentation Enhancements**:
  - Added comprehensive module docstrings to core services (memory-gateway, adapters)
  - Enhanced function docstrings with Args, Returns, and Raises sections
  - Improved README with Installation, Usage, and Deployment sections
  - Added detailed environment variable documentation
  - Included scaling instructions and monitoring setup
- **Build Validation Tools**: Created comprehensive production build validation
  - Added Windows-specific compatibility handling for grpcio and uvloop
  - Implemented detailed debugging logging for build issues
  - Integrated Docker validation and linting checks
- **Performance Profiling**: Added performance profiling utilities
  - Created tools/performance_profiler.py with comprehensive profiling
  - Enhanced fragmentation benchmark with mock fallback
  - Added JSON report generation for performance metrics
- **Security Hardening**:
  - Standardized logging levels and error reporting
  - Added structured logging configuration
  - Enhanced exception handling with proper error logging
  - Completed dependency vulnerability scanning
- **Code Quality Improvements**:
  - Fixed all ruff linting violations
  - Added type checking with mypy (698 errors identified, prioritized for core modules)
  - Resolved threading and async compatibility issues
  - Fixed import organization and code formatting

### Changed
- **Docker Images**: All Python services now use Alpine Linux base images for better performance and security
- **Build Process**: Multi-stage Docker builds with optimized layer caching
- **Logging**: Migrated from print statements to structured logging across codebase
- **Error Handling**: Enhanced exception handling with proper logging and error codes

### Fixed
- **MCP CLI Streaming Test**: Corrected AsyncMock setup with proper ConnectionClosedError handling
- **Docker Build Issues**: Fixed Alpine package names (libgomp vs libgomp1) and FROM keyword casing
- **Threading Issues**: Resolved threading lock issues in adapter_metrics.py for async compatibility
- **Import Issues**: Fixed import organization and removed unused dependencies
- **Type Issues**: Addressed statistics.quantiles compatibility issues

### Security
- **Dependency Scan**: Completed vulnerability assessment
  - Python: 2 vulnerabilities in starlette (FastAPI dependency)
  - Node.js: 0 vulnerabilities in Next.js POC
  - Rust: 0 vulnerabilities in 304 crate dependencies
- **Container Security**: Implemented non-root user execution in all containers
- **Logging Security**: Removed hardcoded secrets and sensitive information from logs

### Performance
- **Image Size Reduction**: ~50% smaller Docker images with Alpine Linux
- **Build Optimization**: Multi-stage builds with proper layer caching
- **Fragmentation Benchmark**: 32 fragments processed in ~2.3ms
- **Memory Usage**: Optimized container memory footprint

### Testing
- **Test Coverage**: All MCP CLI tests passing (13/13)
- **Integration Tests**: Docker build validation for all services
- **Performance Tests**: Fragmentation and build performance benchmarks
- **Security Tests**: Dependency vulnerability scanning integrated

### Documentation
- **README Enhancement**: Added comprehensive installation, usage, and deployment guides
- **API Documentation**: Improved docstrings with proper formatting and examples
- **Environment Setup**: Detailed configuration and scaling instructions
- **Monitoring Setup**: Prometheus, Grafana, and metrics access documentation

## [0.1.0-alpha] - 2025-09-07

### Added
- Initial ATP router service with core functionality
- Memory gateway with audit logging and PII detection
- Basic adapter framework (persona and ollama adapters)
- Docker Compose setup for local development
- Prometheus metrics and Grafana dashboards
- Basic MCP WebSocket endpoint
- Core routing algorithms (UCB, Thompson sampling)
- Session management and lifecycle handling
- Basic security features (mTLS, OIDC placeholders)

### Changed
- Migrated from monolithic architecture to microservices
- Implemented async/await patterns throughout
- Added structured logging and observability

### Fixed
- Initial bug fixes and stability improvements
- Memory leaks in session handling
- Race conditions in adapter communication

### Security
- Basic authentication and authorization
- Input validation and sanitization
- Audit logging for compliance

### Performance
- Initial performance optimizations
- Memory usage improvements
- Concurrent request handling

### Testing
- Unit test framework setup
- Integration test suite
- Performance benchmarking tools

### Documentation
- Initial README and API documentation
- Architecture diagrams
- Deployment guides
