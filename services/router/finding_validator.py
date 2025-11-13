"""Finding schema enforcement and agreement logic for GAP-136."""

from typing import Any

import yaml
from pydantic import ValidationError

from metrics.registry import REGISTRY

from .models import Finding


class FindingValidator:
    """Validates and canonicalizes findings according to the ATP schema."""

    def __init__(self, aliases_path: str | None = None) -> None:
        self.aliases = self._load_aliases(aliases_path)

    def _load_aliases(self, aliases_path: str | None) -> dict[str, str]:
        """Load type aliases from YAML file."""
        if not aliases_path:
            # Default aliases
            return {
                "audience claim missing": "code.vuln.aud_check_missing",
                "no aud check": "code.vuln.aud_check_missing",
                "missing aud": "code.vuln.aud_check_missing",
                "missing audience check": "code.vuln.aud_check_missing",
            }

        try:
            with open(aliases_path) as f:
                config = yaml.safe_load(f)
                aliases = {}
                for alias_group in config.get("aliases", []):
                    canonical = alias_group["to"]
                    for match in alias_group["match"]:
                        aliases[match.lower()] = canonical
                return aliases
        except (FileNotFoundError, yaml.YAMLError):
            return {}

    def validate_finding(self, finding_data: dict[str, Any]) -> Finding:
        """Validate a finding against the schema."""
        try:
            finding = Finding(**finding_data)
            # Canonicalize the type
            finding.type = self._canonicalize_type(finding.type)
            return finding
        except ValidationError as e:
            raise ValueError(f"Invalid finding schema: {e}") from e

    def _canonicalize_type(self, finding_type: str) -> str:
        """Canonicalize finding type using aliases."""
        return self.aliases.get(finding_type.lower(), finding_type)

    def validate_findings_batch(self, findings_data: list[dict[str, Any]]) -> list[Finding]:
        """Validate a batch of findings."""
        validated = []
        for finding_data in findings_data:
            try:
                validated.append(self.validate_finding(finding_data))
            except ValueError:
                # Skip invalid findings for now - could add logging/metrics here
                continue
        return validated


class FindingAgreementScorer:
    """Computes agreement scores between findings."""

    def __init__(self) -> None:
        self.embedding_model = None  # Placeholder for embedding model
        # Initialize metrics for GAP-136
        self._finding_agreement_pct = REGISTRY.histogram(
            "finding_agreement_pct", [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        )

    def compute_agreement(self, findings: list[Finding]) -> float:
        """Compute overall agreement score for a set of findings."""
        if len(findings) <= 1:
            return 1.0

        # Group findings by target (file/span/type)
        groups = self._group_findings(findings)

        agreement_scores = []
        for group in groups.values():
            if len(group) > 1:
                agreement_scores.append(self._compute_group_agreement(group))

        agreement = sum(agreement_scores) / len(agreement_scores) if agreement_scores else 1.0

        # Record metric for GAP-136
        self._finding_agreement_pct.observe(agreement)

        return agreement

    def _group_findings(self, findings: list[Finding]) -> dict[str, list[Finding]]:
        """Group findings by their target (file/span/type)."""
        groups: dict[str, list[Finding]] = {}
        for finding in findings:
            key = f"{finding.file or 'unknown'}:{finding.span or 'unknown'}:{finding.type}"
            if key not in groups:
                groups[key] = []
            groups[key].append(finding)
        return groups

    def _compute_group_agreement(self, group: list[Finding]) -> float:
        """Compute agreement score for a group of findings."""
        if len(group) <= 1:
            return 1.0

        # Evidence overlap (Jaccard on file:line ranges)
        evidence_overlap = self._compute_evidence_overlap(group)

        # Structured fields match (type/severity/tests)
        field_match = self._compute_field_match(group)

        # Placeholder for embedding similarity (would need actual embeddings)
        embedding_similarity = 0.8  # Placeholder

        # Weighted agreement score
        agreement = 0.5 * embedding_similarity + 0.3 * evidence_overlap + 0.2 * field_match
        return agreement

    def _compute_evidence_overlap(self, group: list[Finding]) -> float:
        """Compute Jaccard similarity of evidence spans."""
        all_spans = set()
        for finding in group:
            for evidence in finding.evidence:
                if evidence.file and evidence.lines:
                    all_spans.add(f"{evidence.file}:{evidence.lines}")

        if not all_spans:
            return 1.0  # No evidence to compare

        # Simple overlap calculation
        total_spans = len(all_spans)
        max_possible_overlap = len(group)  # If all findings had identical evidence

        return min(1.0, total_spans / max_possible_overlap)

    def _compute_field_match(self, group: list[Finding]) -> float:
        """Compute match score for structured fields."""
        if not group:
            return 1.0

        reference = group[0]
        matches = 0
        total = 0

        for finding in group[1:]:
            total += 1
            if (
                finding.type == reference.type
                and finding.severity == reference.severity
                and set(finding.tests) == set(reference.tests)
            ):
                matches += 1

        return matches / total if total > 0 else 1.0
