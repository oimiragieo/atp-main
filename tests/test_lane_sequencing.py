#!/usr/bin/env python3
"""Tests for lane-based msg_seq isolation (GAP-118)."""

from router_service.frame import Lane, LaneSequencer


class TestLane:
    """Test Lane abstraction."""

    def test_lane_creation(self):
        """Test lane creation and properties."""
        lane = Lane(persona_id="doctor-1", stream_id="stream-1")
        assert lane.persona_id == "doctor-1"
        assert lane.stream_id == "stream-1"

    def test_lane_equality(self):
        """Test lane equality."""
        lane1 = Lane(persona_id="doctor-1", stream_id="stream-1")
        lane2 = Lane(persona_id="doctor-1", stream_id="stream-1")
        lane3 = Lane(persona_id="lawyer-1", stream_id="stream-1")

        assert lane1 == lane2
        assert lane1 != lane3

    def test_lane_hash(self):
        """Test lane hashing."""
        lane1 = Lane(persona_id="doctor-1", stream_id="stream-1")
        lane2 = Lane(persona_id="doctor-1", stream_id="stream-1")

        assert hash(lane1) == hash(lane2)

    def test_lane_to_key(self):
        """Test lane key conversion."""
        lane = Lane(persona_id="doctor-1", stream_id="stream-1")
        assert lane.to_key() == "doctor-1:stream-1"


class TestLaneSequencer:
    """Test LaneSequencer functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.sequencer = LaneSequencer()

    def test_independent_sequencing(self):
        """Test that different lanes have independent msg_seq counters."""
        doctor_lane = Lane(persona_id="doctor-1", stream_id="stream-1")
        lawyer_lane = Lane(persona_id="lawyer-1", stream_id="stream-1")

        # Doctor lane sequences
        assert self.sequencer.get_next_msg_seq(doctor_lane) == 1
        assert self.sequencer.get_next_msg_seq(doctor_lane) == 2

        # Lawyer lane sequences independently
        assert self.sequencer.get_next_msg_seq(lawyer_lane) == 1
        assert self.sequencer.get_next_msg_seq(lawyer_lane) == 2

        # Doctor continues from where it left off
        assert self.sequencer.get_next_msg_seq(doctor_lane) == 3

    def test_get_current_msg_seq(self):
        """Test getting current msg_seq without incrementing."""
        lane = Lane(persona_id="doctor-1", stream_id="stream-1")

        assert self.sequencer.get_current_msg_seq(lane) == 0
        self.sequencer.get_next_msg_seq(lane)
        assert self.sequencer.get_current_msg_seq(lane) == 1

    def test_reset_lane(self):
        """Test resetting lane counter."""
        lane = Lane(persona_id="doctor-1", stream_id="stream-1")

        self.sequencer.get_next_msg_seq(lane)
        self.sequencer.get_next_msg_seq(lane)
        assert self.sequencer.get_current_msg_seq(lane) == 2

        self.sequencer.reset_lane(lane)
        assert self.sequencer.get_current_msg_seq(lane) == 0

    def test_get_active_lanes(self):
        """Test getting list of active lanes."""
        doctor_lane = Lane(persona_id="doctor-1", stream_id="stream-1")
        lawyer_lane = Lane(persona_id="lawyer-1", stream_id="stream-1")

        # Initially no active lanes
        assert self.sequencer.get_active_lanes() == []

        # After using lanes
        self.sequencer.get_next_msg_seq(doctor_lane)
        self.sequencer.get_next_msg_seq(lawyer_lane)

        active = self.sequencer.get_active_lanes()
        assert len(active) == 2
        assert "doctor-1:stream-1" in active
        assert "lawyer-1:stream-1" in active
