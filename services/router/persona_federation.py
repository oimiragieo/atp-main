"""GAP-116C: Federation schema for persona statistics."""

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from router_service.reputation_model import ReputationModel

try:
    from metrics.registry import REGISTRY
except ImportError:
    REGISTRY = None


@dataclass
class PersonaStats:
    """Federated persona statistics data structure."""

    persona_id: str
    reputation_score: float
    reliability_score: float
    sample_count: int
    last_updated: float
    router_origin: str
    constraints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "persona_id": self.persona_id,
            "reputation_score": self.reputation_score,
            "reliability_score": self.reliability_score,
            "sample_count": self.sample_count,
            "last_updated": self.last_updated,
            "router_origin": self.router_origin,
            "constraints": self.constraints,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PersonaStats":
        """Create from dictionary."""
        return cls(
            persona_id=data["persona_id"],
            reputation_score=data["reputation_score"],
            reliability_score=data["reliability_score"],
            sample_count=data["sample_count"],
            last_updated=data["last_updated"],
            router_origin=data["router_origin"],
            constraints=data.get("constraints", {}),
        )


@dataclass
class SignedPersonaStats:
    """Signed persona statistics for federation."""

    stats: PersonaStats
    origin_router: str
    timestamp: float
    signature: str
    sequence_number: int


