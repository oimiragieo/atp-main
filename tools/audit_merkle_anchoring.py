#!/usr/bin/env python3
"""Audit Merkle Root Anchoring Strategy Tool.

This tool implements a comprehensive audit log anchoring strategy using Merkle trees.
It supports multiple anchoring backends (transparency log, blockchain, etc.) and
provides periodic root publishing with verification capabilities.

Usage:
    python audit_merkle_anchoring.py --help
"""

import argparse
import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

import aiofiles

# Optional imports for different anchoring backends
try:
    from metrics import (
        MERKLE_ROOT_PUBLISH_LATENCY,
        MERKLE_ROOT_PUBLISH_TOTAL,
        MERKLE_ROOT_VERIFICATION_FAILED_TOTAL,
        MERKLE_ROOT_VERIFICATION_TOTAL,
    )
except ImportError:
    MERKLE_ROOT_PUBLISH_TOTAL = None
    MERKLE_ROOT_VERIFICATION_TOTAL = None
    MERKLE_ROOT_VERIFICATION_FAILED_TOTAL = None
    MERKLE_ROOT_PUBLISH_LATENCY = None

from router_service.fragmentation import MerkleTree


@dataclass
class AnchoringConfig:
    """Configuration for audit log anchoring."""

    audit_log_path: str
    anchoring_backend: str = "transparency_log"
    publish_interval_seconds: int = 3600  # 1 hour
    max_entries_per_root: int = 1000
    enable_verification: bool = True
    verification_interval_seconds: int = 300  # 5 minutes


@dataclass
class AnchoringResult:
    """Result of an anchoring operation."""

    timestamp: float
    root_hash: str
    entry_count: int
    backend: str
    success: bool
    error_message: Optional[str] = None
    verification_status: Optional[str] = None


class AnchoringBackend(Protocol):
    """Protocol for anchoring backends."""

    async def publish_root(self, root_hash: str, metadata: dict[str, Any]) -> bool:
        """Publish a Merkle root to the anchoring service."""
        ...

    async def verify_root(self, root_hash: str) -> bool:
        """Verify a Merkle root against the anchoring service."""
        ...


class TransparencyLogBackend:
    """Transparency log anchoring backend."""

    def __init__(self, log_path: str):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    async def publish_root(self, root_hash: str, metadata: dict[str, Any]) -> bool:
        """Publish root to transparency log."""
        try:
            entry = {
                "timestamp": time.time(),
                "root_hash": root_hash,
                "metadata": metadata,
                "backend": "transparency_log"
            }

            async with aiofiles.open(self.log_path, "a") as f:
                await f.write(json.dumps(entry) + "\n")

            return True
        except Exception as e:
            logging.error(f"Failed to publish to transparency log: {e}")
            return False

    async def verify_root(self, root_hash: str) -> bool:
        """Verify root against transparency log."""
        try:
            if not self.log_path.exists():
                return False

            async with aiofiles.open(self.log_path) as f:
                async for line in f:
                    entry = json.loads(line.strip())
                    if entry.get("root_hash") == root_hash:
                        return True
            return False
        except Exception as e:
            logging.error(f"Failed to verify against transparency log: {e}")
            return False


class BlockchainBackend:
    """Blockchain anchoring backend (simulated)."""

    def __init__(self, rpc_url: str = "http://localhost:8545"):
        self.rpc_url = rpc_url
        # In a real implementation, this would connect to a blockchain node

    async def publish_root(self, root_hash: str, metadata: dict[str, Any]) -> bool:
        """Publish root to blockchain (simulated)."""
        try:
            # Simulate blockchain transaction
            logging.info(f"Simulating blockchain transaction for root: {root_hash}")
            # In real implementation: submit transaction to smart contract
            return True
        except Exception as e:
            logging.error(f"Failed to publish to blockchain: {e}")
            return False

    async def verify_root(self, root_hash: str) -> bool:
        """Verify root against blockchain."""
        try:
            # Simulate blockchain query
            logging.info(f"Simulating blockchain verification for root: {root_hash}")
            # In real implementation: query smart contract for root
            return True
        except Exception as e:
            logging.error(f"Failed to verify against blockchain: {e}")
            return False


