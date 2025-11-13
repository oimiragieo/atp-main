"""Migration utilities for transitioning from in-memory registry to database."""

import json
import logging
import os
from typing import Any

from .data_service import get_data_service
from .repository_manager import get_repository_manager

logger = logging.getLogger(__name__)


async def migrate_registry_to_database(registry_file_path: str) -> bool:
    """Migrate model registry from JSON file to database."""
    try:
        # Load existing registry file
        if not os.path.exists(registry_file_path):
            logger.warning(f"Registry file not found: {registry_file_path}")
            return False

        with open(registry_file_path) as f:
            registry_data = json.load(f)

        if not isinstance(registry_data, dict):
            logger.error("Registry data is not a dictionary")
            return False

        repo_manager = get_repository_manager()
        migrated_count = 0

        # Create default provider if needed
        default_provider = await repo_manager.providers.get_by_name("default")
        if not default_provider:
            default_provider = await repo_manager.providers.create(
                name="default",
                display_name="Default Provider",
                provider_type="generic",
                is_enabled=True,
                health_status="healthy",
            )
            logger.info("Created default provider for migration")

        # Migrate each model
        for model_name, model_data in registry_data.items():
            try:
                # Check if model already exists
                existing_model = await repo_manager.models.get_by_name(model_name)
                if existing_model:
                    logger.info(f"Model {model_name} already exists, skipping")
                    continue

                # Extract provider information
                provider_name = model_data.get("provider", "default")
                provider = await repo_manager.providers.get_by_name(provider_name)
                if not provider:
                    # Create provider if it doesn't exist
                    provider = await repo_manager.providers.create(
                        name=provider_name,
                        display_name=provider_name.title(),
                        provider_type="generic",
                        is_enabled=True,
                        health_status="unknown",
                    )
                    logger.info(f"Created provider {provider_name} during migration")

                # Create model
                await repo_manager.models.create(
                    name=model_name,
                    display_name=model_data.get("display_name", model_name),
                    provider_id=provider.id,
                    status=model_data.get("status", "active"),
                    is_enabled=model_data.get("is_enabled", True),
                    model_family=model_data.get("model_family", "unknown"),
                    context_window=model_data.get("context_window", 4096),
                    max_output_tokens=model_data.get("max_output_tokens", 1024),
                    supports_streaming=model_data.get("supports_streaming", False),
                    supports_function_calling=model_data.get("supports_function_calling", False),
                    supports_vision=model_data.get("supports_vision", False),
                    cost_per_input_token=model_data.get("cost_per_input_token", 0.0),
                    cost_per_output_token=model_data.get("cost_per_output_token", 0.0),
                    cost_per_request=model_data.get("cost_per_request", 0.0),
                    latency_p50_ms=model_data.get("latency_p50_ms", 0.0),
                    latency_p95_ms=model_data.get("latency_p95_ms", 0.0),
                    quality_score=model_data.get("quality_score", 0.0),
                )

                migrated_count += 1
                logger.info(f"Migrated model {model_name} to database")

            except Exception as e:
                logger.error(f"Failed to migrate model {model_name}: {e}")
                continue

        logger.info(f"Migration completed: {migrated_count} models migrated")
        return migrated_count > 0

    except Exception as e:
        logger.error(f"Registry migration failed: {e}")
        return False


async def export_database_to_registry(output_file_path: str) -> bool:
    """Export database models to registry JSON format."""
    try:
        data_service = get_data_service()
        registry_data = await data_service.get_model_registry()

        # Write to file
        with open(output_file_path, "w") as f:
            json.dump(registry_data, f, indent=2, default=str)

        logger.info(f"Exported {len(registry_data)} models to {output_file_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to export database to registry: {e}")
        return False


