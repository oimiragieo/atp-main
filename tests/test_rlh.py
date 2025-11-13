#!/usr/bin/env python3
"""
Tests for Router Label Header (RLH) implementation
"""

import pytest

from router_service.rlh import (
    QoS,
    RLHEncapsulatedFrame,
    RLHFlags,
    RLHHeader,
    RLHProcessor,
)


class TestRLHHeader:
    def setup_method(self):
        """Set up test fixtures."""
        self.test_uuid = "12345678-1234-5678-9012-123456789012"
        self.hmac_key = b"test-hmac-key-32-bytes-long-key!!"

    def test_header_creation(self):
        """Test RLH header creation."""
        header = RLHHeader.create(
            dst_router_id=self.test_uuid,
            egress_agent_id=12345,
            qos=QoS.GOLD,
            ttl=64,
            budget_tokens=100000,
            budget_usd_micros=1000000,
            hmac_key=self.hmac_key,
        )

        assert header.dst_router_id == self.test_uuid
        assert header.egress_agent_id == 12345
        assert header.qos == QoS.GOLD
        assert header.ttl == 64
        assert header.budget_tokens == 100000
        assert header.budget_usd_micros == 1000000
        assert header.flags == 0
        assert len(header.hmac) == 16  # 128-bit

    def test_hmac_computation_and_verification(self):
        """Test HMAC computation and verification."""
        header = RLHHeader.create(
            dst_router_id=self.test_uuid,
            egress_agent_id=12345,
            qos=QoS.GOLD,
            ttl=64,
            budget_tokens=100000,
            budget_usd_micros=1000000,
            hmac_key=self.hmac_key,
        )

        # Verify HMAC
        assert header.verify_hmac(self.hmac_key)

        # Test with wrong key
        wrong_key = b"wrong-key-16-bytes!!"
        assert not header.verify_hmac(wrong_key)

    def test_ttl_decrement(self):
        """Test TTL decrement functionality."""
        header = RLHHeader.create(
            dst_router_id=self.test_uuid,
            egress_agent_id=12345,
            qos=QoS.GOLD,
            ttl=5,
            budget_tokens=100000,
            budget_usd_micros=1000000,
        )

        # Decrement TTL
        assert header.decrement_ttl()
        assert header.ttl == 4

        # Continue decrementing
        for _ in range(3):  # Decrement 3 more times: 4->3->2->1
            assert header.decrement_ttl()

        # Last decrement should return False (TTL becomes 0)
        assert not header.decrement_ttl()
        assert header.ttl == 0
        assert header.is_expired()

    def test_budget_decrement(self):
        """Test budget decrement functionality."""
        header = RLHHeader.create(
            dst_router_id=self.test_uuid,
            egress_agent_id=12345,
            qos=QoS.GOLD,
            ttl=64,
            budget_tokens=1000,
            budget_usd_micros=2000,
        )

        # Decrement budget
        assert header.decrement_budget(100, 200)
        assert header.budget_tokens == 900
        assert header.budget_usd_micros == 1800
        assert header.has_budget()

        # Continue decrementing
        assert not header.decrement_budget(900, 1800)
        assert header.budget_tokens == 0
        assert header.budget_usd_micros == 0
        assert not header.has_budget()

        # Further decrements should not go negative
        assert not header.decrement_budget(100, 200)
        assert header.budget_tokens == 0
        assert header.budget_usd_micros == 0

    def test_flag_operations(self):
        """Test flag set/clear/check operations."""
        header = RLHHeader.create(
            dst_router_id=self.test_uuid,
            egress_agent_id=12345,
            qos=QoS.GOLD,
            ttl=64,
            budget_tokens=100000,
            budget_usd_micros=1000000,
        )

        # Initially no flags set
        assert not header.has_flag(RLHFlags.ECN)
        assert not header.has_flag(RLHFlags.RESUME)

        # Set ECN flag
        header.set_flag(RLHFlags.ECN)
        assert header.has_flag(RLHFlags.ECN)
        assert not header.has_flag(RLHFlags.RESUME)

        # Set another flag
        header.set_flag(RLHFlags.RESUME)
        assert header.has_flag(RLHFlags.ECN)
        assert header.has_flag(RLHFlags.RESUME)

        # Clear ECN flag
        header.clear_flag(RLHFlags.ECN)
        assert not header.has_flag(RLHFlags.ECN)
        assert header.has_flag(RLHFlags.RESUME)

    def test_pack_unpack(self):
        """Test header packing and unpacking."""
        original = RLHHeader.create(
            dst_router_id=self.test_uuid,
            egress_agent_id=12345,
            qos=QoS.SILVER,
            ttl=42,
            budget_tokens=50000,
            budget_usd_micros=75000,
            flags=RLHFlags.ECN.value,
            hmac_key=self.hmac_key,
        )

        # Pack
        packed = original.pack()
        assert len(packed) == RLHHeader.HEADER_SIZE

        # Unpack
        unpacked = RLHHeader.unpack(packed)

        # Verify all fields match
        assert unpacked.dst_router_id == original.dst_router_id
        assert unpacked.egress_agent_id == original.egress_agent_id
        assert unpacked.qos == original.qos
        assert unpacked.ttl == original.ttl
        assert unpacked.budget_tokens == original.budget_tokens
        assert unpacked.budget_usd_micros == original.budget_usd_micros
        assert unpacked.flags == original.flags
        assert unpacked.hmac == original.hmac

    def test_pack_unpack_invalid_size(self):
        """Test unpacking with invalid data size."""
        with pytest.raises(ValueError, match="Invalid RLH header size"):
            RLHHeader.unpack(b"too-short")

    def test_pack_unpack_invalid_qos(self):
        """Test unpacking with invalid QoS byte."""
        # Create header with invalid QoS
        header = RLHHeader.create(
            dst_router_id=self.test_uuid,
            egress_agent_id=12345,
            qos=QoS.GOLD,
            ttl=64,
            budget_tokens=100000,
            budget_usd_micros=1000000,
        )

        # Manually corrupt the QoS byte in packed data
        packed = header.pack()
        corrupted = packed[:24] + b"x" + packed[25:]  # Invalid QoS byte at position 24

        with pytest.raises(ValueError, match="Invalid QoS byte"):
            RLHHeader.unpack(corrupted)

    def test_to_dict_from_dict(self):
        """Test dictionary serialization."""
        original = RLHHeader.create(
            dst_router_id=self.test_uuid,
            egress_agent_id=12345,
            qos=QoS.BRONZE,
            ttl=32,
            budget_tokens=25000,
            budget_usd_micros=50000,
            flags=RLHFlags.FRAG.value | RLHFlags.RESUME.value,
            hmac_key=self.hmac_key,
        )

        # Convert to dict
        data = original.to_dict()

        # Convert back from dict
        restored = RLHHeader.from_dict(data)

        # Verify all fields match
        assert restored.dst_router_id == original.dst_router_id
        assert restored.egress_agent_id == original.egress_agent_id
        assert restored.qos == original.qos
        assert restored.ttl == original.ttl
        assert restored.budget_tokens == original.budget_tokens
        assert restored.budget_usd_micros == original.budget_usd_micros
        assert restored.flags == original.flags
        assert restored.hmac == original.hmac


