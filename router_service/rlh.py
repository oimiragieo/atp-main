#!/usr/bin/env python3
"""
Router Label Header (RLH) for AGP Data-Plane Encapsulation

Implements RLH header structure and budget decrement logic according to
AGP Federation Specification Section 9.
"""

from __future__ import annotations

import hashlib
import hmac
import statistics
import struct
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any

from metrics.registry import REGISTRY


@dataclass
class OverheadMeasurement:
    """Record of actual vs predicted overhead for telemetry."""

    timestamp: float
    predicted_tokens: int
    actual_tokens: int
    predicted_usd: int
    actual_usd: int


@dataclass
class OverheadModel:
    """Overhead model parameters for RLH budget decrement."""

    version: str = "1"
    alpha: float = 0.01  # Token overhead multiplier
    beta: int = 10  # Token overhead constant
    gamma: float = 0.02  # USD overhead multiplier
    delta: float = 0.00001  # USD overhead constant

    def calculate_overhead(self, payload_tokens: int, payload_usd_micros: int) -> tuple[int, int]:
        """Calculate overhead for given payload amounts."""
        overhead_tokens = int(self.alpha * payload_tokens + self.beta)
        overhead_usd_micros = int(self.gamma * payload_usd_micros + self.delta)
        return overhead_tokens, overhead_usd_micros

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "version": self.version,
            "alpha": self.alpha,
            "beta": self.beta,
            "gamma": self.gamma,
            "delta": self.delta,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OverheadModel:
        """Create from dictionary."""
        return cls(
            version=data.get("version", "1"),
            alpha=data.get("alpha", 0.01),
            beta=data.get("beta", 10),
            gamma=data.get("gamma", 0.02),
            delta=data.get("delta", 0.00001),
        )


class RLHFlags(Enum):
    """RLH header flags."""

    RESUME = 0x0001
    FRAG = 0x0002
    ECN = 0x0004


class QoS(Enum):
    """QoS tiers for RLH."""

    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"


