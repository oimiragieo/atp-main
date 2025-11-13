"""Tests for GAP-341: Observation curation job (dedupe + safety filter)."""

import json
import os
import tempfile

from metrics.registry import REGISTRY
from router_service.observation_curator import MinHashDeduper, ObservationCurator, SafetyFilter


class TestMinHashDeduper:
    """Test MinHash deduplication functionality."""

    def test_minhash_signature_generation(self):
        """Test that MinHash signatures are generated correctly."""
        deduper = MinHashDeduper(num_hashes=10)

        sig1 = deduper._minhash_signature("test text")
        sig2 = deduper._minhash_signature("test text")
        sig3 = deduper._minhash_signature("different text")

        assert len(sig1) == 10
        assert sig1 == sig2  # Same text should produce same signature
        assert sig1 != sig3  # Different text should produce different signature

    def test_find_duplicates(self):
        """Test duplicate detection."""
        deduper = MinHashDeduper(num_hashes=10)

        observations = [
            {"prompt_hash": "abc123", "task_type": "test", "ts": 1000},
            {"prompt_hash": "abc123", "task_type": "test", "ts": 1001},  # Duplicate
            {"prompt_hash": "def456", "task_type": "other", "ts": 1002},  # Different
        ]

        duplicates = deduper.find_duplicates(observations)

        # Should find at least one duplicate group
        assert len(duplicates) >= 1

        # Check that duplicates are correctly identified
        for bucket_obs in duplicates.values():
            assert len(bucket_obs) > 1

    def test_deduplicate(self):
        """Test deduplication removes duplicates."""
        deduper = MinHashDeduper(num_hashes=10)

        observations = [
            {"prompt_hash": "abc123", "task_type": "test", "ts": 1000},
            {"prompt_hash": "abc123", "task_type": "test", "ts": 1001},  # Duplicate
            {"prompt_hash": "def456", "task_type": "other", "ts": 1002},  # Different
        ]

        original_count = len(observations)
        deduplicated = deduper.deduplicate(observations)

        assert len(deduplicated) < original_count
        assert len(deduplicated) >= 1  # Should keep at least one

    def test_dedup_metrics_update(self):
        """Test that deduplication metrics are updated."""
        deduper = MinHashDeduper()

        # Reset metric
        REGISTRY.gauge("slm_observation_dedup_ratio").set(0)

        observations = [
            {"prompt_hash": "abc123", "task_type": "test", "ts": 1000},
            {"prompt_hash": "abc123", "task_type": "test", "ts": 1001},  # Duplicate
        ]

        deduper.deduplicate(observations)

        # Metric should be updated (0.5 for 2 observations with 1 duplicate)
        ratio = REGISTRY.gauge("slm_observation_dedup_ratio")._value
        assert ratio > 0


class TestSafetyFilter:
    """Test safety filtering functionality."""

    def test_safe_observation(self):
        """Test that safe observations pass the filter."""
        safety_filter = SafetyFilter()

        safe_obs = {"prompt_hash": "abc123", "task_type": "test", "response": "This is a safe response"}

        assert safety_filter.is_safe(safe_obs)

    def test_unsafe_observation(self):
        """Test that unsafe observations are filtered out."""
        safety_filter = SafetyFilter()

        unsafe_obs = {"prompt_hash": "abc123", "task_type": "test", "response": "My password is secret123"}

        assert not safety_filter.is_safe(unsafe_obs)

    def test_filter_unsafe(self):
        """Test filtering unsafe observations from a list."""
        safety_filter = SafetyFilter()

        observations = [
            {"response": "Safe content"},
            {"response": "Contains password: secret"},
            {"response": "More safe content"},
        ]

        filtered = safety_filter.filter_unsafe(observations)

        assert len(filtered) == 2  # Should filter out the unsafe one
        assert all(obs["response"] != "Contains password: secret" for obs in filtered)


class TestObservationCurator:
    """Test the main observation curator."""

    def test_curate_observations(self):
        """Test full curation pipeline."""
        curator = ObservationCurator()

        observations = [
            # Safe, unique
            {"prompt_hash": "abc123", "task_type": "test1", "ts": 1000, "response": "Safe content"},
            # Duplicate of first
            {"prompt_hash": "abc123", "task_type": "test1", "ts": 1001, "response": "Safe content"},
            # Unsafe
            {"prompt_hash": "def456", "task_type": "test2", "ts": 1002, "response": "Contains password"},
            # Safe, unique
            {"prompt_hash": "ghi789", "task_type": "test3", "ts": 1003, "response": "More safe content"},
        ]

        curated = curator.curate_observations(observations)

        # Should have 2 observations left (duplicates and unsafe filtered)
        assert len(curated) == 2

    def test_process_file(self):
        """Test file processing functionality."""
        curator = ObservationCurator()

        # Create test input file
        observations = [
            {"prompt_hash": "abc123", "task_type": "test", "ts": 1000},
            {"prompt_hash": "abc123", "task_type": "test", "ts": 1001},  # Duplicate
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            input_file = os.path.join(temp_dir, "input.jsonl")
            output_file = os.path.join(temp_dir, "output.jsonl")

            # Write test data
            with open(input_file, "w") as f:
                for obs in observations:
                    f.write(json.dumps(obs) + "\n")

            # Process file
            stats = curator.process_file(input_file, output_file)

            # Check results
            assert stats["original_count"] == 2
            assert stats["curated_count"] == 1  # One duplicate removed
            assert stats["duplicates_removed"] == 1
            assert os.path.exists(output_file)

            # Verify output file
            with open(output_file) as f:
                lines = f.readlines()
                assert len(lines) == 1
