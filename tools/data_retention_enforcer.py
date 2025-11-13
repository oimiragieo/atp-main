#!/usr/bin/env python3
"""
Data Retention Enforcement System

Implements GAP-160: Data retention enforcement with configurable policies,
automated purge jobs, and comprehensive metrics tracking.
"""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RetentionPolicy:
    """Retention policy configuration for a data type."""

    data_type: str
    max_age_days: int
    enabled: bool = True
    dry_run: bool = False


class RetentionConfig:
    """Configuration for data retention policies."""

    def __init__(self, config_file: str | None = None):
        self.policies: dict[str, RetentionPolicy] = {}

        # Default policies
        self._load_defaults()

        if config_file and Path(config_file).exists():
            self._load_from_file(config_file)

    def _load_defaults(self):
        """Load default retention policies."""
        self.policies = {
            "lifecycle": RetentionPolicy("lifecycle", 90),  # 90 days
            "admin_audit": RetentionPolicy("admin_audit", 365),  # 1 year
            "reconciliation_audit": RetentionPolicy("reconciliation_audit", 180),  # 6 months
            "slm_observations": RetentionPolicy("slm_observations", 30),  # 30 days
        }

    def _load_from_file(self, config_file: str):
        """Load policies from configuration file."""
        try:
            with open(config_file) as f:
                config = json.load(f)

            for data_type, policy_config in config.get("policies", {}).items():
                self.policies[data_type] = RetentionPolicy(
                    data_type=data_type,
                    max_age_days=policy_config.get("max_age_days", 30),
                    enabled=policy_config.get("enabled", True),
                    dry_run=policy_config.get("dry_run", False),
                )

            logger.info(f"Loaded retention policies from {config_file}")
        except Exception as e:
            logger.error(f"Failed to load retention config from {config_file}: {e}")

    def get_policy(self, data_type: str) -> RetentionPolicy | None:
        """Get retention policy for a data type."""
        return self.policies.get(data_type)

    def save_config(self, config_file: str):
        """Save current policies to configuration file."""
        config = {
            "policies": {
                data_type: {"max_age_days": policy.max_age_days, "enabled": policy.enabled, "dry_run": policy.dry_run}
                for data_type, policy in self.policies.items()
            }
        }

        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"Saved retention policies to {config_file}")


class RetentionEnforcer:
    """Enforces data retention policies by purging old data."""

    def __init__(self, data_dir: str, config: RetentionConfig):
        self.data_dir = Path(data_dir)
        self.config = config
        self.stats = {"files_processed": 0, "records_purged": 0, "bytes_freed": 0, "errors": 0}

    def purge_old_data(self, data_type: str, dry_run: bool = False) -> dict:
        """Purge old data for a specific data type."""
        policy = self.config.get_policy(data_type)
        if not policy or not policy.enabled:
            logger.info(f"No active policy for {data_type}, skipping")
            return {"status": "skipped", "reason": "no_policy"}

        # Override with dry_run if specified
        effective_dry_run = dry_run or policy.dry_run

        logger.info(f"Purging {data_type} data older than {policy.max_age_days} days (dry_run={effective_dry_run})")

        cutoff_time = time.time() - (policy.max_age_days * 24 * 60 * 60)

        # Find files for this data type
        pattern = f"{data_type}*.jsonl"
        files = list(self.data_dir.glob(pattern))

        if not files:
            logger.warning(f"No files found matching pattern {pattern}")
            return {"status": "no_files", "pattern": pattern}

        total_purged = 0
        total_bytes = 0

        for file_path in files:
            try:
                purged, bytes_freed = self._purge_file(file_path, cutoff_time, effective_dry_run)
                total_purged += purged
                total_bytes += bytes_freed
                self.stats["files_processed"] += 1
            except Exception as e:
                logger.error(f"Error purging {file_path}: {e}")
                self.stats["errors"] += 1

        self.stats["records_purged"] += total_purged
        self.stats["bytes_freed"] += total_bytes

        result = {
            "status": "completed",
            "data_type": data_type,
            "cutoff_time": cutoff_time,
            "records_purged": total_purged,
            "bytes_freed": total_bytes,
            "dry_run": effective_dry_run,
        }

        logger.info(
            f"Purge completed for {data_type}: {total_purged} records, "
            f"{total_bytes} bytes {'would be' if effective_dry_run else ''} freed"
        )

        return result

    def _purge_file(self, file_path: Path, cutoff_time: float, dry_run: bool) -> tuple[int, int]:
        """Purge old records from a single file."""
        if not file_path.exists():
            return 0, 0

        # Read all lines
        with open(file_path) as f:
            lines = f.readlines()

        if not lines:
            return 0, 0

        # Filter out old records
        kept_lines = []
        purged_count = 0

        for line in lines:
            try:
                record = json.loads(line.strip())
                record_time = record.get("ts", record.get("timestamp", 0))

                if record_time < cutoff_time:
                    purged_count += 1
                else:
                    kept_lines.append(line)
            except json.JSONDecodeError:
                # Keep malformed lines
                kept_lines.append(line)

        if purged_count == 0:
            return 0, 0

        if not dry_run:
            # Write back only the kept lines
            with open(file_path, "w") as f:
                f.writelines(kept_lines)

        bytes_freed = sum(len(line) for line in lines) - sum(len(line) for line in kept_lines)

        return purged_count, bytes_freed

    def run_full_purge(self, dry_run: bool = False) -> dict:
        """Run purge for all configured data types."""
        logger.info(f"Starting full data retention purge{' (dry run)' if dry_run else ''}")

        results = {}
        start_time = time.time()

        for data_type in self.config.policies.keys():
            results[data_type] = self.purge_old_data(data_type, dry_run)

        end_time = time.time()

        summary = {
            "status": "completed",
            "duration_seconds": end_time - start_time,
            "dry_run": dry_run,
            "results": results,
            "stats": self.stats.copy(),
        }

        logger.info(
            f"Full purge completed in {end_time - start_time:.1f}s: "
            f"{self.stats['records_purged']} records purged, "
            f"{self.stats['bytes_freed']} bytes freed"
        )

        return summary

    def get_stats(self) -> dict:
        """Get current purge statistics."""
        return self.stats.copy()


def main():
    """CLI interface for data retention enforcement."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="ATP Data Retention Enforcement")
    parser.add_argument("--data-dir", default="./data", help="Data directory path")
    parser.add_argument("--config", default="./configs/storage/retention_config.json", help="Retention configuration file")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry run without actual deletion")
    parser.add_argument("--data-type", help="Specific data type to purge")
    parser.add_argument("--init-config", action="store_true", help="Initialize default configuration file")

    args = parser.parse_args()

    # Initialize configuration
    config = RetentionConfig(args.config)

    if args.init_config:
        config.save_config(args.config)
        print(f"Initialized default retention configuration at {args.config}")
        return

    # Create enforcer
    enforcer = RetentionEnforcer(args.data_dir, config)

    if args.data_type:
        # Purge specific data type
        result = enforcer.purge_old_data(args.data_type, args.dry_run)
        print(json.dumps(result, indent=2))
    else:
        # Full purge
        result = enforcer.run_full_purge(args.dry_run)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
