"""Tests for GAP-116C: Persona federation schema."""

import hashlib
import time
from unittest.mock import Mock

from router_service.persona_federation import PersonaFederationNode, PersonaStats
from router_service.reputation_model import ReputationModel


class TestPersonaFederation:
    """Test persona federation functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.router_name = "test-router"
        self.key = hashlib.sha256(b"test-key").digest()
        self.node = PersonaFederationNode(self.router_name, self.key)

        # Create mock reputation model
        self.reputation_model = Mock(spec=ReputationModel)
        self.reputation_model.get_persona_stats.return_value = {
            "persona": "test-persona",
            "sample_count": 50,
            "reputation_score": 0.85,
            "reliability_score": 0.92,
            "has_min_samples": True,
        }

    def test_create_signed_stats(self):
        """Test creating signed persona statistics."""
        signed_stats = self.node.create_signed_stats("test-persona", self.reputation_model)

        assert signed_stats is not None
        assert signed_stats.stats.persona_id == "test-persona"
        assert signed_stats.stats.reputation_score == 0.85
        assert signed_stats.stats.reliability_score == 0.92
        assert signed_stats.stats.sample_count == 50
        assert signed_stats.origin_router == self.router_name
        assert signed_stats.sequence_number == 1
        assert signed_stats.signature is not None

    def test_create_signed_stats_insufficient_data(self):
        """Test creating signed stats with insufficient data."""
        self.reputation_model.get_persona_stats.return_value = {
            "persona": "test-persona",
            "sample_count": 5,
            "reputation_score": None,
            "has_min_samples": False,
        }

        signed_stats = self.node.create_signed_stats("test-persona", self.reputation_model)

        assert signed_stats is None

    def test_validate_signed_stats(self):
        """Test validation of signed persona statistics."""
        signed_stats = self.node.create_signed_stats("test-persona", self.reputation_model)

        assert signed_stats is not None

        # Should validate with correct key
        is_valid = self.node.validate_signed_stats(signed_stats, self.key)
        assert is_valid

        # Should not validate with wrong key
        wrong_key = hashlib.sha256(b"wrong-key").digest()
        is_valid_wrong = self.node.validate_signed_stats(signed_stats, wrong_key)
        assert not is_valid_wrong

    def test_validate_expired_stats(self):
        """Test validation of expired signed statistics."""
        signed_stats = self.node.create_signed_stats("test-persona", self.reputation_model)

        # Manually set old timestamp
        signed_stats.timestamp = time.time() - 7200  # 2 hours ago

        # Should not validate (default max_age is 3600 seconds = 1 hour)
        is_valid = self.node.validate_signed_stats(signed_stats, self.key)
        assert not is_valid

    def test_ingest_federated_stats(self):
        """Test ingesting federated persona statistics."""
        signed_stats = self.node.create_signed_stats("test-persona", self.reputation_model)

        assert signed_stats is not None

        # Should successfully ingest
        success = self.node.ingest_federated_stats(signed_stats, self.key)
        assert success

        # Should be in federated stats
        assert "test-persona" in self.node.federated_stats
        assert len(self.node.federated_stats["test-persona"]) == 1

    def test_ingest_invalid_signature(self):
        """Test ingesting stats with invalid signature."""
        signed_stats = self.node.create_signed_stats("test-persona", self.reputation_model)

        # Tamper with signature
        signed_stats.signature = "invalid-signature"

        # Should fail to ingest
        success = self.node.ingest_federated_stats(signed_stats, self.key)
        assert not success

    def test_sequence_number_conflict_resolution(self):
        """Test conflict resolution with sequence numbers."""
        # Create first stats
        signed_stats1 = self.node.create_signed_stats("test-persona", self.reputation_model)

        # Create second stats (should have higher sequence number)
        signed_stats2 = self.node.create_signed_stats("test-persona", self.reputation_model)

        assert signed_stats2.sequence_number > signed_stats1.sequence_number

        # Ingest both
        self.node.ingest_federated_stats(signed_stats1, self.key)
        self.node.ingest_federated_stats(signed_stats2, self.key)

        # Should only have the latest one from same router
        federated = self.node.federated_stats["test-persona"]
        assert len(federated) == 1
        assert federated[0].sequence_number == signed_stats2.sequence_number

    def test_reputation_conflict_merge(self):
        """Test merging stats with significant reputation differences."""
        # Create first stats
        signed_stats1 = self.node.create_signed_stats("test-persona", self.reputation_model)

        # Create conflicting stats from different router
        other_router = "other-router"
        other_key = hashlib.sha256(b"other-key").digest()
        other_node = PersonaFederationNode(other_router, other_key)

        # Mock reputation model with very different score
        conflicting_model = Mock(spec=ReputationModel)
        conflicting_model.get_persona_stats.return_value = {
            "persona": "test-persona",
            "sample_count": 30,
            "reputation_score": 0.5,  # Much lower than 0.85 (difference > 0.3)
            "reliability_score": 0.88,
            "has_min_samples": True,
        }

        signed_stats2 = other_node.create_signed_stats("test-persona", conflicting_model)

        # Ingest first stats
        self.node.ingest_federated_stats(signed_stats1, self.key)

        # Ingest conflicting stats (should trigger merge)
        success = self.node.ingest_federated_stats(signed_stats2, other_key)
        assert success

        # Should have merged stats
        federated = self.node.federated_stats["test-persona"]
        assert len(federated) >= 1

        # Check consolidated stats
        consolidated = self.node.get_consolidated_stats("test-persona")
        assert consolidated is not None
        # Should be weighted average between 0.85 and 0.5
        expected_avg = (0.85 * 50 + 0.5 * 30) / (50 + 30)
        assert abs(consolidated.reputation_score - expected_avg) < 0.01

    def test_get_consolidated_stats(self):
        """Test getting consolidated persona statistics."""
        # Test with no federated data
        consolidated = self.node.get_consolidated_stats("nonexistent-persona")
        assert consolidated is None

        # Test with local data only
        signed_stats = self.node.create_signed_stats("test-persona", self.reputation_model)
        self.node.local_stats["test-persona"] = signed_stats.stats

        consolidated = self.node.get_consolidated_stats("test-persona")
        assert consolidated is not None
        assert consolidated.persona_id == "test-persona"

    def test_persona_stats_serialization(self):
        """Test PersonaStats serialization/deserialization."""
        stats = PersonaStats(
            persona_id="test-persona",
            reputation_score=0.85,
            reliability_score=0.92,
            sample_count=50,
            last_updated=time.time(),
            router_origin="test-router",
            constraints={"region": "us-west"},
        )

        # Test to_dict
        data = stats.to_dict()
        assert data["persona_id"] == "test-persona"
        assert data["reputation_score"] == 0.85
        assert data["constraints"]["region"] == "us-west"

        # Test from_dict
        restored = PersonaStats.from_dict(data)
        assert restored.persona_id == stats.persona_id
        assert restored.reputation_score == stats.reputation_score
        assert restored.constraints == stats.constraints
