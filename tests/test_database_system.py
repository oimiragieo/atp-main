"""Tests for database system including models, migrations, and backup."""

import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from router_service.database import DatabaseConfig, DatabaseManager
from router_service.database_backup import DatabaseBackupManager, BackupScheduler
from router_service.models.database import (
    Request, Response, Provider, Model, Policy, AuditLog, 
    ComplianceViolation, SystemConfig, ModelStats
)


class TestDatabaseConfig:
    """Test database configuration."""
    
    def test_config_initialization(self):
        config = DatabaseConfig()
        
        assert config.pool_size == 10  # Default value
        assert config.max_overflow == 20
        assert config.pool_timeout == 30
        assert config.pool_recycle == 3600
        assert isinstance(config.database_url, str)
    
    @patch.dict('os.environ', {
        'DATABASE_URL': 'postgresql://user:pass@localhost:5432/testdb'
    })
    def test_config_from_database_url(self):
        config = DatabaseConfig()
        
        assert "postgresql+asyncpg://user:pass@localhost:5432/testdb" in config.database_url
    
    @patch.dict('os.environ', {
        'DB_HOST': 'testhost',
        'DB_PORT': '5433',
        'DB_NAME': 'testdb',
        'DB_USER': 'testuser',
        'DB_PASSWORD': 'testpass'
    })
    def test_config_from_components(self):
        config = DatabaseConfig()
        
        expected = "postgresql+asyncpg://testuser:testpass@testhost:5433/testdb"
        assert config.database_url == expected


class TestDatabaseManager:
    """Test database manager functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.config = DatabaseConfig()
        self.manager = DatabaseManager(self.config)
    
    async def test_manager_initialization(self):
        """Test database manager initialization."""
        assert self.manager.config == self.config
        assert self.manager.engine is None
        assert self.manager.session_factory is None
        assert not self.manager._initialized
    
    @patch('router_service.database.create_async_engine')
    @patch('router_service.database.async_sessionmaker')
    async def test_initialize_success(self, mock_sessionmaker, mock_create_engine):
        """Test successful database initialization."""
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        mock_sessionmaker.return_value = Mock()
        
        await self.manager.initialize()
        
        assert self.manager._initialized
        assert self.manager.engine == mock_engine
        mock_create_engine.assert_called_once()
        mock_sessionmaker.assert_called_once()
    
    @patch('router_service.database.create_async_engine')
    async def test_health_check_success(self, mock_create_engine):
        """Test successful health check."""
        # Mock engine and connection
        mock_connection = AsyncMock()
        mock_result = Mock()
        mock_result.scalar.return_value = 1
        mock_connection.execute.return_value = mock_result
        
        mock_engine = Mock()
        mock_engine.begin.return_value.__aenter__.return_value = mock_connection
        mock_create_engine.return_value = mock_engine
        
        await self.manager.initialize()
        result = await self.manager.health_check()
        
        assert result is True
    
    async def test_health_check_failure(self):
        """Test health check failure."""
        # Manager not initialized
        result = await self.manager.health_check()
        assert result is False


class TestDatabaseModels:
    """Test database model definitions."""
    
    def test_request_model(self):
        """Test Request model structure."""
        # Test that model can be instantiated
        request = Request(
            correlation_id="test-123",
            method="POST",
            path="/api/v1/ask",
            prompt="Test prompt",
            status_code=200,
            is_deleted=False  # Explicitly set default value
        )
        
        assert request.correlation_id == "test-123"
        assert request.method == "POST"
        assert request.path == "/api/v1/ask"
        assert request.prompt == "Test prompt"
        assert request.status_code == 200
        assert request.is_deleted is False
    
    def test_provider_model(self):
        """Test Provider model structure."""
        provider = Provider(
            name="openai",
            display_name="OpenAI",
            provider_type="openai",
            supports_streaming=True,
            supports_function_calling=True,
            supports_vision=False,
            is_enabled=True,
            health_status="healthy"
        )
        
        assert provider.name == "openai"
        assert provider.display_name == "OpenAI"
        assert provider.provider_type == "openai"
        assert provider.supports_streaming is True
        assert provider.is_enabled is True
        assert provider.health_status == "healthy"
    
    def test_policy_model(self):
        """Test Policy model structure."""
        policy = Policy(
            policy_id="test-policy",
            name="Test Policy",
            description="Test policy description",
            priority=100,
            is_enabled=True,
            rules={"rules": [{"effect": "permit"}]}
        )
        
        assert policy.policy_id == "test-policy"
        assert policy.name == "Test Policy"
        assert policy.priority == 100
        assert policy.is_enabled is True
        assert policy.rules == {"rules": [{"effect": "permit"}]}
    
    def test_audit_log_model(self):
        """Test AuditLog model structure."""
        audit_log = AuditLog(
            event_type="user_login",
            user_id="user123",
            action="login",
            outcome="success",
            event_data={"ip": "192.168.1.1"}
        )
        
        assert audit_log.event_type == "user_login"
        assert audit_log.user_id == "user123"
        assert audit_log.action == "login"
        assert audit_log.outcome == "success"
        assert audit_log.event_data == {"ip": "192.168.1.1"}
    
    def test_compliance_violation_model(self):
        """Test ComplianceViolation model structure."""
        violation = ComplianceViolation(
            violation_id="violation-123",
            rule_id="gdpr-rule-1",
            framework="gdpr",
            severity="high",
            title="Data Retention Violation",
            description="Data retained beyond policy limit",
            status="open",
            detected_at=datetime.utcnow()
        )
        
        assert violation.violation_id == "violation-123"
        assert violation.rule_id == "gdpr-rule-1"
        assert violation.framework == "gdpr"
        assert violation.severity == "high"
        assert violation.status == "open"


class TestDatabaseBackupManager:
    """Test database backup functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.backup_manager = DatabaseBackupManager()
        self.backup_manager.backup_dir = Path(self.temp_dir)
    
    def test_backup_manager_initialization(self):
        """Test backup manager initialization."""
        assert isinstance(self.backup_manager.config, DatabaseConfig)
        assert self.backup_manager.retention_days == 30
        assert self.backup_manager.compress_backups is True
        assert self.backup_manager.backup_format == "custom"
    
    async def test_list_backups_empty(self):
        """Test listing backups when none exist."""
        backups = await self.backup_manager.list_backups()
        assert backups == []
    
    async def test_list_backups_with_files(self):
        """Test listing backups with existing files."""
        # Create mock backup files
        backup_file = self.backup_manager.backup_dir / "test_backup.sql"
        backup_file.write_text("-- Test backup content")
        
        backups = await self.backup_manager.list_backups()
        
        assert len(backups) == 1
        assert backups[0]["name"] == "test_backup"
        assert backups[0]["type"] == "full"
        assert backups[0]["compressed"] is False
    
    async def test_verify_backup_nonexistent(self):
        """Test backup verification for non-existent file."""
        result = await self.backup_manager.verify_backup("nonexistent.sql")
        assert result is False
    
    async def test_verify_backup_empty_file(self):
        """Test backup verification for empty file."""
        empty_file = self.backup_manager.backup_dir / "empty.sql"
        empty_file.touch()
        
        result = await self.backup_manager.verify_backup(str(empty_file))
        assert result is False
    
    async def test_verify_backup_valid_sql(self):
        """Test backup verification for valid SQL file."""
        sql_file = self.backup_manager.backup_dir / "valid.sql"
        sql_file.write_text("-- PostgreSQL database dump\nCREATE TABLE test();")
        
        result = await self.backup_manager.verify_backup(str(sql_file))
        assert result is True
    
    def test_parse_database_url(self):
        """Test database URL parsing."""
        self.backup_manager.config.database_url = "postgresql+asyncpg://user:pass@host:5432/dbname"
        
        parsed = self.backup_manager._parse_database_url()
        
        assert parsed["host"] == "host"
        assert parsed["port"] == 5432
        assert parsed["database"] == "dbname"
        assert parsed["username"] == "user"
        assert parsed["password"] == "pass"


