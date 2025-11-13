"""Simple Persona Federation POC"""

from router_service.persona_federation import PersonaFederationNode
from router_service.reputation_model import ReputationModel


def test_basic_federation():
    """Test basic persona federation functionality."""
    print("Testing persona federation...")

    # Create two nodes
    node1 = PersonaFederationNode("router1", b"key1" * 8)
    node2 = PersonaFederationNode("router2", b"key2" * 8)

    # Create reputation models
    model1 = ReputationModel()
    model2 = ReputationModel()

    # Add some test data
    model1.record_performance("test-persona", 0.8, 100, 0.9, 1000000)
    model2.record_performance("test-persona", 0.9, 120, 0.85, 1000000)

    # Create signed stats
    signed1 = node1.create_signed_stats("test-persona", model1)
    signed2 = node2.create_signed_stats("test-persona", model2)

    if signed1 and signed2:
        print("Signed stats created successfully")

        # Test ingestion
        success1 = node1.ingest_federated_stats(signed2, b"key2" * 8)
        success2 = node2.ingest_federated_stats(signed1, b"key1" * 8)

        if success1 and success2:
            print("Federation ingestion successful")

            # Test consolidation
            consolidated1 = node1.get_consolidated_stats("test-persona")
            consolidated2 = node2.get_consolidated_stats("test-persona")

            if consolidated1 and consolidated2:
                print(f"Node1 consolidated: {consolidated1.reputation_score:.3f}")
                print(f"Node2 consolidated: {consolidated2.reputation_score:.3f}")
                print("SUCCESS: Basic federation test passed")
                return True

    print("FAIL: Basic federation test failed")
    return False


if __name__ == "__main__":
    test_basic_federation()
