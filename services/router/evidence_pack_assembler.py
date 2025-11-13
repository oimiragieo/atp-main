"""Evidence pack assembly pipeline for GAP-368.

This module implements automated assembly of compliance evidence packs
containing policies, audit chain segments, DP ledger, retention logs,
and SLO reports for enterprise audits.
"""

from __future__ import annotations

import json
import logging
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from metrics.registry import REGISTRY

logger = logging.getLogger(__name__)

# GAP-368: Evidence pack assembly pipeline metrics
EVIDENCE_PACKS_GENERATED_TOTAL = REGISTRY.counter("evidence_packs_generated_total")
EVIDENCE_PACK_GENERATION_DURATION = REGISTRY.histogram(
    "evidence_pack_generation_duration_seconds", [30, 60, 120, 300, 600]
)


@dataclass
class EvidencePackConfig:
    """Configuration for evidence pack assembly."""

    # Data sources
    policies_dir: str = "tools"
    audit_logs_dir: str = "data"
    dp_ledger_dir: str = "data"
    retention_logs_dir: str = "data"
    slo_reports_dir: str = "data"

    # File patterns
    policy_patterns: list[str] | None = None
    audit_patterns: list[str] | None = None
    dp_patterns: list[str] | None = None
    retention_patterns: list[str] | None = None
    slo_patterns: list[str] | None = None

    # Time range for evidence collection
    days_back: int = 30

    # Output configuration
    output_dir: str = "evidence_packs"
    compression_level: int = 6

    def __post_init__(self):
        if self.policy_patterns is None:
            self.policy_patterns = ["policy*.yaml", "policy*.json"]
        if self.audit_patterns is None:
            self.audit_patterns = ["*audit*.jsonl", "admin_audit.jsonl"]
        if self.dp_patterns is None:
            self.dp_patterns = ["*dp*.jsonl", "*privacy*.jsonl"]
        if self.retention_patterns is None:
            self.retention_patterns = ["lifecycle*.jsonl", "*retention*.jsonl"]
        if self.slo_patterns is None:
            self.slo_patterns = ["slm_observations*.jsonl", "*counters.json", "*slo*.json"]


@dataclass
class EvidencePackManifest:
    """Manifest describing the contents of an evidence pack."""

    pack_id: str
    created_at: str
    time_range: dict[str, str]
    version: str = "1.0"
    components: dict[str, Any] = None

    def __post_init__(self):
        if self.components is None:
            self.components = {}


@dataclass
class EvidencePack:
    """Complete evidence pack with all components."""

    manifest: EvidencePackManifest
    policies: dict[str, Any]
    audit_chain: list[dict[str, Any]]
    dp_ledger: list[dict[str, Any]]
    retention_logs: list[dict[str, Any]]
    slo_reports: dict[str, Any]