class AuditMerkleAnchoring:
    """Main class for audit Merkle root anchoring."""

    def __init__(self, config: AnchoringConfig):
        self.config = config
        self.backends: dict[str, AnchoringBackend] = {}
        self._setup_backends()
        self.last_publish_time = 0
        self.last_verification_time = 0

    def _setup_backends(self):
        """Initialize anchoring backends."""
        if self.config.anchoring_backend == "transparency_log":
            self.backends["transparency_log"] = TransparencyLogBackend(
                f"{self.config.audit_log_path}.transparency_log"
            )
        elif self.config.anchoring_backend == "blockchain":
            self.backends["blockchain"] = BlockchainBackend()
        else:
            raise ValueError(f"Unsupported anchoring backend: {self.config.anchoring_backend}")

    async def _read_audit_entries(self, max_entries: Optional[int] = None) -> list[dict[str, Any]]:
        """Read audit entries from the log file."""
        entries = []
        try:
            async with aiofiles.open(self.config.audit_log_path) as f:
                async for line in f:
                    if line.strip():
                        try:
                            entry = json.loads(line.strip())
                            entries.append(entry)
                            if max_entries and len(entries) >= max_entries:
                                break
                        except json.JSONDecodeError:
                            continue
        except FileNotFoundError:
            logging.warning(f"Audit log not found: {self.config.audit_log_path}")
        except Exception as e:
            logging.error(f"Error reading audit log: {e}")

        return entries

    def _compute_merkle_root(self, entries: list[dict[str, Any]]) -> str:
        """Compute Merkle root from audit entries."""
        if not entries:
            return hashlib.sha256(b"empty").hexdigest()

        merkle = MerkleTree()
        for entry in entries:
            # Use the hash field from audit entries if available, otherwise hash the entry
            if "hash" in entry:
                merkle.add_leaf(entry["hash"])
            else:
                entry_str = json.dumps(entry, sort_keys=True)
                merkle.add_leaf(entry_str)

        root = merkle.get_root()
        return root or hashlib.sha256(b"empty").hexdigest()

    async def publish_root(self) -> AnchoringResult:
        """Publish current Merkle root to configured backend."""
        start_time = time.time()
        try:
            # Read recent audit entries
            entries = await self._read_audit_entries(self.config.max_entries_per_root)
            if not entries:
                return AnchoringResult(
                    timestamp=time.time(),
                    root_hash="",
                    entry_count=0,
                    backend=self.config.anchoring_backend,
                    success=False,
                    error_message="No audit entries found"
                )

            # Compute Merkle root
            root_hash = self._compute_merkle_root(entries)

            # Prepare metadata
            metadata = {
                "entry_count": len(entries),
                "timestamp": time.time(),
                "audit_log_path": self.config.audit_log_path
            }

            # Publish to backend
            backend = self.backends.get(self.config.anchoring_backend)
            if not backend:
                return AnchoringResult(
                    timestamp=time.time(),
                    root_hash=root_hash,
                    entry_count=len(entries),
                    backend=self.config.anchoring_backend,
                    success=False,
                    error_message="Backend not configured"
                )

            success = await backend.publish_root(root_hash, metadata)

            # Record metrics
            publish_time = time.time() - start_time
            if MERKLE_ROOT_PUBLISH_TOTAL:
                MERKLE_ROOT_PUBLISH_TOTAL.inc()
            if MERKLE_ROOT_PUBLISH_LATENCY:
                MERKLE_ROOT_PUBLISH_LATENCY.observe(publish_time)

            result = AnchoringResult(
                timestamp=time.time(),
                root_hash=root_hash,
                entry_count=len(entries),
                backend=self.config.anchoring_backend,
                success=success
            )

            if success:
                self.last_publish_time = time.time()
                logging.info(f"Successfully published Merkle root: {root_hash}")
            else:
                result.error_message = "Backend publish failed"

            return result

        except Exception as e:
            # Record failed publish latency
            publish_time = time.time() - start_time
            if MERKLE_ROOT_PUBLISH_LATENCY:
                MERKLE_ROOT_PUBLISH_LATENCY.observe(publish_time)

            logging.error(f"Error publishing root: {e}")
            return AnchoringResult(
                timestamp=time.time(),
                root_hash="",
                entry_count=0,
                backend=self.config.anchoring_backend,
                success=False,
                error_message=str(e)
            )

    async def verify_root(self, root_hash: str) -> bool:
        """Verify a Merkle root against the anchoring backend."""
        try:
            backend = self.backends.get(self.config.anchoring_backend)
            if not backend:
                logging.error("Backend not configured for verification")
                if MERKLE_ROOT_VERIFICATION_FAILED_TOTAL:
                    MERKLE_ROOT_VERIFICATION_FAILED_TOTAL.inc()
                return False

            if MERKLE_ROOT_VERIFICATION_TOTAL:
                MERKLE_ROOT_VERIFICATION_TOTAL.inc()

            verified = await backend.verify_root(root_hash)
            self.last_verification_time = time.time()

            if verified:
                logging.info(f"Root verification successful: {root_hash}")
            else:
                logging.warning(f"Root verification failed: {root_hash}")
                if MERKLE_ROOT_VERIFICATION_FAILED_TOTAL:
                    MERKLE_ROOT_VERIFICATION_FAILED_TOTAL.inc()

            return verified

        except Exception as e:
            logging.error(f"Error verifying root: {e}")
            if MERKLE_ROOT_VERIFICATION_FAILED_TOTAL:
                MERKLE_ROOT_VERIFICATION_FAILED_TOTAL.inc()
            return False

    async def run_periodic_anchoring(self):
        """Run periodic anchoring in a loop."""
        logging.info("Starting periodic Merkle root anchoring")
        logging.info(f"Publish interval: {self.config.publish_interval_seconds}s")
        logging.info(f"Verification interval: {self.config.verification_interval_seconds}s")

        while True:
            current_time = time.time()

            # Check if it's time to publish
            if current_time - self.last_publish_time >= self.config.publish_interval_seconds:
                result = await self.publish_root()
                if result.success:
                    logging.info(f"Periodic publish completed: {result.root_hash}")
                else:
                    logging.error(f"Periodic publish failed: {result.error_message}")

            # Check if it's time to verify (if enabled)
            if (self.config.enable_verification and
                current_time - self.last_verification_time >= self.config.verification_interval_seconds):
                # Verify the last published root
                entries = await self._read_audit_entries(self.config.max_entries_per_root)
                if entries:
                    current_root = self._compute_merkle_root(entries)
                    verified = await self.verify_root(current_root)
                    logging.info(f"Periodic verification: {'PASS' if verified else 'FAIL'}")

            # Sleep for a shorter interval to check conditions frequently
            await asyncio.sleep(min(60, self.config.publish_interval_seconds // 10))


def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Audit Merkle Root Anchoring Strategy Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run periodic anchoring with transparency log
  python audit_merkle_anchoring.py --audit-log /path/to/audit.log --backend transparency_log

  # Publish single root and verify
  python audit_merkle_anchoring.py --audit-log /path/to/audit.log --publish-once --verify

  # Compare anchoring strategies
  python audit_merkle_anchoring.py --audit-log /path/to/audit.log --compare-backends
        """
    )

    parser.add_argument(
        "--audit-log",
        required=True,
        help="Path to the audit log file"
    )

    parser.add_argument(
        "--backend",
        choices=["transparency_log", "blockchain"],
        default="transparency_log",
        help="Anchoring backend to use (default: transparency_log)"
    )

    parser.add_argument(
        "--publish-interval",
        type=int,
        default=3600,
        help="Interval between root publications in seconds (default: 3600)"
    )

    parser.add_argument(
        "--max-entries",
        type=int,
        default=1000,
        help="Maximum audit entries to include in each root (default: 1000)"
    )

    parser.add_argument(
        "--publish-once",
        action="store_true",
        help="Publish a single root and exit"
    )

    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify the current root after publishing"
    )

    parser.add_argument(
        "--compare-backends",
        action="store_true",
        help="Compare different anchoring backends"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    return parser


async def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    config = AnchoringConfig(
        audit_log_path=args.audit_log,
        anchoring_backend=args.backend,
        publish_interval_seconds=args.publish_interval,
        max_entries_per_root=args.max_entries
    )

    anchoring = AuditMerkleAnchoring(config)

    if args.compare_backends:
        await compare_anchoring_backends(args.audit_log)
    elif args.publish_once:
        result = await anchoring.publish_root()
        print(f"Publish result: {'SUCCESS' if result.success else 'FAILED'}")
        print(f"Root hash: {result.root_hash}")
        print(f"Entry count: {result.entry_count}")

        if args.verify and result.success:
            verified = await anchoring.verify_root(result.root_hash)
            print(f"Verification: {'PASS' if verified else 'FAIL'}")
    else:
        await anchoring.run_periodic_anchoring()


async def compare_anchoring_backends(audit_log_path: str):
    """Compare different anchoring backends."""
    print("Comparing Anchoring Backends")
    print("=" * 50)

    backends = ["transparency_log", "blockchain"]
    results = {}

    for backend in backends:
        print(f"\nTesting {backend} backend:")
        config = AnchoringConfig(
            audit_log_path=audit_log_path,
            anchoring_backend=backend,
            max_entries_per_root=100
        )

        anchoring = AuditMerkleAnchoring(config)

        # Time the publish operation
        start_time = time.time()
        result = await anchoring.publish_root()
        publish_time = time.time() - start_time

        # Time the verify operation
        if result.success:
            start_time = time.time()
            verified = await anchoring.verify_root(result.root_hash)
            verify_time = time.time() - start_time
        else:
            verified = False
            verify_time = 0

        results[backend] = {
            "success": result.success,
            "publish_time": publish_time,
            "verify_time": verify_time,
            "verified": verified,
            "entry_count": result.entry_count
        }

        print(f"  Success: {result.success}")
        print(".3f")
        print(".3f")
        print(f"  Verified: {verified}")
        print(f"  Entry count: {result.entry_count}")

    print("\nComparison Summary:")
    print("-" * 30)
    for backend, data in results.items():
        reliability = "High" if data["verified"] else "Low"
        speed = "Fast" if data["publish_time"] < 1.0 else "Slow"
        print(f"{backend}: Reliability={reliability}, Speed={speed}")


if __name__ == "__main__":
    asyncio.run(main())