class PersonaFederationNode:
    """Router node that participates in persona statistics federation."""

    def __init__(self, router_name: str, signing_key: bytes):
        self.router_name = router_name
        self.signing_key = signing_key
        self.local_stats: dict[str, PersonaStats] = {}
        self.federated_stats: dict[str, list[SignedPersonaStats]] = {}
        self.sequence_counters: dict[str, int] = {}

    def create_signed_stats(
        self, persona_id: str, reputation_model: ReputationModel, constraints: Optional[dict[str, Any]] = None
    ) -> Optional[SignedPersonaStats]:
        """Create signed persona statistics for federation."""
        stats = reputation_model.get_persona_stats(persona_id)
        if not stats or stats["reputation_score"] is None:
            return None

        persona_stats = PersonaStats(
            persona_id=persona_id,
            reputation_score=stats["reputation_score"],
            reliability_score=stats.get("reliability_score", 0.0),
            sample_count=stats["sample_count"],
            last_updated=time.time(),
            router_origin=self.router_name,
            constraints=constraints or {},
        )

        self.local_stats[persona_id] = persona_stats

        seq_num = self.sequence_counters.get(persona_id, 0) + 1
        self.sequence_counters[persona_id] = seq_num

        payload = self._create_signature_payload(persona_stats, seq_num)
        signature = self._sign_payload(payload)

        return SignedPersonaStats(
            stats=persona_stats,
            origin_router=self.router_name,
            timestamp=persona_stats.last_updated,
            signature=signature,
            sequence_number=seq_num,
        )

    def validate_signed_stats(
        self, signed_stats: SignedPersonaStats, router_key: bytes, max_age_seconds: int = 3600
    ) -> bool:
        """Validate signed persona statistics."""
        if time.time() - signed_stats.timestamp > max_age_seconds:
            return False

        payload = self._create_signature_payload(signed_stats.stats, signed_stats.sequence_number)
        expected_sig = self._sign_payload_with_key(payload, router_key)

        return hmac.compare_digest(signed_stats.signature, expected_sig)

    def ingest_federated_stats(self, signed_stats: SignedPersonaStats, router_key: bytes) -> bool:
        """Ingest federated persona statistics with conflict resolution."""
        if not self.validate_signed_stats(signed_stats, router_key):
            return False

        persona_id = signed_stats.stats.persona_id

        if persona_id not in self.federated_stats:
            self.federated_stats[persona_id] = []

        existing_stats = self.federated_stats[persona_id]

        conflict_resolution = self._resolve_conflicts(signed_stats, existing_stats)

        if conflict_resolution["action"] == "accept":
            self.federated_stats[persona_id] = [
                s
                for s in existing_stats
                if not (
                    s.origin_router == signed_stats.origin_router and s.sequence_number < signed_stats.sequence_number
                )
            ]
            self.federated_stats[persona_id].append(signed_stats)
            # Increment federated persona updates metric
            if REGISTRY:
                REGISTRY.counter("federated_persona_updates_total").inc()
            return True
        elif conflict_resolution["action"] == "merge":
            merged_stats = self._merge_stats(signed_stats, existing_stats)
            if merged_stats:
                self.federated_stats[persona_id].append(merged_stats)
                # Increment federated persona updates metric
                if REGISTRY:
                    REGISTRY.counter("federated_persona_updates_total").inc()
            return True

        return False

    def get_consolidated_stats(self, persona_id: str) -> Optional[PersonaStats]:
        """Get consolidated persona statistics from all federated sources."""
        if persona_id not in self.federated_stats:
            return self.local_stats.get(persona_id)

        federated = self.federated_stats[persona_id]
        if not federated:
            return self.local_stats.get(persona_id)

        best_signed = self._select_best_stats(federated)
        if best_signed:
            return best_signed.stats

        return self.local_stats.get(persona_id)

    def _create_signature_payload(self, stats: PersonaStats, seq_num: int) -> str:
        """Create signature payload string."""
        return (
            f"{stats.persona_id}|"
            f"{stats.reputation_score:.6f}|"
            f"{stats.reliability_score:.6f}|"
            f"{stats.sample_count}|"
            f"{int(stats.last_updated)}|"
            f"{stats.router_origin}|"
            f"{seq_num}"
        )

    def _sign_payload(self, payload: str) -> str:
        """Sign payload with node's key."""
        return hmac.new(self.signing_key, payload.encode(), hashlib.sha256).hexdigest()

    def _sign_payload_with_key(self, payload: str, key: bytes) -> str:
        """Sign payload with provided key."""
        return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()

    def _resolve_conflicts(
        self, new_stats: SignedPersonaStats, existing_stats: list[SignedPersonaStats]
    ) -> dict[str, Any]:
        """Resolve conflicts between federated persona statistics."""
        if not existing_stats:
            return {"action": "accept"}

        same_router_stats = [s for s in existing_stats if s.origin_router == new_stats.origin_router]

        if same_router_stats:
            latest_same_router = max(same_router_stats, key=lambda s: s.sequence_number)
            if new_stats.sequence_number <= latest_same_router.sequence_number:
                return {"action": "reject", "reason": "stale_sequence"}

        recent_stats = [s for s in existing_stats if time.time() - s.timestamp < 3600]

        if recent_stats:
            avg_reputation = sum(s.stats.reputation_score for s in recent_stats) / len(recent_stats)

            reputation_diff = abs(new_stats.stats.reputation_score - avg_reputation)

            if reputation_diff > 0.3:
                return {"action": "merge", "reason": "significant_conflict", "conflict_score": reputation_diff}

        return {"action": "accept"}

    def _merge_stats(
        self, new_stats: SignedPersonaStats, existing_stats: list[SignedPersonaStats]
    ) -> Optional[SignedPersonaStats]:
        """Merge conflicting persona statistics."""
        total_samples = sum(s.stats.sample_count for s in existing_stats)
        total_samples += new_stats.stats.sample_count

        if total_samples == 0:
            return None

        weighted_reputation = sum(s.stats.reputation_score * s.stats.sample_count for s in existing_stats)
        weighted_reputation += new_stats.stats.reputation_score * new_stats.stats.sample_count

        weighted_reliability = sum(s.stats.reliability_score * s.stats.sample_count for s in existing_stats)
        weighted_reliability += new_stats.stats.reliability_score * new_stats.stats.sample_count

        merged = PersonaStats(
            persona_id=new_stats.stats.persona_id,
            reputation_score=weighted_reputation / total_samples,
            reliability_score=weighted_reliability / total_samples,
            sample_count=total_samples,
            last_updated=time.time(),
            router_origin="federated_merge",
            constraints={"merged": True},
        )

        seq_num = self.sequence_counters.get(merged.persona_id, 0) + 1
        self.sequence_counters[merged.persona_id] = seq_num

        payload = self._create_signature_payload(merged, seq_num)
        signature = self._sign_payload(payload)

        return SignedPersonaStats(
            stats=merged,
            origin_router=self.router_name,
            timestamp=merged.last_updated,
            signature=signature,
            sequence_number=seq_num,
        )

    def _select_best_stats(self, candidates: list[SignedPersonaStats]) -> Optional[SignedPersonaStats]:
        """Select the best persona statistics from candidates."""
        if not candidates:
            return None

        candidates.sort(key=lambda s: (s.timestamp, s.stats.sample_count), reverse=True)

        return candidates[0]