@dataclass
class RLHHeader:
    """Router Label Header structure (RLH v1)."""

    # Header fields (total 48 bytes)
    dst_router_id: str  # 128-bit UUID as hex string
    egress_agent_id: int  # 64-bit hash of agent handle
    qos: QoS
    ttl: int  # 8-bit TTL
    budget_tokens: int  # 64-bit remaining tokens
    budget_usd_micros: int  # 64-bit remaining USD micros
    flags: int  # 16-bit flags
    hmac: bytes  # 128-bit HMAC

    VERSION = 1
    HEADER_SIZE = 67  # bytes

    @classmethod
    def create(
        cls,
        dst_router_id: str,
        egress_agent_id: int,
        qos: QoS,
        ttl: int,
        budget_tokens: int,
        budget_usd_micros: int,
        flags: int = 0,
        hmac_key: bytes | None = None,
    ) -> RLHHeader:
        """Create a new RLH header with computed HMAC."""
        header = cls(
            dst_router_id=dst_router_id,
            egress_agent_id=egress_agent_id,
            qos=qos,
            ttl=ttl,
            budget_tokens=budget_tokens,
            budget_usd_micros=budget_usd_micros,
            flags=flags,
            hmac=b"",  # Will be computed
        )

        if hmac_key:
            header.hmac = header.compute_hmac(hmac_key)
        else:
            # For testing, use zero HMAC
            header.hmac = b"\x00" * 16

        return header

    def compute_hmac(self, key: bytes) -> bytes:
        """Compute HMAC for the header."""
        # Pack header fields for HMAC computation (exclude HMAC field itself)
        data = struct.pack(
            ">16sQBQQQH",  # Big-endian format: 16s, Q, B, Q, Q, Q, H
            bytes.fromhex(self.dst_router_id.replace("-", "")),  # 128-bit UUID
            self.egress_agent_id,  # 64-bit
            ord(self.qos.value[0]),  # 8-bit (first char of QoS string)
            self.ttl,  # 8-bit
            self.budget_tokens,  # 64-bit
            self.budget_usd_micros,  # 64-bit
            self.flags,  # 16-bit
        )

        return hmac.new(key, data, hashlib.sha256).digest()[:16]  # 128-bit

    def verify_hmac(self, key: bytes) -> bool:
        """Verify HMAC of the header."""
        expected_hmac = self.compute_hmac(key)
        return hmac.compare_digest(self.hmac, expected_hmac)

    def decrement_ttl(self) -> bool:
        """Decrement TTL and return True if still valid."""
        if self.ttl > 0:
            self.ttl -= 1
            return self.ttl > 0
        return False

    def decrement_budget(self, tokens_used: int, usd_micros_used: int) -> bool:
        """Decrement budget and return True if still has budget."""
        self.budget_tokens = max(0, self.budget_tokens - tokens_used)
        self.budget_usd_micros = max(0, self.budget_usd_micros - usd_micros_used)

        return self.budget_tokens > 0 and self.budget_usd_micros > 0

    def has_budget(self) -> bool:
        """Check if header has remaining budget."""
        return self.budget_tokens > 0 and self.budget_usd_micros > 0

    def is_expired(self) -> bool:
        """Check if TTL has expired."""
        return self.ttl == 0

    def set_flag(self, flag: RLHFlags) -> None:
        """Set a flag in the header."""
        self.flags |= flag.value

    def clear_flag(self, flag: RLHFlags) -> None:
        """Clear a flag in the header."""
        self.flags &= ~flag.value

    def has_flag(self, flag: RLHFlags) -> bool:
        """Check if a flag is set."""
        return (self.flags & flag.value) != 0

    def pack(self) -> bytes:
        """Pack header into bytes for transmission."""
        # Convert UUID string to 16 bytes
        uuid_bytes = bytes.fromhex(self.dst_router_id.replace("-", ""))

        return struct.pack(
            ">16sQBQQQH16s",  # Big-endian format: 16s, Q, B, Q, Q, Q, H, 16s
            uuid_bytes,  # 128-bit dst_router_id
            self.egress_agent_id,  # 64-bit
            ord(self.qos.value[0]),  # 8-bit (first char: g/s/b)
            self.ttl,  # 8-bit
            self.budget_tokens,  # 64-bit
            self.budget_usd_micros,  # 64-bit
            self.flags,  # 16-bit
            self.hmac,  # 128-bit
        )

    @classmethod
    def unpack(cls, data: bytes) -> RLHHeader:
        """Unpack header from bytes."""
        if len(data) != cls.HEADER_SIZE:
            raise ValueError(f"Invalid RLH header size: {len(data)}, expected {cls.HEADER_SIZE}")

        (
            uuid_bytes,
            egress_agent_id,
            qos_byte,
            ttl,
            budget_tokens,
            budget_usd_micros,
            flags,
            hmac_bytes,
        ) = struct.unpack(">16sQBQQQH16s", data)

        # Convert UUID bytes back to string
        dst_router_id = f"{uuid_bytes.hex()[:8]}-{uuid_bytes.hex()[8:12]}-{uuid_bytes.hex()[12:16]}-{uuid_bytes.hex()[16:20]}-{uuid_bytes.hex()[20:]}"

        # Convert QoS byte back to enum
        qos_char = chr(qos_byte)
        if qos_char == "g":
            qos = QoS.GOLD
        elif qos_char == "s":
            qos = QoS.SILVER
        elif qos_char == "b":
            qos = QoS.BRONZE
        else:
            raise ValueError(f"Invalid QoS byte: {qos_byte}")

        return cls(
            dst_router_id=dst_router_id,
            egress_agent_id=egress_agent_id,
            qos=qos,
            ttl=ttl,
            budget_tokens=budget_tokens,
            budget_usd_micros=budget_usd_micros,
            flags=flags,
            hmac=hmac_bytes,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert header to dictionary for serialization."""
        return {
            "version": self.VERSION,
            "dst_router_id": self.dst_router_id,
            "egress_agent_id": self.egress_agent_id,
            "qos": self.qos.value,
            "ttl": self.ttl,
            "budget_tokens": self.budget_tokens,
            "budget_usd_micros": self.budget_usd_micros,
            "flags": self.flags,
            "hmac": self.hmac.hex(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RLHHeader:
        """Create header from dictionary."""
        return cls(
            dst_router_id=data["dst_router_id"],
            egress_agent_id=data["egress_agent_id"],
            qos=QoS(data["qos"]),
            ttl=data["ttl"],
            budget_tokens=data["budget_tokens"],
            budget_usd_micros=data["budget_usd_micros"],
            flags=data["flags"],
            hmac=bytes.fromhex(data["hmac"]),
        )


@dataclass
class RLHEncapsulatedFrame:
    """ATP Frame encapsulated with RLH header."""

    rlh_header: RLHHeader
    atp_frame: dict[str, Any]  # ATP frame as dictionary

    def pack(self) -> bytes:
        """Pack encapsulated frame for transmission."""
        header_bytes = self.rlh_header.pack()
        # In real implementation, ATP frame would be serialized
        # For POC, we'll just use JSON representation
        import json

        frame_bytes = json.dumps(self.atp_frame).encode("utf-8")
        return header_bytes + frame_bytes

    @classmethod
    def unpack(cls, data: bytes) -> RLHEncapsulatedFrame:
        """Unpack encapsulated frame."""
        if len(data) < RLHHeader.HEADER_SIZE:
            raise ValueError("Data too short for RLH header")

        header = RLHHeader.unpack(data[: RLHHeader.HEADER_SIZE])

        # Parse ATP frame (simplified for POC)
        import json

        frame_data = json.loads(data[RLHHeader.HEADER_SIZE :].decode("utf-8"))

        return cls(rlh_header=header, atp_frame=frame_data)


class RLHProcessor:
    """Processes RLH encapsulated frames and handles budget/TTL logic."""

    def __init__(self, router_id: str, hmac_key: bytes | None = None, overhead_model: OverheadModel | None = None):
        self.router_id = router_id
        self.hmac_key = hmac_key or b"default-hmac-key-for-poc"
        self.overhead_model = overhead_model or OverheadModel()
        self.rlh_forwarded = REGISTRY.counter("rlh_forwarded_total")
        self.rlh_dropped_ttl = REGISTRY.counter("rlh_dropped_ttl_total")
        self.rlh_dropped_budget = REGISTRY.counter("rlh_dropped_budget_total")
        self.rlh_ecn_marked = REGISTRY.counter("rlh_ecn_marked_total")
        self.overhead_model_version = REGISTRY.gauge("overhead_model_version")
        self.overhead_model_version.set(float(self.overhead_model.version))

        # Overhead telemetry tracking
        self.overhead_measurements = deque(maxlen=10000)  # Keep last 10k measurements
        self.overhead_mape_7d = REGISTRY.gauge("overhead_mape_7d")
        self.overhead_p95_factor = REGISTRY.gauge("overhead_p95_factor")

    def encapsulate_frame(
        self,
        atp_frame: dict[str, Any],
        dst_router_id: str,
        egress_agent_id: int,
        qos: QoS,
        initial_budget_tokens: int,
        initial_budget_usd_micros: int,
        ttl: int = 64,
    ) -> RLHEncapsulatedFrame:
        """Encapsulate an ATP frame with RLH header."""
        header = RLHHeader.create(
            dst_router_id=dst_router_id,
            egress_agent_id=egress_agent_id,
            qos=qos,
            ttl=ttl,
            budget_tokens=initial_budget_tokens,
            budget_usd_micros=initial_budget_usd_micros,
            hmac_key=self.hmac_key,
        )

        return RLHEncapsulatedFrame(rlh_header=header, atp_frame=atp_frame)

    def process_incoming_frame(self, encapsulated_frame: RLHEncapsulatedFrame) -> RLHEncapsulatedFrame | None:
        """Process an incoming RLH encapsulated frame."""
        header = encapsulated_frame.rlh_header

        # Verify HMAC if key is available
        if self.hmac_key and not header.verify_hmac(self.hmac_key):
            # In production, this would log an error
            return None

        # Check if destined for this router
        if header.dst_router_id != self.router_id:
            # Forward to next hop (simplified - would need routing logic)
            self.rlh_forwarded.inc()
            return encapsulated_frame

        # This is the egress router - decapsulate and return ATP frame
        # In real implementation, would return just the ATP frame
        return encapsulated_frame

    def forward_frame(
        self,
        encapsulated_frame: RLHEncapsulatedFrame,
        next_hop_router_id: str,
        payload_tokens: int = 1000,
        payload_usd_micros: int = 10000,
        congestion_detected: bool = False,
    ) -> RLHEncapsulatedFrame | None:
        """Forward an RLH encapsulated frame to the next hop."""

        # Decrement TTL
        if not encapsulated_frame.rlh_header.decrement_ttl():
            self.rlh_dropped_ttl.inc()
            return None

        # Calculate overhead using the model
        overhead_tokens, overhead_usd_micros = self.overhead_model.calculate_overhead(
            payload_tokens, payload_usd_micros
        )

        # Decrement budget with overhead
        if not encapsulated_frame.rlh_header.decrement_budget(overhead_tokens, overhead_usd_micros):
            self.rlh_dropped_budget.inc()
            return None

        # Update destination
        encapsulated_frame.rlh_header.dst_router_id = next_hop_router_id

        # Set ECN flag if congestion detected
        if congestion_detected:
            encapsulated_frame.rlh_header.set_flag(RLHFlags.ECN)
            self.rlh_ecn_marked.inc()

        # Recompute HMAC with new values
        encapsulated_frame.rlh_header.hmac = encapsulated_frame.rlh_header.compute_hmac(self.hmac_key)

        self.rlh_forwarded.inc()

        # Record overhead measurement for telemetry
        # For now, record predicted as actual (will be refined with real measurements)
        self.record_overhead_measurement(
            predicted_tokens=overhead_tokens,
            actual_tokens=overhead_tokens,
            predicted_usd=overhead_usd_micros,
            actual_usd=overhead_usd_micros,
        )

        return encapsulated_frame

    def get_overhead_model(self) -> dict[str, Any]:
        """Get overhead model for inclusion in AGP OPEN messages."""
        return {"overhead_model": self.overhead_model.to_dict()}

    def update_overhead_model(self, new_model: OverheadModel) -> None:
        """Update the overhead model parameters."""
        self.overhead_model = new_model
        # Update metric
        self.overhead_model_version.set(float(self.overhead_model.version))

    def get_stats(self) -> dict[str, Any]:
        """Get RLH processing statistics."""
        return {
            "rlh_forwarded": self.rlh_forwarded._value,
            "rlh_dropped_ttl": self.rlh_dropped_ttl._value,
            "rlh_dropped_budget": self.rlh_dropped_budget._value,
            "rlh_ecn_marked": self.rlh_ecn_marked._value,
            "overhead_model": self.overhead_model.to_dict(),
        }

    def record_overhead_measurement(
        self, predicted_tokens: int, actual_tokens: int, predicted_usd: int, actual_usd: int
    ) -> None:
        """Record an overhead measurement for telemetry."""
        measurement = OverheadMeasurement(
            timestamp=time.time(),
            predicted_tokens=predicted_tokens,
            actual_tokens=actual_tokens,
            predicted_usd=predicted_usd,
            actual_usd=actual_usd,
        )
        self.overhead_measurements.append(measurement)
        self._update_telemetry_metrics()

    def _update_telemetry_metrics(self) -> None:
        """Update MAPE and p95 factor metrics based on recent measurements."""
        if len(self.overhead_measurements) < 10:  # Need minimum samples
            return

        # Calculate MAPE for tokens and USD
        token_errors = []
        usd_errors = []

        for measurement in self.overhead_measurements:
            if measurement.predicted_tokens > 0:
                token_error = (
                    abs(measurement.actual_tokens - measurement.predicted_tokens) / measurement.predicted_tokens
                )
                token_errors.append(token_error)

            if measurement.predicted_usd > 0:
                usd_error = abs(measurement.actual_usd - measurement.predicted_usd) / measurement.predicted_usd
                usd_errors.append(usd_error)

        if token_errors and usd_errors:
            # Combined MAPE
            combined_mape = (sum(token_errors) + sum(usd_errors)) / (len(token_errors) + len(usd_errors))
            self.overhead_mape_7d.set(combined_mape)

        # Calculate p95 factor (actual/predicted ratio)
        if len(self.overhead_measurements) >= 20:  # Need enough samples for p95
            factors = []
            for measurement in self.overhead_measurements:
                if measurement.predicted_tokens > 0:
                    factors.append(measurement.actual_tokens / measurement.predicted_tokens)
                if measurement.predicted_usd > 0:
                    factors.append(measurement.actual_usd / measurement.predicted_usd)

            if factors:
                p95_factor = statistics.quantiles(factors, n=20)[18]  # 95th percentile
                self.overhead_p95_factor.set(p95_factor)

    def get_overhead_telemetry(self) -> dict[str, Any]:
        """Get current overhead telemetry for AGP UPDATE messages."""
        return {
            "overhead_mape_7d": self.overhead_mape_7d.value,
            "overhead_p95_factor": self.overhead_p95_factor.value,
        }
