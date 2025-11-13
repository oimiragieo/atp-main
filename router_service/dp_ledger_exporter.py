#!/usr/bin/env python3
"""GAP-369: Differential Privacy Ledger Exporter

Exports sanitized differential privacy events to a tamper-evident ledger format.
Ensures privacy budget compliance and provides cryptographic integrity for audit trails.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from metrics.registry import REGISTRY

logger = logging.getLogger(__name__)

# GAP-369: DP Ledger metrics
DP_LEDGER_EXPORTS_TOTAL = REGISTRY.counter("dp_ledger_exports_total")
DP_LEDGER_ENTRIES_TOTAL = REGISTRY.counter("dp_ledger_entries_total")
DP_LEDGER_BUDGET_EXCEEDED_TOTAL = REGISTRY.counter("dp_ledger_budget_exceeded_total")


@dataclass
class DpLedgerEntry:
    """A differentially private ledger entry with integrity protection."""

    entry_id: str
    tenant_id: str
    event_type: str
    timestamp: datetime
    dp_value: float
    epsilon_used: float
    sensitivity: float
    sequence_number: int
    previous_hash: str
    metadata: Optional[dict[str, Any]] = None

    def to_dict(self, include_hash: bool = True) -> dict[str, Any]:
        """Convert entry to dictionary for serialization."""
        result = {
            "entry_id": self.entry_id,
            "tenant_id": self.tenant_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "dp_value": self.dp_value,
            "epsilon_used": self.epsilon_used,
            "sensitivity": self.sensitivity,
            "sequence_number": self.sequence_number,
            "previous_hash": self.previous_hash
        }

        if self.metadata:
            result["metadata"] = self.metadata

        if include_hash:
            result["entry_hash"] = self.compute_hash()

        return result

    def compute_hash(self) -> str:
        """Compute cryptographic hash of the entry for integrity."""
        # Create canonical representation for hashing
        canonical_data = {
            "entry_id": self.entry_id,
            "tenant_id": self.tenant_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "dp_value": round(self.dp_value, 6),  # Round for consistent hashing
            "epsilon_used": round(self.epsilon_used, 6),
            "sensitivity": round(self.sensitivity, 6),
            "sequence_number": self.sequence_number,
            "previous_hash": self.previous_hash
        }

        if self.metadata:
            # Sort metadata keys for consistent hashing
            canonical_data["metadata"] = {k: self.metadata[k] for k in sorted(self.metadata.keys())}

        # Serialize to JSON with sorted keys for deterministic hashing
        canonical_json = json.dumps(canonical_data, sort_keys=True, separators=(',', ':'))

        # Compute SHA-256 hash
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'DpLedgerEntry':
        """Create entry from dictionary representation."""
        return cls(
            entry_id=data["entry_id"],
            tenant_id=data["tenant_id"],
            event_type=data["event_type"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            dp_value=data["dp_value"],
            epsilon_used=data["epsilon_used"],
            sensitivity=data["sensitivity"],
            sequence_number=data["sequence_number"],
            previous_hash=data["previous_hash"],
            metadata=data.get("metadata")
        )


class DpLedgerExporter:
    """Exports differentially private events to a tamper-evident ledger."""

    def __init__(self,
                 ledger_path: str = "./dp_ledger",
                 max_epsilon_per_tenant: float = 2.0,
                 hmac_key: Optional[bytes] = None):
        self.ledger_path = Path(ledger_path)
        self.ledger_path.mkdir(exist_ok=True)
        self.max_epsilon_per_tenant = max_epsilon_per_tenant
        self.hmac_key = hmac_key or self._generate_key()

        # Track tenant epsilon usage
        self.tenant_epsilon_usage: dict[str, float] = {}

        # Ledger state
        self.current_sequence = 0
        self.last_hash = "0" * 64  # Genesis hash

        # Load existing ledger state if available
        self._load_ledger_state()

    def _generate_key(self) -> bytes:
        """Generate a random HMAC key for integrity protection."""
        return hashlib.sha256(str(datetime.now().timestamp()).encode()).digest()

    def _load_ledger_state(self):
        """Load existing ledger state from disk."""
        ledger_file = self.ledger_path / "ledger.jsonl"

        if not ledger_file.exists():
            return

        try:
            with open(ledger_file, encoding='utf-8') as f:
                lines = f.readlines()

            if lines:
                # Load the last entry to get current state
                last_line = lines[-1].strip()
                if last_line:
                    last_entry_data = json.loads(last_line)
                    self.current_sequence = last_entry_data["sequence_number"]
                    self.last_hash = last_entry_data.get("entry_hash", self.last_hash)

                    # Rebuild epsilon usage from ledger
                    for line in lines:
                        entry_data = json.loads(line.strip())
                        tenant_id = entry_data["tenant_id"]
                        epsilon_used = entry_data["epsilon_used"]
                        self.tenant_epsilon_usage[tenant_id] = (
                            self.tenant_epsilon_usage.get(tenant_id, 0.0) + epsilon_used
                        )

            logger.info(f"Loaded ledger state: {self.current_sequence} entries, last hash: {self.last_hash[:16]}...")

        except Exception as e:
            logger.error(f"Failed to load ledger state: {e}")
            # Reset to clean state on error
            self.current_sequence = 0
            self.last_hash = "0" * 64

    def add_entry(self,
                  tenant_id: str,
                  event_type: str,
                  dp_value: float,
                  epsilon_used: float,
                  sensitivity: float,
                  metadata: Optional[dict[str, Any]] = None) -> bool:
        """Add a DP event to the ledger, checking budget compliance."""

        # Check privacy budget
        current_usage = self.tenant_epsilon_usage.get(tenant_id, 0.0)
        if current_usage + epsilon_used > self.max_epsilon_per_tenant:
            logger.warning(
                f"Privacy budget exceeded for tenant {tenant_id}: "
                f"current={current_usage:.3f}, requested={epsilon_used:.3f}, "
                f"limit={self.max_epsilon_per_tenant:.3f}"
            )
            DP_LEDGER_BUDGET_EXCEEDED_TOTAL.inc()
            return False

        # Create new ledger entry
        self.current_sequence += 1
        entry = DpLedgerEntry(
            entry_id=f"dp_{tenant_id}_{self.current_sequence:08d}",
            tenant_id=tenant_id,
            event_type=event_type,
            timestamp=datetime.now(),
            dp_value=dp_value,
            epsilon_used=epsilon_used,
            sensitivity=sensitivity,
            sequence_number=self.current_sequence,
            previous_hash=self.last_hash,
            metadata=metadata
        )

        # Compute and update hash chain
        entry_hash = entry.compute_hash()
        self.last_hash = entry_hash

        # Update epsilon usage
        self.tenant_epsilon_usage[tenant_id] = current_usage + epsilon_used

        # Append to ledger
        self._append_to_ledger(entry)

        DP_LEDGER_ENTRIES_TOTAL.inc()
        logger.info(f"Added ledger entry {entry.entry_id} for tenant {tenant_id}")

        return True

    def _append_to_ledger(self, entry: DpLedgerEntry):
        """Append entry to the ledger file."""
        ledger_file = self.ledger_path / "ledger.jsonl"

        with open(ledger_file, 'a', encoding='utf-8') as f:
            entry_data = entry.to_dict(include_hash=True)
            json.dump(entry_data, f, ensure_ascii=False)
            f.write('\n')

    def export_ledger(self, format_type: str = "jsonl") -> str:
        """Export the current ledger state."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_file = self.ledger_path / f"ledger_export_{timestamp}.{format_type}"

        if format_type == "jsonl":
            # Copy the current ledger file
            ledger_file = self.ledger_path / "ledger.jsonl"
            if ledger_file.exists():
                with open(ledger_file, encoding='utf-8') as src:
                    with open(export_file, 'w', encoding='utf-8') as dst:
                        dst.write(src.read())
            else:
                # Create empty export
                export_file.touch()

        elif format_type == "json":
            # Export as JSON array
            ledger_file = self.ledger_path / "ledger.jsonl"
            entries = []

            if ledger_file.exists():
                with open(ledger_file, encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            entries.append(json.loads(line.strip()))

            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "export_timestamp": datetime.now().isoformat(),
                    "total_entries": len(entries),
                    "ledger_integrity": self._verify_ledger_integrity(),
                    "entries": entries
                }, f, indent=2, ensure_ascii=False)

        else:
            raise ValueError(f"Unsupported export format: {format_type}")

        DP_LEDGER_EXPORTS_TOTAL.inc()
        logger.info(f"Exported ledger to {export_file}")
        return str(export_file)

    def _verify_ledger_integrity(self) -> dict[str, Any]:
        """Verify the integrity of the ledger hash chain."""
        ledger_file = self.ledger_path / "ledger.jsonl"

        if not ledger_file.exists():
            return {"valid": True, "entries_checked": 0, "corrupt_entries": 0}

        corrupt_count = 0
        expected_hash = "0" * 64
        entries_checked = 0

        try:
            with open(ledger_file, encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue

                    entry_data = json.loads(line.strip())
                    entries_checked += 1

                    # Verify hash chain
                    if entry_data["previous_hash"] != expected_hash:
                        corrupt_count += 1
                        logger.error(f"Hash chain broken at entry {entry_data['entry_id']}")

                    # Recompute hash to verify integrity
                    temp_entry = DpLedgerEntry.from_dict(entry_data)
                    computed_hash = temp_entry.compute_hash()

                    if computed_hash != entry_data.get("entry_hash"):
                        corrupt_count += 1
                        logger.error(f"Hash mismatch at entry {entry_data['entry_id']}")

                    expected_hash = entry_data.get("entry_hash", computed_hash)

        except Exception as e:
            logger.error(f"Ledger integrity check failed: {e}")
            return {"valid": False, "entries_checked": entries_checked, "corrupt_entries": corrupt_count, "error": str(e)}

        return {
            "valid": corrupt_count == 0,
            "entries_checked": entries_checked,
            "corrupt_entries": corrupt_count
        }

    def get_budget_status(self, tenant_id: str) -> dict[str, float]:
        """Get privacy budget status for a tenant."""
        used = self.tenant_epsilon_usage.get(tenant_id, 0.0)
        remaining = max(0.0, self.max_epsilon_per_tenant - used)

        return {
            "tenant_id": tenant_id,
            "epsilon_used": used,
            "epsilon_remaining": remaining,
            "epsilon_limit": self.max_epsilon_per_tenant,
            "utilization_rate": used / self.max_epsilon_per_tenant if self.max_epsilon_per_tenant > 0 else 0.0
        }

    def get_ledger_stats(self) -> dict[str, Any]:
        """Get statistics about the ledger."""
        integrity = self._verify_ledger_integrity()

        return {
            "total_entries": self.current_sequence,
            "ledger_integrity": integrity,
            "active_tenants": len(self.tenant_epsilon_usage),
            "total_epsilon_used": sum(self.tenant_epsilon_usage.values()),
            "last_hash": self.last_hash
        }


# Global ledger exporter instance
_dp_ledger_exporter: Optional[DpLedgerExporter] = None


def get_dp_ledger_exporter() -> Optional[DpLedgerExporter]:
    """Get the global DP ledger exporter instance."""
    return _dp_ledger_exporter


def initialize_dp_ledger_exporter(ledger_path: str = "./dp_ledger",
                                max_epsilon_per_tenant: float = 2.0) -> DpLedgerExporter:
    """Initialize the global DP ledger exporter."""
    global _dp_ledger_exporter
    _dp_ledger_exporter = DpLedgerExporter(ledger_path, max_epsilon_per_tenant)
    return _dp_ledger_exporter
