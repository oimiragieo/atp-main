#!/usr/bin/env python3
"""
Tests for AGP version compatibility and unknown field handling (GAP-109N)
"""

import pytest

from router_service.agp_update_handler import AGPOpenMessage, AGPUpdateMessage, ValidationError


class TestAGPOpenMessage:
    """Test AGP OPEN message and version negotiation."""

    def test_valid_open_message(self):
        """Test valid OPEN message creation and validation."""
        msg = AGPOpenMessage(
            router_id="test-router-123", adn=64512, capabilities={"agp_version": "1.0", "max_prefix": 131072}
        )
        msg.validate()  # Should not raise

    def test_open_message_validation_missing_router_id(self):
        """Test OPEN message validation with missing router_id."""
        msg = AGPOpenMessage(router_id="", adn=64512)
        with pytest.raises(ValidationError, match="router_id is required"):
            msg.validate()

    def test_open_message_validation_invalid_adn(self):
        """Test OPEN message validation with invalid ADN."""
        msg = AGPOpenMessage(router_id="test-router", adn=-1)
        with pytest.raises(ValidationError, match="Invalid ADN"):
            msg.validate()

    def test_open_message_validation_invalid_capabilities(self):
        """Test OPEN message validation with invalid capabilities."""
        msg = AGPOpenMessage(router_id="test-router", adn=64512, capabilities="invalid")
        with pytest.raises(ValidationError, match="capabilities must be a dictionary"):
            msg.validate()

    def test_get_agp_version(self):
        """Test getting AGP version from capabilities."""
        msg = AGPOpenMessage(capabilities={"agp_version": "1.1"})
        assert msg.get_agp_version() == "1.1"

    def test_get_agp_version_default(self):
        """Test getting default AGP version when not specified."""
        msg = AGPOpenMessage(capabilities={})
        assert msg.get_agp_version() == "1.0"

    def test_version_compatibility_same_major(self):
        """Test version compatibility with same major version."""
        msg = AGPOpenMessage(capabilities={"agp_version": "1.1"})
        assert msg.is_version_compatible("1.0") is True
        assert msg.is_version_compatible("1.2") is True

    def test_version_compatibility_different_major(self):
        """Test version compatibility with different major version."""
        msg = AGPOpenMessage(capabilities={"agp_version": "2.0"})
        assert msg.is_version_compatible("1.0") is False

    def test_version_compatibility_invalid_version(self):
        """Test version compatibility with invalid version strings."""
        msg = AGPOpenMessage(capabilities={"agp_version": "invalid"})
        assert msg.is_version_compatible("1.0") is False

    def test_version_negotiation_compatible(self):
        """Test version negotiation with compatible versions."""
        msg = AGPOpenMessage(capabilities={"agp_version": "1.1"})
        negotiated = msg.negotiate_version("1.0")
        assert negotiated == "1.0"  # Should choose minimum

    def test_version_negotiation_incompatible(self):
        """Test version negotiation with incompatible versions."""
        msg = AGPOpenMessage(capabilities={"agp_version": "2.0"})
        with pytest.raises(ValidationError, match="Incompatible AGP version"):
            msg.negotiate_version("1.0")

    def test_from_dict_known_fields(self):
        """Test creating OPEN message from dict with known fields."""
        data = {"type": "OPEN", "router_id": "test-router", "adn": 64512, "capabilities": {"agp_version": "1.0"}}
        msg = AGPOpenMessage.from_dict(data)
        assert msg.router_id == "test-router"
        assert msg.adn == 64512
        assert msg.get_agp_version() == "1.0"

    def test_from_dict_unknown_fields_ignored(self):
        """Test that unknown fields are ignored when creating OPEN message."""
        data = {
            "type": "OPEN",
            "router_id": "test-router",
            "adn": 64512,
            "capabilities": {"agp_version": "1.0"},
            "unknown_field": "ignored",
            "another_unknown": 123,
        }
        msg = AGPOpenMessage.from_dict(data)
        assert msg.router_id == "test-router"
        assert msg.adn == 64512
        # Unknown fields should not affect the message
        assert hasattr(msg, "unknown_field") is False


class TestAGPUpdateMessageUnknownFields:
    """Test AGP UPDATE message handling of unknown fields."""

    def test_update_from_dict_known_fields(self):
        """Test creating UPDATE message from dict with known fields."""
        data = {
            "type": "UPDATE",
            "announce": [{"prefix": "test.*", "attrs": {"path": [64512], "next_hop": "peer1"}}],
            "withdraw": ["old.*"],
        }
        msg = AGPUpdateMessage.from_dict(data)
        assert msg.type == "UPDATE"
        assert len(msg.announce) == 1
        assert msg.withdraw == ["old.*"]

    def test_update_from_dict_unknown_fields_ignored(self):
        """Test that unknown fields are ignored when creating UPDATE message."""
        data = {
            "type": "UPDATE",
            "announce": [{"prefix": "test.*", "attrs": {"path": [64512], "next_hop": "peer1"}}],
            "unknown_field": "ignored",
            "future_extension": {"some": "data"},
        }
        msg = AGPUpdateMessage.from_dict(data)
        assert msg.type == "UPDATE"
        assert len(msg.announce) == 1
        # Unknown fields should not affect the message
        assert hasattr(msg, "unknown_field") is False

    def test_update_from_dict_missing_fields(self):
        """Test creating UPDATE message from dict with missing fields."""
        data = {
            "type": "UPDATE"
            # announce and withdraw are optional
        }
        msg = AGPUpdateMessage.from_dict(data)
        assert msg.type == "UPDATE"
        assert msg.announce is None
        assert msg.withdraw is None


class TestVersionNegotiationIntegration:
    """Test version negotiation integration scenarios."""

    def test_backward_compatibility_newer_peer(self):
        """Test that newer peer can communicate with older implementation."""
        # Simulate older implementation receiving message with unknown fields
        data = {
            "type": "UPDATE",
            "announce": [
                {
                    "prefix": "test.*",
                    "attrs": {
                        "path": [64512],
                        "next_hop": "peer1",
                        "future_field": "unknown_to_old_version",  # Unknown field
                    },
                }
            ],
            "unknown_message_field": "also_unknown",  # Unknown message field
        }

        # Should not fail due to unknown fields
        msg = AGPUpdateMessage.from_dict(data)
        assert msg.type == "UPDATE"
        assert len(msg.announce) == 1

    def test_open_message_unknown_capabilities(self):
        """Test OPEN message with unknown capabilities."""
        data = {
            "type": "OPEN",
            "router_id": "test-router",
            "adn": 64512,
            "capabilities": {
                "agp_version": "1.0",
                "known_capability": "value",
                "future_capability": "unknown",  # Unknown capability
                "another_future": 123,
            },
        }

        msg = AGPOpenMessage.from_dict(data)
        assert msg.router_id == "test-router"
        assert msg.get_agp_version() == "1.0"
        # Unknown capabilities should be preserved
        assert "future_capability" in msg.capabilities


if __name__ == "__main__":
    pytest.main([__file__])
