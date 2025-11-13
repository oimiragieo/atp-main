# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Enhanced Test Fixtures and Utilities
Comprehensive test fixtures for enterprise components testing.
"""

import asyncio
import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import aiohttp
import asyncpg
import pytest
import redis.asyncio as redis

# Testcontainers imports
try:
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    TESTCONTAINERS_AVAILABLE = True
except ImportError:
    TESTCONTAINERS_AVAILABLE = False


class TestDataFactory:
    """Factory for generating test data."""

    @staticmethod
    def create_chat_request(
        model: str = "gpt-4",
        messages: list[dict[str, str]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 100,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Create a chat completion request."""
        if messages is None:
            messages = [{"role": "user", "content": "Hello, how are you?"}]

        return {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    @staticmethod
    def create_provider_config(
        name: str = "test-provider",
        provider_type: str = "openai",
        endpoint: str = "https://api.test.com",
        api_key: str = "test-key",
        models: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a provider configuration."""
        if models is None:
            models = ["gpt-4", "gpt-3.5-turbo"]

        return {
            "name": name,
            "type": provider_type,
            "endpoint": endpoint,
            "api_key": api_key,
            "models": models,
            "priority": 100,
            "status": "active",
        }

    @staticmethod
    def create_user_data(
        user_id: str = "test-user",
        email: str = "test@example.com",
        role: str = "user",
        permissions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create user data."""
        if permissions is None:
            permissions = ["read", "write"]

        return {
            "user_id": user_id,
            "email": email,
            "role": role,
            "permissions": permissions,
            "created_at": time.time(),
            "active": True,
        }

    @staticmethod
    def create_metrics_data(
        timestamp: float | None = None,
        requests_count: int = 100,
        error_count: int = 5,
        avg_latency: float = 0.5,
        cost: float = 1.50,
    ) -> dict[str, Any]:
        """Create metrics data."""
        if timestamp is None:
            timestamp = time.time()

        return {
            "timestamp": timestamp,
            "requests_count": requests_count,
            "error_count": error_count,
            "success_rate": (requests_count - error_count) / requests_count,
            "avg_latency": avg_latency,
            "p95_latency": avg_latency * 1.5,
            "total_cost": cost,
            "cost_per_request": cost / requests_count,
        }


class DatabaseFixtures:
    """Database-related test fixtures."""

    @pytest.fixture
    async def postgres_container(self):
        """PostgreSQL container fixture."""
        if not TESTCONTAINERS_AVAILABLE:
            pytest.skip("Testcontainers not available")

        with PostgresContainer("postgres:15-alpine") as postgres:
            # Wait for container to be ready
            postgres.get_connection_url()
            yield postgres

    @pytest.fixture
    async def postgres_connection(self, postgres_container):
        """PostgreSQL connection fixture."""
        connection_url = postgres_container.get_connection_url()
        conn = await asyncpg.connect(connection_url)

        # Set up test schema
        await self._setup_test_schema(conn)

        yield conn

        # Cleanup
        await conn.close()

    @pytest.fixture
    async def redis_container(self):
        """Redis container fixture."""
        if not TESTCONTAINERS_AVAILABLE:
            pytest.skip("Testcontainers not available")

        with RedisContainer("redis:7-alpine") as redis_container:
            yield redis_container

    @pytest.fixture
    async def redis_connection(self, redis_container):
        """Redis connection fixture."""
        redis_url = redis_container.get_connection_url()
        redis_client = redis.from_url(redis_url)

        # Test connection
        await redis_client.ping()

        yield redis_client

        # Cleanup
        await redis_client.flushall()
        await redis_client.close()

    async def _setup_test_schema(self, conn):
        """Set up test database schema."""
        schema_sql = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) UNIQUE NOT NULL,
            email VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL,
            permissions JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            active BOOLEAN DEFAULT TRUE
        );
        
        CREATE TABLE IF NOT EXISTS providers (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) UNIQUE NOT NULL,
            type VARCHAR(50) NOT NULL,
            endpoint VARCHAR(500),
            api_key VARCHAR(500),
            models JSONB,
            priority INTEGER DEFAULT 100,
            status VARCHAR(20) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT NOW()
        );
        
        CREATE TABLE IF NOT EXISTS requests (
            id SERIAL PRIMARY KEY,
            request_id VARCHAR(255) UNIQUE NOT NULL,
            user_id VARCHAR(255),
            model VARCHAR(100),
            provider VARCHAR(100),
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            cost DECIMAL(10, 6),
            latency DECIMAL(8, 3),
            status VARCHAR(20),
            created_at TIMESTAMP DEFAULT NOW()
        );
        
        CREATE TABLE IF NOT EXISTS metrics (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            metric_name VARCHAR(100) NOT NULL,
            metric_value DECIMAL(15, 6),
            labels JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        );
        """

        await conn.execute(schema_sql)


class MockFixtures:
    """Mock-related test fixtures."""

    @pytest.fixture
    def mock_openai_client(self):
        """Mock OpenAI client."""
        mock_client = Mock()
        mock_client.chat = Mock()
        mock_client.chat.completions = Mock()

        # Mock successful response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Hello! I'm doing well, thank you for asking."))]
        mock_response.usage = Mock(prompt_tokens=10, completion_tokens=15, total_tokens=25)

        mock_client.chat.completions.create.return_value = mock_response

        return mock_client

    @pytest.fixture
    def mock_anthropic_client(self):
        """Mock Anthropic client."""
        mock_client = Mock()
        mock_client.messages = Mock()

        # Mock successful response
        mock_response = Mock()
        mock_response.content = [Mock(text="Hello! I'm Claude, and I'm doing well. How can I help you today?")]
        mock_response.usage = Mock(input_tokens=10, output_tokens=18, total_tokens=28)

        mock_client.messages.create.return_value = mock_response

        return mock_client

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client."""
        mock_client = AsyncMock()
        mock_client.ping.return_value = True
        mock_client.get.return_value = None
        mock_client.set.return_value = True
        mock_client.delete.return_value = 1
        mock_client.exists.return_value = False
        mock_client.expire.return_value = True

        return mock_client

    @pytest.fixture
    def mock_database_connection(self):
        """Mock database connection."""
        mock_conn = AsyncMock()
        mock_conn.execute.return_value = "INSERT 0 1"
        mock_conn.fetch.return_value = []
        mock_conn.fetchrow.return_value = None
        mock_conn.fetchval.return_value = None

        return mock_conn


