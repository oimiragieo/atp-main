#!/usr/bin/env python3
"""
Config Drift & Security Baseline Detector

Monitors configuration files for drift from security baselines.
Detects unauthorized changes to critical configuration files and
alerts on potential security violations.

Usage:
    python config_drift_detector.py baseline [path] [--exclude pattern]
    python config_drift_detector.py scan [path] [--alert] [--report json]
    python config_drift_detector.py list-baselines
"""

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from metrics import CONFIG_DRIFT_ALERTS_TOTAL
except ImportError:
    # Fallback for standalone usage
    CONFIG_DRIFT_ALERTS_TOTAL = None


@dataclass
class ConfigFile:
    """Represents a configuration file with its baseline hash."""
    path: str
    hash_value: str
    last_modified: float
    file_size: int
    security_level: str = "medium"  # low, medium, high


@dataclass
class DriftAlert:
    """Represents a configuration drift alert."""
    file_path: str
    baseline_hash: str
    current_hash: str
    change_type: str  # "modified", "deleted", "new"
    security_level: str
    timestamp: float


class ConfigDriftDetector:
    """Detects configuration drift from security baselines."""

    # Configuration file extensions to monitor
    CONFIG_EXTENSIONS = {
        ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
        ".env", ".properties", ".xml", ".config"
    }

    # Critical security configuration files
    SECURITY_CONFIGS = {
        "requirements.txt", "package.json", "Cargo.toml", "go.mod",
        "Dockerfile", "docker-compose.yml", ".env", "config.json",
        "security.json", "policies.json", "access.json"
    }

    # Files/directories to exclude
    EXCLUDE_PATTERNS = {
        ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
        "build", "dist", "target", ".pytest_cache", ".mypy_cache",
        ".terraform", "terraform.tfstate"
    }

    def __init__(self, baseline_store: Path = None):
        self.baseline_store = baseline_store or Path("data/config_baselines.json")
        self.baselines: dict[str, ConfigFile] = {}
        self._load_baselines()

    def _load_baselines(self) -> None:
        """Load baseline hashes from storage."""
        if self.baseline_store.exists():
            try:
                with open(self.baseline_store) as f:
                    data = json.load(f)
                    for path_str, file_data in data.items():
                        self.baselines[path_str] = ConfigFile(**file_data)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Could not load baselines: {e}", file=sys.stderr)

    def _save_baselines(self) -> None:
        """Save baseline hashes to storage."""
        self.baseline_store.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for path_str, config_file in self.baselines.items():
            data[path_str] = {
                "path": config_file.path,
                "hash_value": config_file.hash_value,
                "last_modified": config_file.last_modified,
                "file_size": config_file.file_size,
                "security_level": config_file.security_level
            }

        with open(self.baseline_store, 'w') as f:
            json.dump(data, f, indent=2)

    def _calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file."""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except OSError as e:
            print(f"Error reading {file_path}: {e}", file=sys.stderr)
            return ""

    def _get_security_level(self, file_path: Path) -> str:
        """Determine security level of a configuration file."""
        filename = file_path.name.lower()

        # High security: critical system configs
        if filename in {"secrets.json", "credentials.json", "keys.json", "ssl.json"}:
            return "high"

        # Medium security: standard configs
        if filename in self.SECURITY_CONFIGS or file_path.suffix in self.CONFIG_EXTENSIONS:
            return "medium"

        # Low security: other files
        return "low"

    def _should_exclude(self, path: Path, exclude_patterns: set[str]) -> bool:
        """Check if path should be excluded from scanning."""
        # Exclude baseline store file
        if path == self.baseline_store:
            return True

        if any(part in exclude_patterns for part in path.parts):
            return True

        # Exclude hidden files/directories (but not the baseline store)
        if any(part.startswith('.') for part in path.parts) and path != self.baseline_store:
            return True

        return False

    def establish_baseline(self, scan_path: Path, exclude_patterns: Optional[list[str]] = None) -> int:
        """Establish baseline hashes for configuration files."""
        custom_excludes = set(self.EXCLUDE_PATTERNS)
        if exclude_patterns:
            custom_excludes.update(exclude_patterns)

        config_files = []
        for ext in self.CONFIG_EXTENSIONS:
            config_files.extend(scan_path.rglob(f"*{ext}"))

        # Also include known security config files regardless of extension
        for config_name in self.SECURITY_CONFIGS:
            for match in scan_path.rglob(config_name):
                if match not in config_files:
                    config_files.append(match)

        established = 0
        for config_file in config_files:
            if self._should_exclude(config_file, custom_excludes):
                continue

            try:
                stat = config_file.stat()
                hash_value = self._calculate_hash(config_file)
                if hash_value:
                    security_level = self._get_security_level(config_file)
                    baseline = ConfigFile(
                        path=str(config_file),
                        hash_value=hash_value,
                        last_modified=stat.st_mtime,
                        file_size=stat.st_size,
                        security_level=security_level
                    )
                    self.baselines[str(config_file)] = baseline
                    established += 1
            except OSError as e:
                print(f"Warning: Could not process {config_file}: {e}", file=sys.stderr)

        self._save_baselines()
        return established

    def scan_for_drift(self, scan_path: Path, exclude_patterns: Optional[list[str]] = None) -> list[DriftAlert]:
        """Scan for configuration drift and return alerts."""
        import time
        custom_excludes = set(self.EXCLUDE_PATTERNS)
        if exclude_patterns:
            custom_excludes.update(exclude_patterns)

        alerts = []

        # Check existing baselines for changes/deletions
        for path_str, baseline in self.baselines.items():
            config_path = Path(path_str)

            # Skip if outside scan path
            try:
                config_path.relative_to(scan_path)
            except ValueError:
                continue

            if self._should_exclude(config_path, custom_excludes):
                continue

            if not config_path.exists():
                # File deleted
                alert = DriftAlert(
                    file_path=path_str,
                    baseline_hash=baseline.hash_value,
                    current_hash="",
                    change_type="deleted",
                    security_level=baseline.security_level,
                    timestamp=time.time()
                )
                alerts.append(alert)

                # Increment metrics for deleted file alerts
                if CONFIG_DRIFT_ALERTS_TOTAL:
                    CONFIG_DRIFT_ALERTS_TOTAL.inc()
            else:
                # Check for modifications
                try:
                    current_hash = self._calculate_hash(config_path)
                    if current_hash and current_hash != baseline.hash_value:
                        alert = DriftAlert(
                            file_path=path_str,
                            baseline_hash=baseline.hash_value,
                            current_hash=current_hash,
                            change_type="modified",
                            security_level=baseline.security_level,
                            timestamp=time.time()
                        )
                        alerts.append(alert)

                        # Increment metrics for modified file alerts
                        if CONFIG_DRIFT_ALERTS_TOTAL:
                            CONFIG_DRIFT_ALERTS_TOTAL.inc()
                except OSError as e:
                    print(f"Warning: Could not scan {config_path}: {e}", file=sys.stderr)

        # Check for new configuration files
        config_files = []
        for ext in self.CONFIG_EXTENSIONS:
            config_files.extend(scan_path.rglob(f"*{ext}"))

        for config_name in self.SECURITY_CONFIGS:
            for match in scan_path.rglob(config_name):
                if match not in config_files:
                    config_files.append(match)

        for config_file in config_files:
            if self._should_exclude(config_file, custom_excludes):
                continue

            path_str = str(config_file)
            if path_str not in self.baselines:
                try:
                    current_hash = self._calculate_hash(config_file)
                    if current_hash:
                        security_level = self._get_security_level(config_file)
                        alert = DriftAlert(
                            file_path=path_str,
                            baseline_hash="",
                            current_hash=current_hash,
                            change_type="new",
                            security_level=security_level,
                            timestamp=time.time()
                        )
                        alerts.append(alert)

                        # Increment metrics for new file alerts
                        if CONFIG_DRIFT_ALERTS_TOTAL:
                            CONFIG_DRIFT_ALERTS_TOTAL.inc()
                except OSError as e:
                    print(f"Warning: Could not scan {config_file}: {e}", file=sys.stderr)

        return alerts

    def list_baselines(self) -> list[ConfigFile]:
        """List all baseline configurations."""
        return list(self.baselines.values())


def main():
    parser = argparse.ArgumentParser(description="Config Drift & Security Baseline Detector")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Baseline command
    baseline_parser = subparsers.add_parser("baseline", help="Establish configuration baselines")
    baseline_parser.add_argument("path", type=Path, help="Path to scan for configuration files")
    baseline_parser.add_argument("--exclude", action="append", help="Additional patterns to exclude")

    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan for configuration drift")
    scan_parser.add_argument("path", type=Path, help="Path to scan for drift")
    scan_parser.add_argument("--exclude", action="append", help="Additional patterns to exclude")
    scan_parser.add_argument("--alert", action="store_true", help="Alert on drift detection")
    scan_parser.add_argument("--report", type=Path, help="Save drift report to JSON file")

    # List command
    subparsers.add_parser("list-baselines", help="List established baselines")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    detector = ConfigDriftDetector()

    if args.command == "baseline":
        count = detector.establish_baseline(args.path, args.exclude)
        print(f"Established baselines for {count} configuration files")

    elif args.command == "scan":
        alerts = detector.scan_for_drift(args.path, args.exclude)

        if alerts:
            print(f"Found {len(alerts)} configuration drift(s):")
            for alert in alerts:
                print(f"  {alert.change_type.upper()}: {alert.file_path} "
                      f"(security: {alert.security_level})")

                if CONFIG_DRIFT_ALERTS_TOTAL:
                    CONFIG_DRIFT_ALERTS_TOTAL.inc()

            if args.report:
                report_data = []
                for alert in alerts:
                    report_data.append({
                        "file_path": alert.file_path,
                        "baseline_hash": alert.baseline_hash,
                        "current_hash": alert.current_hash,
                        "change_type": alert.change_type,
                        "security_level": alert.security_level,
                        "timestamp": alert.timestamp
                    })

                with open(args.report, 'w') as f:
                    json.dump(report_data, f, indent=2)
                print(f"Drift report saved to {args.report}")

            if args.alert:
                # Could integrate with alerting system here
                print("ALERT: Configuration drift detected!")
                return 1
        else:
            print("No configuration drift detected")

    elif args.command == "list-baselines":
        baselines = detector.list_baselines()
        if baselines:
            print(f"Established baselines for {len(baselines)} files:")
            for baseline in sorted(baselines, key=lambda x: x.path):
                print(f"  {baseline.path} (security: {baseline.security_level})")
        else:
            print("No baselines established")

    return 0


if __name__ == "__main__":
    sys.exit(main())