class TestBackupScheduler:
    """Test backup scheduler functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.backup_manager = Mock(spec=DatabaseBackupManager)
        self.scheduler = BackupScheduler(self.backup_manager)
    
    def test_scheduler_initialization(self):
        """Test scheduler initialization."""
        assert self.scheduler.backup_manager == self.backup_manager
        assert not self.scheduler.running
        assert self.scheduler._task is None
        assert self.scheduler.full_backup_interval == 24
        assert self.scheduler.incremental_backup_interval == 4
    
    async def test_start_scheduler(self):
        """Test starting the scheduler."""
        await self.scheduler.start()
        
        assert self.scheduler.running is True
        assert self.scheduler._task is not None
    
    async def test_stop_scheduler(self):
        """Test stopping the scheduler."""
        await self.scheduler.start()
        await self.scheduler.stop()
        
        assert self.scheduler.running is False


@pytest.mark.asyncio
class TestDatabaseAPI:
    """Test database management API endpoints."""
    
    async def test_database_health_response_model(self):
        """Test database health response model."""
        from router_service.database_api import DatabaseHealthResponse
        
        response = DatabaseHealthResponse(
            healthy=True,
            connection_pool_size=10,
            active_connections=2,
            database_version="PostgreSQL 13.0",
            last_check=datetime.utcnow()
        )
        
        assert response.healthy is True
        assert response.connection_pool_size == 10
        assert response.active_connections == 2
        assert "PostgreSQL" in response.database_version
    
    async def test_backup_info_model(self):
        """Test backup info model."""
        from router_service.database_api import BackupInfoModel
        
        backup_info = BackupInfoModel(
            name="test_backup",
            file="/path/to/backup.sql",
            size=1024,
            created_at=datetime.utcnow(),
            compressed=False,
            type="full"
        )
        
        assert backup_info.name == "test_backup"
        assert backup_info.file == "/path/to/backup.sql"
        assert backup_info.size == 1024
        assert backup_info.compressed is False
        assert backup_info.type == "full"


class TestDatabaseIntegration:
    """Integration tests for database system."""
    
    def test_database_models_import(self):
        """Test that all database models can be imported."""
        from router_service.models.database import (
            Request, Response, Provider, Model, Policy,
            AuditLog, ComplianceViolation, SystemConfig, ModelStats
        )
        
        # Verify all models are available
        assert Request is not None
        assert Response is not None
        assert Provider is not None
        assert Model is not None
        assert Policy is not None
        assert AuditLog is not None
        assert ComplianceViolation is not None
        assert SystemConfig is not None
        assert ModelStats is not None
    
    def test_database_manager_singleton(self):
        """Test database manager singleton pattern."""
        from router_service.database import get_database_manager
        
        manager1 = get_database_manager()
        manager2 = get_database_manager()
        
        # Should return the same instance
        assert manager1 is manager2
    
    def test_backup_manager_singleton(self):
        """Test backup manager singleton pattern."""
        from router_service.database_backup import get_backup_manager
        
        manager1 = get_backup_manager()
        manager2 = get_backup_manager()
        
        # Should return the same instance
        assert manager1 is manager2
    
    def test_migration_file_exists(self):
        """Test that initial migration file exists."""
        migration_file = Path("migrations/versions/001_initial_database_schema.py")
        assert migration_file.exists()
        
        # Check migration content
        content = migration_file.read_text()
        assert "def upgrade()" in content
        assert "def downgrade()" in content
        assert "create_table" in content