class TestRLHEncapsulatedFrame:
    """Test cases for RLH encapsulated frames."""

    def setup_method(self):
        """Set up test fixtures."""
        self.test_uuid = "12345678-1234-5678-9012-123456789012"
        self.hmac_key = b"test-hmac-key-32-bytes-long-key!!"
        self.sample_frame = {
            "v": 1,
            "session_id": "session-123",
            "stream_id": "stream-456",
            "msg_seq": 1,
            "frag_seq": 0,
            "flags": [],
            "qos": "gold",
            "ttl": 64,
            "window": {"max_parallel": 10, "max_tokens": 1000, "max_usd_micros": 10000},
            "meta": {"task_type": "completion"},
            "payload": {"type": "text", "content": "Hello world"},
            "sig": "signature123",
        }

    def test_frame_encapsulation(self):
        """Test frame encapsulation with RLH."""
        header = RLHHeader.create(
            dst_router_id=self.test_uuid,
            egress_agent_id=12345,
            qos=QoS.GOLD,
            ttl=64,
            budget_tokens=100000,
            budget_usd_micros=1000000,
            hmac_key=self.hmac_key,
        )

        encapsulated = RLHEncapsulatedFrame(rlh_header=header, atp_frame=self.sample_frame)

        assert encapsulated.rlh_header == header
        assert encapsulated.atp_frame == self.sample_frame

    def test_pack_unpack_frame(self):
        """Test encapsulated frame packing and unpacking."""
        header = RLHHeader.create(
            dst_router_id=self.test_uuid,
            egress_agent_id=12345,
            qos=QoS.GOLD,
            ttl=64,
            budget_tokens=100000,
            budget_usd_micros=1000000,
            hmac_key=self.hmac_key,
        )

        original = RLHEncapsulatedFrame(rlh_header=header, atp_frame=self.sample_frame)

        # Pack
        packed = original.pack()

        # Unpack
        unpacked = RLHEncapsulatedFrame.unpack(packed)

        # Verify header
        assert unpacked.rlh_header.dst_router_id == original.rlh_header.dst_router_id
        assert unpacked.rlh_header.egress_agent_id == original.rlh_header.egress_agent_id
        assert unpacked.rlh_header.qos == original.rlh_header.qos
        assert unpacked.rlh_header.ttl == original.rlh_header.ttl
        assert unpacked.rlh_header.budget_tokens == original.rlh_header.budget_tokens
        assert unpacked.rlh_header.budget_usd_micros == original.rlh_header.budget_usd_micros

        # Verify ATP frame
        assert unpacked.atp_frame == original.atp_frame

    def test_unpack_invalid_data(self):
        """Test unpacking with insufficient data."""
        with pytest.raises(ValueError, match="Data too short for RLH header"):
            RLHEncapsulatedFrame.unpack(b"short")


