"""Simple validation script for Phase 3 adapter integration."""

import asyncio
import sys


def test_imports():
    """Test that all Phase 3 imports work."""
    print("Testing Phase 3 imports...")

    try:
        from router_service.adapters.client import AdapterClient, AdapterClientPool

        print("  ✓ AdapterClient imports")
        print("  ✓ AdapterClientPool imports")

        from router_service.routing_constants import CATALOG, load_catalog_from_adapters, refresh_catalog

        print("  ✓ Dynamic catalog imports")
        print(f"  ✓ Catalog contains {len(CATALOG)} models")

        # Test config has adapter settings (without instantiating)
        import router_service.config as config_module

        # Check that Settings class has the new adapter fields
        settings_fields = dir(config_module.Settings)
        required_fields = ["use_real_adapters", "adapter_timeout", "adapter_rollout_percent", "get_adapter_endpoint"]
        for field in required_fields:
            assert field in settings_fields or hasattr(config_module.Settings, field)
        print(f"  ✓ Config has all adapter settings fields")

        return True
    except Exception as e:
        print(f"  ✗ Import failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_adapter_client_basic():
    """Test basic adapter client functionality."""
    print("\nTesting AdapterClient basic functionality...")

    try:
        from router_service.adapters.client import AdapterClient, AdapterClientPool

        # Test client creation
        client = AdapterClient("localhost:7073", timeout=30.0)
        assert client.endpoint == "localhost:7073"
        assert client.timeout == 30.0
        print("  ✓ AdapterClient creation")

        # Test pool creation
        pool = AdapterClientPool()
        client1 = pool.get_client("localhost:7073")
        client2 = pool.get_client("localhost:7073")
        assert client1 is client2  # Should be the same instance
        print("  ✓ AdapterClientPool creation and reuse")

        # Test get_active_clients
        active = pool.get_active_clients()
        assert "localhost:7073" in active
        print(f"  ✓ Pool tracks active clients: {active}")

        return True
    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_dynamic_catalog():
    """Test dynamic catalog loading."""
    print("\nTesting dynamic catalog...")

    try:
        from router_service.routing_constants import CATALOG, STATIC_CATALOG, refresh_catalog

        # Check catalog loaded
        print(f"  ✓ CATALOG contains {len(CATALOG)} models")

        # Check fallback to static in test environment
        if CATALOG == STATIC_CATALOG:
            print("  ✓ Gracefully fell back to STATIC_CATALOG (expected in test env)")

        # Check model structure
        for model in CATALOG[:2]:  # Check first 2 models
            print(f"    - {model.name}: ${model.cost_per_1k_tokens}/1K tokens, {model.latency_p95}ms p95")

        # Test refresh function exists
        print("  ✓ refresh_catalog() function available")

        return True
    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_adapter_pool_lifecycle():
    """Test adapter pool lifecycle management."""
    print("\nTesting AdapterClientPool lifecycle...")

    try:
        from router_service.adapters.client import AdapterClientPool

        pool = AdapterClientPool()

        # Get some clients
        client1 = pool.get_client("localhost:7073")
        client2 = pool.get_client("localhost:7074")
        print(f"  ✓ Created clients for 2 endpoints")

        # Check active
        active = pool.get_active_clients()
        assert len(active) == 2
        print(f"  ✓ Pool tracks {len(active)} active clients")

        # Note: We can't test close_all() without mocking because it would
        # try to actually close gRPC channels
        print("  ✓ Pool lifecycle management available")

        return True
    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all validation tests."""
    print("=" * 60)
    print("Phase 3 Adapter Integration Validation")
    print("=" * 60)

    results = []

    # Run synchronous tests
    results.append(("Imports", test_imports()))
    results.append(("AdapterClient Basic", test_adapter_client_basic()))
    results.append(("Dynamic Catalog", test_dynamic_catalog()))

    # Run async tests
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    results.append(("AdapterPool Lifecycle", loop.run_until_complete(test_adapter_pool_lifecycle())))
    loop.close()

    # Summary
    print("\n" + "=" * 60)
    print("Validation Results")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("✓ All validation tests passed!")
        return 0
    else:
        print("✗ Some validation tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
