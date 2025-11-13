"""GAP-341: Observation curation job (dedupe + safety filter)."""

import hashlib
import json
from collections import defaultdict
from typing import Any

from metrics.registry import REGISTRY


class MinHashDeduper:
    """MinHash-based deduplication for SLM observations."""

    def __init__(self, num_hashes: int = 100, hash_size: int = 32):
        self.num_hashes = num_hashes
        self.hash_size = hash_size
        self._dedup_ratio = REGISTRY.gauge("slm_observation_dedup_ratio")

    def _minhash_signature(self, text: str) -> list[int]:
        """Generate MinHash signature for a text string."""
        # Simple implementation using multiple hash functions
        signature = []
        for i in range(self.num_hashes):
            # Use different seeds for each hash function
            hash_obj = hashlib.md5(f"{i}:{text}".encode())  # noqa: S324
            hash_int = int(hash_obj.hexdigest()[:8], 16)
            signature.append(hash_int % (2**self.hash_size))
        return signature

    def find_duplicates(self, observations: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Find duplicate observations using MinHash."""
        # Group observations by their MinHash signatures
        buckets = defaultdict(list)

        for obs in observations:
            # Create a signature from prompt_hash and key fields
            signature_key = f"{obs.get('prompt_hash', '')}:{obs.get('task_type', '')}"
            signature = self._minhash_signature(signature_key)
            # Use first few hash values as bucket key
            bucket_key = tuple(signature[:5])
            buckets[bucket_key].append(obs)

        # Filter to only buckets with duplicates
        duplicates = {k: v for k, v in buckets.items() if len(v) > 1}
        return duplicates

    def deduplicate(self, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove duplicates from observations list."""
        duplicates = self.find_duplicates(observations)

        # Keep only one observation per duplicate group (keep the most recent)
        to_remove = set()
        for bucket_obs in duplicates.values():
            # Sort by timestamp, keep the most recent
            sorted_obs = sorted(bucket_obs, key=lambda x: x.get("ts", 0), reverse=True)
            # Mark all but the first (most recent) for removal
            for obs in sorted_obs[1:]:
                to_remove.add(id(obs))

        # Filter out duplicates
        deduplicated = [obs for obs in observations if id(obs) not in to_remove]

        # Update metrics
        if observations:
            ratio = len(deduplicated) / len(observations)
            self._dedup_ratio.set(ratio)

        return deduplicated


class SafetyFilter:
    """Safety filter for SLM observations."""

    def __init__(self):
        # Define safety patterns to filter out
        self._unsafe_patterns = ["password", "secret", "token", "key", "credential"]

    def is_safe(self, observation: dict[str, Any]) -> bool:
        """Check if an observation passes safety filters."""
        # Check for sensitive data patterns
        text_content = json.dumps(observation, default=str).lower()

        for pattern in self._unsafe_patterns:
            if pattern in text_content:
                return False

        return True

    def filter_unsafe(self, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter out unsafe observations."""
        return [obs for obs in observations if self.is_safe(obs)]


class ObservationCurator:
    """Main observation curation job combining dedupe and safety filtering."""

    def __init__(self):
        self.deduper = MinHashDeduper()
        self.safety_filter = SafetyFilter()

    def curate_observations(self, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Run full curation pipeline: dedupe + safety filter."""
        # First deduplicate
        deduplicated = self.deduper.deduplicate(observations)

        # Then apply safety filter
        safe_observations = self.safety_filter.filter_unsafe(deduplicated)

        return safe_observations

    def process_file(self, input_file: str, output_file: str) -> dict[str, int]:
        """Process an observation file and write curated results."""
        observations = []

        # Read input file
        with open(input_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        obs = json.loads(line)
                        observations.append(obs)
                    except json.JSONDecodeError:
                        continue  # Skip malformed lines

        original_count = len(observations)

        # Curate observations
        curated = self.curate_observations(observations)

        # Write output file
        with open(output_file, "w") as f:
            for obs in curated:
                f.write(json.dumps(obs) + "\n")

        return {
            "original_count": original_count,
            "curated_count": len(curated),
            "duplicates_removed": original_count - len(self.deduper.deduplicate(observations)),
            "unsafe_filtered": len(self.deduper.deduplicate(observations)) - len(curated),
        }
