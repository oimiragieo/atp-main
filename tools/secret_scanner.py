#!/usr/bin/env python3
"""
Secret Leak Scanner for CI

Scans repository files for potential secret leaks using regex patterns.
Similar to gitleaks/trufflehog but lightweight and Python-based.

Usage:
    python secret_scanner.py [path] [--exclude pattern] [--report json]
"""

import argparse
import json
import re
from pathlib import Path
from typing import Optional

# Secret detection patterns
SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "aws_secret_key": re.compile(r"\b[0-9a-zA-Z/+]{40}\b"),
    "gcp_service_account": re.compile(r"\"type\"\s*:\s*\"service_account\""),
    "jwt_token": re.compile(r"\beyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\b"),
    "oauth_token": re.compile(r"\bya29\.[A-Za-z0-9-_]+\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9]{20,48}\b"),
    "github_token": re.compile(r"\bghp_[A-Za-z0-9]{36,40}\b"),
    "private_key": re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----"),
    "generic_secret": re.compile(r"(?i)(?:secret|password|token|key|credential).*['\"]([^'\"]{8,})['\"]"),
}

# File extensions to scan
SCAN_EXTENSIONS = {
    ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".env", ".config",
    ".txt", ".md", ".sh", ".bash", ".ps1", ".sql", ".xml", ".html"
}

# Files/directories to exclude
EXCLUDE_PATTERNS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    "build", "dist", "target", ".pytest_cache", ".mypy_cache"
}


class SecretScanner:
    """Scans files for potential secret leaks."""

    def __init__(self, exclude_patterns: Optional[list[str]] = None):
        self.exclude_patterns = set(EXCLUDE_PATTERNS)
        if exclude_patterns:
            self.exclude_patterns.update(exclude_patterns)
        self.findings: list[dict] = []

    def should_scan_file(self, file_path: Path) -> bool:
        """Check if file should be scanned."""
        # Check file extension
        if file_path.suffix.lower() not in SCAN_EXTENSIONS:
            return False

        # Check exclude patterns
        for pattern in self.exclude_patterns:
            if pattern in str(file_path):
                return False

        return True

    def scan_file(self, file_path: Path) -> list[dict]:
        """Scan a single file for secrets."""
        findings = []

        try:
            with open(file_path, encoding='utf-8', errors='ignore') as f:
                content = f.read()

            lines = content.splitlines()
            for line_num, line in enumerate(lines, 1):
                for pattern_name, pattern in SECRET_PATTERNS.items():
                    matches = pattern.findall(line)
                    if matches:
                        for match in matches:
                            findings.append({
                                "file": str(file_path),
                                "line": line_num,
                                "pattern": pattern_name,
                                "match": match[:50] + "..." if len(match) > 50 else match,
                                "severity": "high" if pattern_name in ["private_key", "aws_secret_key"] else "medium"
                            })

        except Exception as e:
            print(f"Error scanning {file_path}: {e}")

        return findings

    def scan_directory(self, directory: Path) -> list[dict]:
        """Scan all files in a directory."""
        all_findings = []

        for file_path in directory.rglob("*"):
            if file_path.is_file() and self.should_scan_file(file_path):
                findings = self.scan_file(file_path)
                all_findings.extend(findings)

        return all_findings

    def generate_report(self, findings: list[dict], output_format: str = "text") -> str:
        """Generate a report from findings."""
        if output_format == "json":
            return json.dumps(findings, indent=2)

        if not findings:
            return "✅ No potential secret leaks found."

        report = "🚨 Potential Secret Leaks Found:\n\n"

        for finding in findings:
            severity_icon = "🔴" if finding["severity"] == "high" else "🟡"
            report += f"{severity_icon} {finding['file']}:{finding['line']}\n"
            report += f"   Pattern: {finding['pattern']}\n"
            report += f"   Match: {finding['match']}\n\n"

        report += f"Total findings: {len(findings)}\n"
        high_severity = sum(1 for f in findings if f["severity"] == "high")
        report += f"High severity: {high_severity}\n"

        return report


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Scan for potential secret leaks")
    parser.add_argument("path", nargs="?", default=".", help="Path to scan")
    parser.add_argument("--exclude", action="append", help="Additional exclude patterns")
    parser.add_argument("--report", choices=["text", "json"], default="text",
                       help="Output format")
    parser.add_argument("--output", help="Output file (default: stdout)")

    args = parser.parse_args()

    scanner = SecretScanner(args.exclude)
    scan_path = Path(args.path)

    if scan_path.is_file():
        findings = scanner.scan_file(scan_path)
    else:
        findings = scanner.scan_directory(scan_path)

    report = scanner.generate_report(findings, args.report)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
    else:
        print(report)

    # Exit with error code if findings found
    exit(1 if findings else 0)


if __name__ == "__main__":
    main()
