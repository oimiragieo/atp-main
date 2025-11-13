"""Per-prefix billing record signing (GAP-109).

Provides signed billing records for per-prefix cost accounting with HMAC-SHA256
signatures using the existing KeyManager infrastructure from GAP-040.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from metrics.registry import REGISTRY

from .frame_sign import sign_frame_with_kid, verify_frame_with_km
from .key_manager import KeyManager

_CTR_BILLING_RECORDS_EMITTED = REGISTRY.counter("billing_records_emitted_total")


@dataclass
class BillingRecord:
    """Core billing record data structure."""

    tenant: str
    adapter: str
    prefix: str  # Per-prefix accounting
    in_tokens: int
    out_tokens: int
    usd_micros: int
    timestamp: int  # Unix timestamp in microseconds
    sequence: int  # Sequence number for ordering

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant": self.tenant,
            "adapter": self.adapter,
            "prefix": self.prefix,
            "in_tokens": self.in_tokens,
            "out_tokens": self.out_tokens,
            "usd_micros": self.usd_micros,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
        }


@dataclass
class SignedBillingRecord:
    """Signed billing record with HMAC signature and key ID."""

    record: BillingRecord
    signature: str
    kid: str

    @classmethod
    def create(
        cls,
        tenant: str,
        adapter: str,
        prefix: str,
        in_tokens: int,
        out_tokens: int,
        usd_micros: int,
        sequence: int,
        km: KeyManager,
        kid: str | None = None,
    ) -> SignedBillingRecord:
        """Create and sign a new billing record."""
        timestamp = int(time.time() * 1_000_000)  # microseconds
        record = BillingRecord(
            tenant=tenant,
            adapter=adapter,
            prefix=prefix,
            in_tokens=in_tokens,
            out_tokens=out_tokens,
            usd_micros=usd_micros,
            timestamp=timestamp,
            sequence=sequence,
        )

        record_dict = record.to_dict()
        signature = sign_frame_with_kid(record_dict, km, kid)
        kid_used = record_dict.get("kid", km.current_kid())

        _CTR_BILLING_RECORDS_EMITTED.inc(1)

        return cls(record=record, signature=signature, kid=kid_used)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization/storage."""
        result = self.record.to_dict()
        result["sig"] = self.signature
        result["kid"] = self.kid
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SignedBillingRecord:
        """Reconstruct from dictionary."""
        # Extract signature fields
        sig = data.pop("sig", "")
        kid = data.pop("kid", "")

        # Reconstruct record
        record = BillingRecord(**data)

        return cls(record=record, signature=sig, kid=kid)

    def verify(self, km: KeyManager) -> bool:
        """Verify the signature against the record."""
        record_dict = self.record.to_dict()
        record_dict["sig"] = self.signature
        record_dict["kid"] = self.kid
        return verify_frame_with_km(record_dict, km)


class BillingRecordSigner:
    """Manages signing and verification of billing records."""

    def __init__(self, km: KeyManager):
        self.km = km
        self.sequence_counter: dict[str, int] = {}  # per-tenant sequence

    def sign_record(
        self,
        tenant: str,
        adapter: str,
        prefix: str,
        in_tokens: int,
        out_tokens: int,
        usd_micros: int,
        kid: str | None = None,
    ) -> SignedBillingRecord:
        """Sign a billing record with automatic sequence numbering."""
        seq = self.sequence_counter.get(tenant, 0) + 1
        self.sequence_counter[tenant] = seq

        return SignedBillingRecord.create(
            tenant=tenant,
            adapter=adapter,
            prefix=prefix,
            in_tokens=in_tokens,
            out_tokens=out_tokens,
            usd_micros=usd_micros,
            sequence=seq,
            km=self.km,
            kid=kid,
        )

    def verify_record(self, signed_record: SignedBillingRecord) -> bool:
        """Verify a signed billing record."""
        return signed_record.verify(self.km)
