#!/usr/bin/env python3
"""
Configuration Loader for ATP Enterprise AI Platform

Loads configuration from YAML files and environment variables.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ConfigSource:
    """Configuration source information."""
    file_path: Optional[str] = None
    environment: Optional[str] = None
    defaults: Optional[Dict[str, Any]] = None

class ConfigLoader:
    """Configuration loader with environment variable override support."""
    
    def __init__(self, config_dir: str = "configs"):
        self.config_dir = Path(config_dir)
        self.config_cache: Dict[str, Any] = {}
        
    def load_config(self, 
                   environment: str = None, 
                   config_file: str = "app.yaml") -> Dict[str, Any]:
        """Load configuration for the specified environment."""
        
        # Determine environment
        if environment is None:
            environment = os.getenv("ENVIRONMENT", "development")
        
        # Create cache key
        cache_key = f"{environment}:{config_file}"
        
        # Return cached config if available
        if cache_key in self.config_cache:
            return self.config_cache[cache_key]
        
        # Load configuration
        config = self._load_config_file(environment, config_file)
        
        # Override with environment variables
        config = self._override_with_env_vars(config)
        
        # Validate configuration
        self._validate_config(config)
        
        # Cache and return
        self.config_cache[cache_key] = config
        return config
    
    def _load_config_file(self, environment: str, config_file: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        
        # Try environment-specific config first
        env_config_path = self.config_dir / environment / config_file
        if env_config_path.exists():
            logger.info(f"Loading config from {env_config_path}")
            return self._read_yaml_file(env_config_path)
        
        # Fall back to examples config
        example_config_path = self.config_dir / "examples" / config_file
        if example_config_path.exists():
            logger.warning(f"Using example config from {example_config_path}")
            return self._read_yaml_file(example_config_path)
        
        # Fall back to default config
        default_config_path = self.config_dir / config_file
        if default_config_path.exists():
            logger.info(f"Loading default config from {default_config_path}")
            return self._read_yaml_file(default_config_path)
        
        raise FileNotFoundError(f"No configuration file found for environment '{environment}'")
    
    def _read_yaml_file(self, file_path: Path) -> Dict[str, Any]:
        """Read and parse YAML file."""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
                
            # Replace environment variables in the content
            content = self._substitute_env_vars(content)
            
            # Parse YAML
            config = yaml.safe_load(content)
            return config or {}
            
        except Exception as e:
            logger.error(f"Failed to load config from {file_path}: {e}")
            raise
    
    def _substitute_env_vars(self, content: str) -> str:
        """Substitute environment variables in configuration content."""
        import re
        
        # Find all ${VAR_NAME} patterns
        pattern = r'\$\{([^}]+)\}'
        
        def replace_var(match):
            var_name = match.group(1)
            # Support default values: ${VAR_NAME:default_value}
            if ':' in var_name:
                var_name, default_value = var_name.split(':', 1)
                return os.getenv(var_name, default_value)
            else:
                return os.getenv(var_name, match.group(0))  # Return original if not found
        
        return re.sub(pattern, replace_var, content)
    
    def _override_with_env_vars(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Override configuration values with environment variables."""
        
        # Define environment variable mappings
        env_mappings = {
            # Application
            'ENVIRONMENT': 'app.environment',
            'DEBUG': 'app.debug',
            'LOG_LEVEL': 'logging.level',
            
            # Database
            'DATABASE_URL': 'database.url',
            'DB_POOL_SIZE': 'database.pool_size',
            'DB_MAX_OVERFLOW': 'database.max_overflow',
            
            # Redis
            'REDIS_URL': 'redis.url',
            'REDIS_MAX_CONNECTIONS': 'redis.max_connections',
            
            # Security
            'JWT_SECRET': 'security.auth.jwt_secret',
            'CSRF_SECRET_KEY': 'security.csrf.secret_key',
            
            # AI Providers
            'OPENAI_API_KEY': 'providers.openai.api_key',
            'ANTHROPIC_API_KEY': 'providers.anthropic.api_key',
            'GOOGLE_API_KEY': 'providers.google.api_key',
            
            # OIDC
            'OIDC_ENABLED': 'security.auth.oidc.enabled',
            'OIDC_ISSUER': 'security.auth.oidc.issuer',
            'OIDC_CLIENT_ID': 'security.auth.oidc.client_id',
            'OIDC_CLIENT_SECRET': 'security.auth.oidc.client_secret',
            
            # Monitoring
            'METRICS_ENABLED': 'monitoring.metrics.enabled',
            'METRICS_PORT': 'monitoring.metrics.port',
            'TRACING_ENABLED': 'monitoring.tracing.enabled',
            'JAEGER_ENDPOINT': 'monitoring.tracing.jaeger_endpoint',
            
            # Server
            'SERVER_HOST': 'server.host',
            'SERVER_PORT': 'server.port',
            'SERVER_WORKERS': 'server.workers',
        }
        
        # Apply environment variable overrides
        for env_var, config_path in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                self._set_nested_value(config, config_path, self._convert_value(env_value))
        
        return config
    
    def _set_nested_value(self, config: Dict[str, Any], path: str, value: Any):
        """Set a nested configuration value using dot notation."""
        keys = path.split('.')
        current = config
        
        # Navigate to the parent of the target key
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Set the final value
        current[keys[-1]] = value
    
    def _convert_value(self, value: str) -> Any:
        """Convert string value to appropriate type."""
        # Boolean conversion
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        
        # Integer conversion
        try:
            return int(value)
        except ValueError:
            pass
        
        # Float conversion
        try:
            return float(value)
        except ValueError:
            pass
        
        # Return as string
        return value
    
    def _validate_config(self, config: Dict[str, Any]):
        """Validate configuration values."""
        
        # Check required fields
        required_fields = [
            'app.name',
            'app.environment',
            'database.url',
            'redis.url'
        ]
        
        for field in required_fields:
            if not self._get_nested_value(config, field):
                logger.warning(f"Required configuration field missing: {field}")
        
        # Validate environment
        environment = self._get_nested_value(config, 'app.environment')
        if environment not in ['development', 'staging', 'production']:
            logger.warning(f"Unknown environment: {environment}")
        
        # Validate security settings for production
        if environment == 'production':
            self._validate_production_security(config)
    
    def _validate_production_security(self, config: Dict[str, Any]):
        """Validate security settings for production environment."""
        
        # Check that debug is disabled
        if self._get_nested_value(config, 'app.debug', False):
            logger.warning("Debug mode should be disabled in production")
        
        # Check for default secrets
        jwt_secret = self._get_nested_value(config, 'security.auth.jwt_secret', '')
        if 'change' in jwt_secret.lower() or len(jwt_secret) < 32:
            logger.error("JWT secret appears to be default or too short for production")
        
        # Check CORS settings
        cors_origins = self._get_nested_value(config, 'security.cors.origins', [])
        if 'localhost' in str(cors_origins):
            logger.warning("CORS origins include localhost in production")
    
    def _get_nested_value(self, config: Dict[str, Any], path: str, default: Any = None) -> Any:
        """Get a nested configuration value using dot notation."""
        keys = path.split('.')
        current = config
        
        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            return default
    
    def reload_config(self):
        """Clear configuration cache to force reload."""
        self.config_cache.clear()
        logger.info("Configuration cache cleared")

# Global configuration loader instance
config_loader = ConfigLoader()

def get_config(environment: str = None, config_file: str = "app.yaml") -> Dict[str, Any]:
    """Get configuration for the specified environment."""
    return config_loader.load_config(environment, config_file)

def reload_config():
    """Reload configuration from files."""
    config_loader.reload_config()

if __name__ == "__main__":
    # Test the configuration loader
    import json
    
    config = get_config()
    print("Loaded configuration:")
    print(json.dumps(config, indent=2, default=str))