class EvidencePackAssembler:
    """Assembles compliance evidence packs from various data sources."""

    def __init__(self, config: EvidencePackConfig | None = None):
        self.config = config or EvidencePackConfig()
        self.base_path = Path.cwd()

    def _get_path(self, config_path: str) -> Path:
        """Get the full path for a config directory, handling both absolute and relative paths."""
        path = Path(config_path)
        if path.is_absolute():
            return path
        return self.base_path / path

    def assemble_pack(
        self, pack_id: str | None = None, custom_time_range: dict[str, str] | None = None
    ) -> EvidencePack:
        """Assemble a complete evidence pack.

        Args:
            pack_id: Optional custom pack ID
            custom_time_range: Optional custom time range override

        Returns:
            Complete evidence pack
        """
        start_time = time.time()

        # Generate pack ID if not provided
        if pack_id is None:
            pack_id = f"evidence-pack-{int(time.time())}"

        # Determine time range
        time_range = custom_time_range or self._calculate_time_range()

        logger.info(f"Assembling evidence pack {pack_id} for time range: {time_range}")

        # Collect all components
        manifest = EvidencePackManifest(pack_id=pack_id, created_at=datetime.now().isoformat(), time_range=time_range)

        # Collect policies
        policies = self._collect_policies()
        manifest.components["policies"] = {"count": len(policies), "sources": list(policies.keys())}

        # Collect audit chain
        audit_chain = self._collect_audit_chain(time_range)
        manifest.components["audit_chain"] = {"count": len(audit_chain), "sources": self.config.audit_patterns}

        # Collect DP ledger
        dp_ledger = self._collect_dp_ledger(time_range)
        manifest.components["dp_ledger"] = {"count": len(dp_ledger), "sources": self.config.dp_patterns}

        # Collect retention logs
        retention_logs = self._collect_retention_logs(time_range)
        manifest.components["retention_logs"] = {
            "count": len(retention_logs),
            "sources": self.config.retention_patterns,
        }

        # Collect SLO reports
        slo_reports = self._collect_slo_reports(time_range)
        manifest.components["slo_reports"] = {"count": len(slo_reports), "sources": self.config.slo_patterns}

        pack = EvidencePack(
            manifest=manifest,
            policies=policies,
            audit_chain=audit_chain,
            dp_ledger=dp_ledger,
            retention_logs=retention_logs,
            slo_reports=slo_reports,
        )

        # Record metrics
        duration = time.time() - start_time
        EVIDENCE_PACK_GENERATION_DURATION.observe(duration)
        EVIDENCE_PACKS_GENERATED_TOTAL.inc()

        logger.info(
            f"Evidence pack {pack_id} assembled in {duration:.2f}s with "
            f"{len(policies)} policies, {len(audit_chain)} audit entries, "
            f"{len(dp_ledger)} DP entries, {len(retention_logs)} retention entries, "
            f"{len(slo_reports)} SLO reports"
        )

        return pack

    def save_pack(self, pack: EvidencePack, output_path: str | None = None) -> str:
        """Save evidence pack to disk as a compressed archive.

        Args:
            pack: The evidence pack to save
            output_path: Optional custom output path

        Returns:
            Path to the saved pack
        """
        if output_path is None:
            output_dir = self._get_path(self.config.output_dir)
            output_dir.mkdir(exist_ok=True)
            output_path = str(output_dir / f"{pack.manifest.pack_id}.zip")

        logger.info(f"Saving evidence pack to {output_path}")

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=self.config.compression_level) as zf:
            # Save manifest
            manifest_data = {
                "pack_id": pack.manifest.pack_id,
                "created_at": pack.manifest.created_at,
                "time_range": pack.manifest.time_range,
                "version": pack.manifest.version,
                "components": pack.manifest.components,
            }
            zf.writestr("manifest.json", json.dumps(manifest_data, indent=2))

            # Save policies
            if pack.policies:
                zf.writestr("policies.json", json.dumps(pack.policies, indent=2))

            # Save audit chain
            if pack.audit_chain:
                zf.writestr("audit_chain.jsonl", "\n".join(json.dumps(entry) for entry in pack.audit_chain))

            # Save DP ledger
            if pack.dp_ledger:
                zf.writestr("dp_ledger.jsonl", "\n".join(json.dumps(entry) for entry in pack.dp_ledger))

            # Save retention logs
            if pack.retention_logs:
                zf.writestr("retention_logs.jsonl", "\n".join(json.dumps(entry) for entry in pack.retention_logs))

            # Save SLO reports
            if pack.slo_reports:
                zf.writestr("slo_reports.json", json.dumps(pack.slo_reports, indent=2))

        logger.info(f"Evidence pack saved to {output_path}")
        return output_path

    def _calculate_time_range(self) -> dict[str, str]:
        """Calculate the time range for evidence collection."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.config.days_back)

        return {"start": start_date.isoformat(), "end": end_date.isoformat()}

    def _collect_policies(self) -> dict[str, Any]:
        """Collect policy files from the policies directory."""
        policies = {}
        policies_path = self._get_path(self.config.policies_dir)

        if not policies_path.exists():
            logger.warning(f"Policies directory {policies_path} does not exist")
            return policies

        for pattern in self.config.policy_patterns:
            for policy_file in policies_path.glob(pattern):
                try:
                    if policy_file.suffix.lower() == ".yaml":
                        import yaml

                        with open(policy_file, encoding="utf-8") as f:
                            policies[policy_file.name] = yaml.safe_load(f)
                    elif policy_file.suffix.lower() == ".json":
                        with open(policy_file, encoding="utf-8") as f:
                            policies[policy_file.name] = json.load(f)
                    else:
                        logger.warning(f"Unsupported policy file format: {policy_file}")
                except Exception as e:
                    logger.error(f"Error reading policy file {policy_file}: {e}")

        return policies

    def _collect_audit_chain(self, time_range: dict[str, str]) -> list[dict[str, Any]]:
        """Collect audit chain entries within the time range."""
        audit_entries = []
        audit_path = self._get_path(self.config.audit_logs_dir)

        if not audit_path.exists():
            logger.warning(f"Audit logs directory {audit_path} does not exist")
            return audit_entries

        start_time = datetime.fromisoformat(time_range["start"])
        end_time = datetime.fromisoformat(time_range["end"])

        for pattern in self.config.audit_patterns:
            for audit_file in audit_path.glob(pattern):
                try:
                    with open(audit_file, encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                entry = json.loads(line.strip())
                                # Filter by timestamp if available
                                if self._entry_in_time_range(entry, start_time, end_time):
                                    audit_entries.append(entry)
                except Exception as e:
                    logger.error(f"Error reading audit file {audit_file}: {e}")

        return audit_entries

    def _collect_dp_ledger(self, time_range: dict[str, str]) -> list[dict[str, Any]]:
        """Collect differential privacy ledger entries."""
        dp_entries = []
        dp_path = self._get_path(self.config.dp_ledger_dir)

        if not dp_path.exists():
            logger.warning(f"DP ledger directory {dp_path} does not exist")
            return dp_entries

        start_time = datetime.fromisoformat(time_range["start"])
        end_time = datetime.fromisoformat(time_range["end"])

        for pattern in self.config.dp_patterns:
            for dp_file in dp_path.glob(pattern):
                try:
                    with open(dp_file, encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                entry = json.loads(line.strip())
                                if self._entry_in_time_range(entry, start_time, end_time):
                                    dp_entries.append(entry)
                except Exception as e:
                    logger.error(f"Error reading DP ledger file {dp_file}: {e}")

        return dp_entries

    def _collect_retention_logs(self, time_range: dict[str, str]) -> list[dict[str, Any]]:
        """Collect retention log entries."""
        retention_entries = []
        retention_path = self._get_path(self.config.retention_logs_dir)

        if not retention_path.exists():
            logger.warning(f"Retention logs directory {retention_path} does not exist")
            return retention_entries

        start_time = datetime.fromisoformat(time_range["start"])
        end_time = datetime.fromisoformat(time_range["end"])

        for pattern in self.config.retention_patterns:
            for retention_file in retention_path.glob(pattern):
                try:
                    with open(retention_file, encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                entry = json.loads(line.strip())
                                if self._entry_in_time_range(entry, start_time, end_time):
                                    retention_entries.append(entry)
                except Exception as e:
                    logger.error(f"Error reading retention log file {retention_file}: {e}")

        return retention_entries

    def _collect_slo_reports(self, time_range: dict[str, str]) -> dict[str, Any]:
        """Collect SLO reports and metrics."""
        slo_reports = {}
        slo_path = self._get_path(self.config.slo_reports_dir)

        if not slo_path.exists():
            logger.warning(f"SLO reports directory {slo_path} does not exist")
            return slo_reports

        start_time = datetime.fromisoformat(time_range["start"])
        end_time = datetime.fromisoformat(time_range["end"])

        # Collect SLM observations
        slm_entries = []
        for pattern in ["slm_observations*.jsonl"]:
            for slm_file in slo_path.glob(pattern):
                try:
                    with open(slm_file, encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                entry = json.loads(line.strip())
                                if self._entry_in_time_range(entry, start_time, end_time):
                                    slm_entries.append(entry)
                except Exception as e:
                    logger.error(f"Error reading SLM file {slm_file}: {e}")

        if slm_entries:
            slo_reports["slm_observations"] = slm_entries

        # Collect counter files
        for pattern in ["*counters.json"]:
            for counter_file in slo_path.glob(pattern):
                try:
                    with open(counter_file, encoding="utf-8") as f:
                        counters = json.load(f)
                        slo_reports[f"counters_{counter_file.stem}"] = counters
                except Exception as e:
                    logger.error(f"Error reading counter file {counter_file}: {e}")

        return slo_reports

    def _entry_in_time_range(self, entry: dict[str, Any], start_time: datetime, end_time: datetime) -> bool:
        """Check if an entry falls within the specified time range."""
        # Try common timestamp fields
        timestamp_fields = ["timestamp", "time", "created_at", "event_time"]

        for field in timestamp_fields:
            if field in entry:
                try:
                    entry_time = datetime.fromisoformat(entry[field])
                    return start_time <= entry_time <= end_time
                except (ValueError, TypeError):
                    continue

        # If no timestamp found, include the entry (better to include than exclude)
        return True


def create_evidence_pack(
    pack_id: str | None = None, config: EvidencePackConfig | None = None, save_to_disk: bool = True
) -> EvidencePack:
    """Convenience function to create and optionally save an evidence pack.

    Args:
        pack_id: Optional custom pack ID
        config: Optional custom configuration
        save_to_disk: Whether to save the pack to disk

    Returns:
        The created evidence pack
    """
    assembler = EvidencePackAssembler(config)
    pack = assembler.assemble_pack(pack_id)

    if save_to_disk:
        assembler.save_pack(pack)

    return pack


def get_evidence_pack_info(pack_path: str) -> dict[str, Any]:
    """Get information about an evidence pack without extracting it.

    Args:
        pack_path: Path to the evidence pack zip file

    Returns:
        Dictionary with pack information
    """
    with zipfile.ZipFile(pack_path, "r") as zf:
        # Read manifest
        with zf.open("manifest.json") as f:
            manifest = json.load(f)

        # Get file list
        files = zf.namelist()

        return {"manifest": manifest, "files": files, "total_size": sum(zf.getinfo(name).file_size for name in files)}