class HTTPFixtures:
    """HTTP-related test fixtures."""

    @pytest.fixture
    async def http_session(self):
        """HTTP session fixture."""
        async with aiohttp.ClientSession() as session:
            yield session

    @pytest.fixture
    def mock_http_responses(self):
        """Mock HTTP responses for testing."""
        responses = {
            "openai_chat": {
                "status": 200,
                "json": {
                    "choices": [{"message": {"role": "assistant", "content": "Hello! How can I help you today?"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22},
                },
            },
            "anthropic_chat": {
                "status": 200,
                "json": {
                    "content": [{"type": "text", "text": "Hello! I'm Claude. How can I assist you?"}],
                    "usage": {"input_tokens": 10, "output_tokens": 14, "total_tokens": 24},
                },
            },
            "error_response": {
                "status": 500,
                "json": {"error": {"message": "Internal server error", "type": "server_error"}},
            },
            "rate_limit_response": {
                "status": 429,
                "json": {"error": {"message": "Rate limit exceeded", "type": "rate_limit_error"}},
            },
        }

        return responses


class FileSystemFixtures:
    """File system-related test fixtures."""

    @pytest.fixture
    def temp_directory(self):
        """Temporary directory fixture."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def config_file(self, temp_directory):
        """Configuration file fixture."""
        config_data = {
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "test_db",
                "username": "test_user",
                "password": "test_pass",
            },
            "redis": {"host": "localhost", "port": 6379, "db": 0},
            "providers": {
                "openai": {"api_key": "test-openai-key", "endpoint": "https://api.openai.com/v1"},
                "anthropic": {"api_key": "test-anthropic-key", "endpoint": "https://api.anthropic.com/v1"},
            },
        }

        config_file = temp_directory / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f, indent=2)

        return config_file

    @pytest.fixture
    def log_file(self, temp_directory):
        """Log file fixture."""
        log_file = temp_directory / "test.log"
        log_file.touch()
        return log_file


class AsyncFixtures:
    """Async-related test fixtures."""

    @pytest.fixture
    def event_loop(self):
        """Event loop fixture."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    @pytest.fixture
    async def async_context_manager(self):
        """Async context manager fixture."""

        class AsyncContextManager:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        yield AsyncContextManager()


class PerformanceFixtures:
    """Performance testing fixtures."""

    @pytest.fixture
    def performance_monitor(self):
        """Performance monitoring fixture."""

        class PerformanceMonitor:
            def __init__(self):
                self.start_time = None
                self.end_time = None
                self.memory_usage = []
                self.cpu_usage = []

            def start(self):
                self.start_time = time.time()

            def stop(self):
                self.end_time = time.time()

            @property
            def duration(self):
                if self.start_time and self.end_time:
                    return self.end_time - self.start_time
                return None

            def record_memory(self, usage):
                self.memory_usage.append(usage)

            def record_cpu(self, usage):
                self.cpu_usage.append(usage)

        return PerformanceMonitor()

    @pytest.fixture
    def load_generator(self):
        """Load generation fixture."""

        class LoadGenerator:
            def __init__(self):
                self.requests_sent = 0
                self.responses_received = 0
                self.errors = []

            async def generate_load(self, target_rps: int, duration: int):
                """Generate load at target RPS for specified duration."""
                interval = 1.0 / target_rps
                end_time = time.time() + duration

                while time.time() < end_time:
                    try:
                        # Simulate request
                        await asyncio.sleep(0.01)  # Simulate processing time
                        self.requests_sent += 1
                        self.responses_received += 1

                        await asyncio.sleep(interval)
                    except Exception as e:
                        self.errors.append(str(e))

            @property
            def success_rate(self):
                if self.requests_sent == 0:
                    return 0
                return self.responses_received / self.requests_sent

        return LoadGenerator()


class SecurityFixtures:
    """Security testing fixtures."""

    @pytest.fixture
    def security_scanner(self):
        """Security scanning fixture."""

        class SecurityScanner:
            def __init__(self):
                self.vulnerabilities = []
                self.scan_results = {}

            def scan_for_sql_injection(self, endpoint: str, payload: str):
                """Simulate SQL injection scanning."""
                # Mock scan results
                if "'" in payload or "DROP" in payload.upper():
                    self.vulnerabilities.append(
                        {"type": "sql_injection", "endpoint": endpoint, "payload": payload, "severity": "high"}
                    )

            def scan_for_xss(self, endpoint: str, payload: str):
                """Simulate XSS scanning."""
                if "<script>" in payload or "javascript:" in payload:
                    self.vulnerabilities.append(
                        {"type": "xss", "endpoint": endpoint, "payload": payload, "severity": "medium"}
                    )

            def scan_for_command_injection(self, endpoint: str, payload: str):
                """Simulate command injection scanning."""
                if any(cmd in payload for cmd in [";", "|", "&&", "$(", "`"]):
                    self.vulnerabilities.append(
                        {"type": "command_injection", "endpoint": endpoint, "payload": payload, "severity": "critical"}
                    )

            @property
            def has_vulnerabilities(self):
                return len(self.vulnerabilities) > 0

            @property
            def critical_vulnerabilities(self):
                return [v for v in self.vulnerabilities if v["severity"] == "critical"]

        return SecurityScanner()

    @pytest.fixture
    def compliance_checker(self):
        """Compliance checking fixture."""

        class ComplianceChecker:
            def __init__(self):
                self.checks = {}
                self.violations = []

            def check_gdpr_compliance(self, data_handling_practices):
                """Check GDPR compliance."""
                required_practices = [
                    "data_minimization",
                    "consent_management",
                    "right_to_erasure",
                    "data_portability",
                    "privacy_by_design",
                ]

                for practice in required_practices:
                    if practice not in data_handling_practices:
                        self.violations.append({"regulation": "GDPR", "requirement": practice, "severity": "high"})

                self.checks["gdpr"] = len(self.violations) == 0

            def check_soc2_compliance(self, security_controls):
                """Check SOC 2 compliance."""
                required_controls = [
                    "access_control",
                    "encryption",
                    "monitoring",
                    "incident_response",
                    "backup_recovery",
                ]

                for control in required_controls:
                    if control not in security_controls:
                        self.violations.append({"regulation": "SOC2", "requirement": control, "severity": "medium"})

                self.checks["soc2"] = len(self.violations) == 0

            @property
            def is_compliant(self):
                return all(self.checks.values()) and len(self.violations) == 0

        return ComplianceChecker()


# Combine all fixtures into a single class for easy import
class EnterpriseTestFixtures(
    DatabaseFixtures,
    MockFixtures,
    HTTPFixtures,
    FileSystemFixtures,
    AsyncFixtures,
    PerformanceFixtures,
    SecurityFixtures,
):
    """Combined enterprise test fixtures."""

    pass
