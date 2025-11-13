"""Example of how to integrate the enterprise data access layer with the router service."""

import asyncio
import logging

from .data_service import get_data_service
from .registry_adapter import get_registry_adapter
from .repository_manager import get_repository_manager
from .startup import initialize_enterprise_data_layer

logger = logging.getLogger(__name__)


async def example_model_registry_usage():
    """Example of using the new data access layer for model registry operations."""

    print("=== Enterprise Data Access Layer Integration Example ===\n")

    # 1. Initialize the enterprise data layer
    print("1. Initializing enterprise data layer...")
    success = await initialize_enterprise_data_layer(
        create_tables=True,
        migrate_registry=False,  # Skip migration for this example
        create_samples=True,  # Create sample data
    )

    if not success:
        print("❌ Failed to initialize enterprise data layer")
        return

    print("✅ Enterprise data layer initialized successfully\n")

    # 2. Using the Data Service (recommended for new code)
    print("2. Using Data Service (recommended approach):")
    data_service = get_data_service()

    # Get model registry
    registry = await data_service.get_model_registry()
    print(f"   📊 Registry contains {len(registry)} models")

    # List models
    for model_name, model_data in list(registry.items())[:3]:  # Show first 3
        print(f"   🤖 {model_name}: {model_data['status']} ({model_data['provider']})")

    # Get shadow models
    shadow_models = await data_service.get_shadow_models()
    print(f"   🌙 Shadow models: {shadow_models}")

    print()

    # 3. Using the Registry Adapter (for backward compatibility)
    print("3. Using Registry Adapter (backward compatibility):")
    adapter = get_registry_adapter()

    # The adapter provides the same interface as the old in-memory registry
    registry_compat = await adapter.get_registry()
    print(f"   📊 Registry size: {len(registry_compat)}")

    # Synchronous access (for compatibility with existing code)
    if registry_compat:
        first_model = list(registry_compat.keys())[0]
        print(f"   🔍 First model: {first_model}")
        print(f"   📋 Model in registry: {first_model in adapter}")
        print(f"   📝 Model data: {adapter.get(first_model, {}).get('status', 'unknown')}")

    print()

    # 4. Direct Repository Usage (for advanced operations)
    print("4. Using Repository Manager (advanced operations):")
    repo_manager = get_repository_manager()

    # Get model statistics
    model_stats = await repo_manager.models.get_model_statistics()
    print(f"   📈 Model statistics: {model_stats}")

    # Get provider statistics
    provider_stats = await repo_manager.providers.get_provider_statistics()
    print(f"   🏢 Provider statistics: {provider_stats}")

    print()

    # 5. Transaction Example
    print("5. Transaction Management Example:")
    try:
        async with repo_manager.transaction() as tx_manager:
            # All operations within this block are part of the same transaction
            print("   🔄 Starting transaction...")

            # Example: Update multiple models atomically
            models = await tx_manager.models.get_enabled_models()
            if models:
                model = models[0]
                print(f"   📝 Updating performance for model: {model.name}")

                success = await tx_manager.models.update_performance_metrics(
                    model.id, quality_score=0.95, latency_p95_ms=150.0
                )

                if success:
                    print("   ✅ Model performance updated in transaction")
                else:
                    print("   ❌ Failed to update model performance")

            # Transaction will be committed automatically when exiting the context
            print("   ✅ Transaction completed successfully")

    except Exception as e:
        print(f"   ❌ Transaction failed: {e}")

    print()

    # 6. Health Check
    print("6. Health Check:")
    health = await data_service.health_check()
    print(f"   🏥 Overall status: {health['status']}")
    print(f"   🔗 Database connection: {health['database_connection']}")
    print(f"   📊 Registry size: {health['registry_size']}")

    print("\n=== Integration Example Complete ===")


async def example_request_logging():
    """Example of logging requests using the new data access layer."""

    print("\n=== Request Logging Example ===")

    data_service = get_data_service()

    # Log a sample request
    request = await data_service.log_request(
        correlation_id="example-123",
        user_id="user-456",
        tenant_id="tenant-789",
        session_id="session-abc",
        prompt="What is the capital of France?",
        model_used="gpt-4",
        provider_used="openai",
        response_text="The capital of France is Paris.",
        status_code=200,
        response_time_ms=250.5,
        tokens_input=8,
        tokens_output=7,
        cost_usd=0.0001,
        quality_score=0.95,
        confidence_score=0.98,
        request_metadata={"source": "example", "version": "1.0"},
    )

    if request:
        print(f"✅ Request logged with ID: {request.id}")
        print(f"   📝 Correlation ID: {request.correlation_id}")
        print(f"   💰 Cost: ${request.cost_usd}")
        print(f"   ⏱️  Response time: {request.response_time_ms}ms")
    else:
        print("❌ Failed to log request")

    print("=== Request Logging Example Complete ===\n")


async def example_migration_workflow():
    """Example of migrating from old registry file to database."""

    print("=== Migration Workflow Example ===")

    # This would typically be used when transitioning from file-based registry
    from .registry_migration import create_sample_models, export_database_to_registry

    # Create sample models (simulating existing data)
    print("1. Creating sample models...")
    success = await create_sample_models()
    if success:
        print("✅ Sample models created")
    else:
        print("ℹ️  Sample models already exist or creation skipped")

    # Export current database state to registry format
    print("2. Exporting database to registry format...")
    export_success = await export_database_to_registry("exported_registry.json")
    if export_success:
        print("✅ Database exported to exported_registry.json")
    else:
        print("❌ Failed to export database")

    print("=== Migration Workflow Example Complete ===\n")


async def main():
    """Main example function."""

    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Suppress verbose database logs
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

    try:
        # Run examples
        await example_model_registry_usage()
        await example_request_logging()
        await example_migration_workflow()

        print("🎉 All examples completed successfully!")

    except Exception as e:
        print(f"❌ Example failed: {e}")
        logger.exception("Example execution failed")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