async def validate_migration(registry_file_path: str) -> dict[str, Any]:
    """Validate that migration was successful by comparing file and database."""
    try:
        # Load file data
        with open(registry_file_path) as f:
            file_data = json.load(f)

        # Get database data
        data_service = get_data_service()
        db_data = await data_service.get_model_registry()

        # Compare
        file_models = set(file_data.keys())
        db_models = set(db_data.keys())

        missing_in_db = file_models - db_models
        extra_in_db = db_models - file_models
        common_models = file_models & db_models

        validation_result = {
            "total_file_models": len(file_models),
            "total_db_models": len(db_models),
            "common_models": len(common_models),
            "missing_in_db": list(missing_in_db),
            "extra_in_db": list(extra_in_db),
            "migration_success": len(missing_in_db) == 0,
        }

        # Check data consistency for common models
        inconsistencies = []
        for model_name in common_models:
            file_model = file_data[model_name]
            db_model = db_data[model_name]

            # Check key fields
            key_fields = ["status", "is_enabled", "provider"]
            for field in key_fields:
                if file_model.get(field) != db_model.get(field):
                    inconsistencies.append(
                        {
                            "model": model_name,
                            "field": field,
                            "file_value": file_model.get(field),
                            "db_value": db_model.get(field),
                        }
                    )

        validation_result["inconsistencies"] = inconsistencies
        validation_result["data_consistent"] = len(inconsistencies) == 0

        return validation_result

    except Exception as e:
        logger.error(f"Migration validation failed: {e}")
        return {"error": str(e), "migration_success": False, "data_consistent": False}


async def create_sample_models() -> bool:
    """Create sample models for testing if no models exist."""
    try:
        repo_manager = get_repository_manager()

        # Check if any models exist
        model_count = await repo_manager.models.count()
        if model_count > 0:
            logger.info(f"Models already exist ({model_count}), skipping sample creation")
            return True

        # Create sample providers
        providers_data = [
            {
                "name": "openai",
                "display_name": "OpenAI",
                "provider_type": "cloud",
                "supports_streaming": True,
                "supports_function_calling": True,
                "supports_vision": True,
            },
            {
                "name": "anthropic",
                "display_name": "Anthropic",
                "provider_type": "cloud",
                "supports_streaming": True,
                "supports_function_calling": True,
                "supports_vision": False,
            },
            {
                "name": "local",
                "display_name": "Local Models",
                "provider_type": "local",
                "supports_streaming": True,
                "supports_function_calling": False,
                "supports_vision": False,
            },
        ]

        providers = {}
        for provider_data in providers_data:
            provider = await repo_manager.providers.create(**provider_data)
            providers[provider.name] = provider
            logger.info(f"Created sample provider: {provider.name}")

        # Create sample models
        models_data = [
            {
                "name": "gpt-4",
                "display_name": "GPT-4",
                "provider_id": providers["openai"].id,
                "status": "active",
                "model_family": "gpt-4",
                "context_window": 8192,
                "max_output_tokens": 4096,
                "supports_streaming": True,
                "supports_function_calling": True,
                "supports_vision": True,
                "cost_per_input_token": 0.00003,
                "cost_per_output_token": 0.00006,
                "quality_score": 0.95,
            },
            {
                "name": "gpt-3.5-turbo",
                "display_name": "GPT-3.5 Turbo",
                "provider_id": providers["openai"].id,
                "status": "active",
                "model_family": "gpt-3.5",
                "context_window": 4096,
                "max_output_tokens": 2048,
                "supports_streaming": True,
                "supports_function_calling": True,
                "supports_vision": False,
                "cost_per_input_token": 0.0000015,
                "cost_per_output_token": 0.000002,
                "quality_score": 0.85,
            },
            {
                "name": "claude-3-opus",
                "display_name": "Claude 3 Opus",
                "provider_id": providers["anthropic"].id,
                "status": "shadow",
                "model_family": "claude-3",
                "context_window": 200000,
                "max_output_tokens": 4096,
                "supports_streaming": True,
                "supports_function_calling": True,
                "supports_vision": True,
                "cost_per_input_token": 0.000015,
                "cost_per_output_token": 0.000075,
                "quality_score": 0.92,
            },
            {
                "name": "llama-2-7b",
                "display_name": "Llama 2 7B",
                "provider_id": providers["local"].id,
                "status": "active",
                "model_family": "llama-2",
                "context_window": 4096,
                "max_output_tokens": 2048,
                "supports_streaming": True,
                "supports_function_calling": False,
                "supports_vision": False,
                "cost_per_input_token": 0.0,
                "cost_per_output_token": 0.0,
                "quality_score": 0.75,
            },
        ]

        created_count = 0
        for model_data in models_data:
            model = await repo_manager.models.create(**model_data)
            created_count += 1
            logger.info(f"Created sample model: {model.name}")

        logger.info(f"Created {created_count} sample models and {len(providers)} providers")
        return True

    except Exception as e:
        logger.error(f"Failed to create sample models: {e}")
        return False
