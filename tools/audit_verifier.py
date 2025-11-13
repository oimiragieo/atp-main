#!/usr/bin/env python3
"""
Audit Hash Verification CLI Tool

This tool verifies the integrity of tamper-evident audit logs by checking
the hash chain and HMAC signatures. It can verify individual log files
or batch verify multiple logs.

Usage:
    python audit_verifier.py <audit_log_path> [--secret <secret>] [--batch <directory>]
    python audit_verifier.py --help
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add the memory-gateway directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory-gateway"))

# Import the audit log verification functionality
import audit_log


class AuditVerifier:
    """CLI tool for verifying audit log integrity."""

    def __init__(self, secret: bytes | None = None):
        """Initialize verifier with optional secret."""
        self.secret = secret or b"default-audit-secret"  # Use default if not provided

    def verify_single_log(self, log_path: str) -> bool:
        """Verify a single audit log file."""
        if not os.path.exists(log_path):
            print(f"❌ Error: Audit log file not found: {log_path}")
            return False

        try:
            is_valid = audit_log.verify_log(log_path, self.secret)
            if is_valid:
                print(f"✅ Audit log integrity verified: {log_path}")
                self._print_log_stats(log_path)
                return True
            else:
                print(f"❌ Audit log verification FAILED: {log_path}")
                print("   Possible tampering detected!")
                return False
        except Exception as e:
            print(f"❌ Error verifying audit log {log_path}: {e}")
            return False

    def verify_batch_logs(self, directory: str) -> tuple[int, int]:
        """Verify all audit log files in a directory."""
        if not os.path.exists(directory):
            print(f"❌ Error: Directory not found: {directory}")
            return 0, 0

        log_files = list(Path(directory).glob("*.log")) + list(Path(directory).glob("*.jsonl"))
        if not log_files:
            print(f"⚠️  No .log or .jsonl files found in directory: {directory}")
            return 0, 0

        print(f"🔍 Verifying {len(log_files)} audit log files in {directory}...")

        verified = 0
        failed = 0

        for log_file in sorted(log_files):
            if self.verify_single_log(str(log_file)):
                verified += 1
            else:
                failed += 1

        print("\n📊 Batch verification complete:")
        print(f"   ✅ Verified: {verified}")
        print(f"   ❌ Failed: {failed}")
        print(f"   📁 Total: {verified + failed}")

        return verified, failed

    def _print_log_stats(self, log_path: str) -> None:
        """Print statistics about the verified log file."""
        try:
            with open(log_path) as f:
                lines = f.readlines()

            event_count = len(lines)
            if event_count > 0:
                # Parse the last line to get the latest hash
                last_record = json.loads(lines[-1].strip())
                latest_hash = last_record.get("hash", "unknown")[:16] + "..."

                print(f"   📝 Events: {event_count}")
                print(f"   🔗 Latest hash: {latest_hash}")
        except Exception as e:
            print(f"   ⚠️  Could not read log stats: {e}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Verify integrity of tamper-evident audit logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify a single audit log
  python audit_verifier.py /path/to/audit.log

  # Verify with custom secret
  python audit_verifier.py /path/to/audit.log --secret my-secret-key

  # Batch verify all logs in a directory
  python audit_verifier.py --batch /path/to/logs/

  # Verify and show detailed output
  python audit_verifier.py /path/to/audit.log --verbose
        """,
    )

    parser.add_argument("log_path", nargs="?", help="Path to audit log file to verify")

    parser.add_argument("--secret", help="Secret key for HMAC verification (default: default-audit-secret)")

    parser.add_argument("--batch", help="Directory containing audit log files to verify")

    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed verification information")

    args = parser.parse_args()

    # Handle secret
    secret = args.secret.encode("utf-8") if args.secret else None
    verifier = AuditVerifier(secret)

    # Handle batch mode
    if args.batch:
        if args.log_path:
            print("❌ Error: Cannot specify both log_path and --batch")
            sys.exit(1)

        verified, failed = verifier.verify_batch_logs(args.batch)
        sys.exit(0 if failed == 0 else 1)

    # Handle single file mode
    if not args.log_path:
        parser.print_help()
        sys.exit(1)

    success = verifier.verify_single_log(args.log_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