class TestRLHProcessor:
    """Test cases for RLH processor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.router_id = "12345678-1234-5678-9012-123456789012"
        self.hmac_key = b"test-hmac-key-32-bytes-long-key!!"
        self.processor = RLHProcessor(self.router_id, self.hmac_key)

        self.sample_frame = {
            "v": 1,
            "session_id": "session-123",
            "stream_id": "stream-456",
            "msg_seq": 1,
            "payload": {"type": "text", "content": "Hello world"},
        }

    def test_encapsulate_frame(self):
        """Test frame encapsulation."""
        encapsulated = self.processor.encapsulate_frame(
            atp_frame=self.sample_frame,
            dst_router_id="87654321-4321-8765-2109-876543210987",
            egress_agent_id=12345,
            qos=QoS.GOLD,
            initial_budget_tokens=100000,
            initial_budget_usd_micros=1000000,
            ttl=64,
        )

        assert encapsulated.rlh_header.dst_router_id == "87654321-4321-8765-2109-876543210987"
        assert encapsulated.rlh_header.egress_agent_id == 12345
        assert encapsulated.rlh_header.qos == QoS.GOLD
        assert encapsulated.rlh_header.ttl == 64
        assert encapsulated.rlh_header.budget_tokens == 100000
        assert encapsulated.rlh_header.budget_usd_micros == 1000000
        assert encapsulated.atp_frame == self.sample_frame

    def test_process_incoming_frame_for_this_router(self):
        """Test processing frame destined for this router."""
        # Create frame destined for this router
        encapsulated = self.processor.encapsulate_frame(
            atp_frame=self.sample_frame,
            dst_router_id=self.router_id,  # Destined for this router
            egress_agent_id=12345,
            qos=QoS.GOLD,
            initial_budget_tokens=100000,
            initial_budget_usd_micros=1000000,
        )

        result = self.processor.process_incoming_frame(encapsulated)

        # Should return the encapsulated frame (egress processing)
        assert result is not None
        assert result.rlh_header.dst_router_id == self.router_id

    def test_process_incoming_frame_for_other_router(self):
        """Test processing frame destined for another router."""
        # Get initial counter value
        initial_stats = self.processor.get_stats()
        initial_forwarded = initial_stats["rlh_forwarded"]

        # Create frame destined for another router
        encapsulated = self.processor.encapsulate_frame(
            atp_frame=self.sample_frame,
            dst_router_id="87654321-4321-8765-2109-876543210999",  # Not this router
            egress_agent_id=12345,
            qos=QoS.GOLD,
            initial_budget_tokens=100000,
            initial_budget_usd_micros=1000000,
        )

        result = self.processor.process_incoming_frame(encapsulated)

        # Should return the frame for forwarding
        assert result is not None
        assert result.rlh_header.dst_router_id == "87654321-4321-8765-2109-876543210999"

        # Should increment forwarded counter by 1
        final_stats = self.processor.get_stats()
        assert final_stats["rlh_forwarded"] == initial_forwarded + 1

    def test_forward_frame_success(self):
        """Test successful frame forwarding."""
        encapsulated = self.processor.encapsulate_frame(
            atp_frame=self.sample_frame,
            dst_router_id="abcd1234-5678-9012-3456-789012345678",
            egress_agent_id=12345,
            qos=QoS.GOLD,
            initial_budget_tokens=10000,
            initial_budget_usd_micros=20000,
            ttl=5,
        )

        result = self.processor.forward_frame(
            encapsulated_frame=encapsulated,
            next_hop_router_id="fedcba98-7654-3210-fedc-ba9876543210",
            payload_tokens=1000,
            payload_usd_micros=2000,
        )

        assert result is not None
        assert result.rlh_header.ttl == 4  # Decremented
        assert result.rlh_header.budget_tokens == 9980  # Decremented by overhead (20 tokens)
        assert result.rlh_header.budget_usd_micros == 19960  # Decremented by overhead (40 micros)
        assert result.rlh_header.dst_router_id == "fedcba98-7654-3210-fedc-ba9876543210"  # Updated

        # Should increment forwarded counter
        stats = self.processor.get_stats()
        assert stats["rlh_forwarded"] >= 1

    def test_forward_frame_ttl_expiry(self):
        """Test frame drop due to TTL expiry."""
        # Get initial counter value
        initial_stats = self.processor.get_stats()
        initial_dropped_ttl = initial_stats["rlh_dropped_ttl"]

        encapsulated = self.processor.encapsulate_frame(
            atp_frame=self.sample_frame,
            dst_router_id="abcd1234-5678-9012-3456-789012345678",
            egress_agent_id=12345,
            qos=QoS.GOLD,
            initial_budget_tokens=10000,
            initial_budget_usd_micros=20000,
            ttl=1,  # Will expire
        )

        result = self.processor.forward_frame(
            encapsulated_frame=encapsulated,
            next_hop_router_id="final-router",
            payload_tokens=1000,
            payload_usd_micros=2000,
        )

        # Should return None (dropped)
        assert result is None

        # Should increment TTL drop counter by 1
        final_stats = self.processor.get_stats()
        assert final_stats["rlh_dropped_ttl"] == initial_dropped_ttl + 1

    def test_forward_frame_budget_exhaustion(self):
        # Get initial counter value
        initial_stats = self.processor.get_stats()
        initial_dropped_budget = initial_stats["rlh_dropped_budget"]

        encapsulated = self.processor.encapsulate_frame(
            atp_frame=self.sample_frame,
            dst_router_id="abcd1234-5678-9012-3456-789012345678",
            egress_agent_id=12345,
            qos=QoS.GOLD,
            initial_budget_tokens=15,  # Low budget that will be exhausted by overhead
            initial_budget_usd_micros=1000,
            ttl=10,
        )

        result = self.processor.forward_frame(
            encapsulated_frame=encapsulated,
            next_hop_router_id="fedcba98-7654-3210-fedc-ba9876543210",
            payload_tokens=1000,  # More than available
            payload_usd_micros=2000,
        )

        # Should return None (dropped)
        assert result is None

        # Should increment budget drop counter by 1
        final_stats = self.processor.get_stats()
        assert final_stats["rlh_dropped_budget"] == initial_dropped_budget + 1

    def test_forward_frame_with_congestion(self):
        # Get initial counter value
        initial_stats = self.processor.get_stats()
        initial_ecn_marked = initial_stats["rlh_ecn_marked"]

        encapsulated = self.processor.encapsulate_frame(
            atp_frame=self.sample_frame,
            dst_router_id="abcd1234-5678-9012-3456-789012345678",
            egress_agent_id=12345,
            qos=QoS.GOLD,
            initial_budget_tokens=10000,
            initial_budget_usd_micros=20000,
            ttl=5,
        )

        result = self.processor.forward_frame(
            encapsulated_frame=encapsulated,
            next_hop_router_id="fedcba98-7654-3210-fedc-ba9876543210",
            payload_tokens=1000,
            payload_usd_micros=2000,
            congestion_detected=True,  # Congestion detected
        )

        assert result is not None
        assert result.rlh_header.has_flag(RLHFlags.ECN)  # ECN flag should be set

        # Should increment ECN marked counter by 1
        final_stats = self.processor.get_stats()
        assert final_stats["rlh_ecn_marked"] == initial_ecn_marked + 1

    def test_get_stats(self):
        stats = self.processor.get_stats()

        expected_keys = ["rlh_forwarded", "rlh_dropped_ttl", "rlh_dropped_budget", "rlh_ecn_marked"]
        for key in expected_keys:
            assert key in stats
            assert isinstance(stats[key], (int, float))


if __name__ == "__main__":
    pytest.main([__file__])
