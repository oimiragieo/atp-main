#!/usr/bin/env python3
"""
Access Review Attestation Workflow

This module implements a periodic access review system that:
- Exports current access permissions for review
- Detects stale/inactive access that should be revoked
- Maintains attestation records of completed reviews
- Provides compliance reporting for access reviews

Key Features:
- Periodic access export with configurable schedules
- Stale access detection based on last activity
- Attestation workflow with approval tracking
- Audit trail for all review actions
- Integration with existing access control systems
"""

import argparse
import csv
import json
import os

# Add the project root to Python path for imports
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import metrics
from metrics import ACCESS_REVIEWS_COMPLETED_TOTAL


@dataclass
class AccessRecord:
    """Represents a user's access to a resource."""

    user_id: str
    resource_type: str  # e.g., "namespace", "tenant", "role"
    resource_id: str
    permission: str  # e.g., "read", "write", "admin"
    granted_at: datetime
    last_accessed: datetime | None
    granted_by: str
    justification: str


@dataclass
class AccessReview:
    """Represents an access review cycle."""

    review_id: str
    review_period_start: datetime
    review_period_end: datetime
    reviewer: str
    access_records: list[AccessRecord]
    attestation_date: datetime | None
    findings: list[str]  # Issues found during review
    actions_taken: list[str]  # Actions taken (revoked, approved, etc.)
    created_at: datetime
    status: str  # "pending", "in_progress", "completed", "overdue"


class AccessReviewAttestationWorkflow:
    """Manages periodic access reviews and attestations."""

    def __init__(self, data_dir: Path = Path("data")):
        self.data_dir = data_dir
        self.data_dir.mkdir(exist_ok=True)
        self.access_file = data_dir / "access_records.jsonl"
        self.reviews_file = data_dir / "access_reviews.jsonl"

    def export_access_records(self, output_file: Path | None = None) -> list[AccessRecord]:
        """Export current access records for review."""
        # Mock data - in production this would query actual access control systems
        records = [
            AccessRecord(
                user_id="user1",
                resource_type="namespace",
                resource_id="production",
                permission="admin",
                granted_at=datetime.now() - timedelta(days=30),
                last_accessed=datetime.now() - timedelta(days=2),
                granted_by="admin",
                justification="Production deployment access",
            ),
            AccessRecord(
                user_id="user2",
                resource_type="tenant",
                resource_id="acme",
                permission="read",
                granted_at=datetime.now() - timedelta(days=90),
                last_accessed=datetime.now() - timedelta(days=45),
                granted_by="manager",
                justification="Client data access for support",
            ),
            AccessRecord(
                user_id="user3",
                resource_type="role",
                resource_id="developer",
                permission="write",
                granted_at=datetime.now() - timedelta(days=180),
                last_accessed=None,  # Never accessed - stale!
                granted_by="hr",
                justification="Development team access",
            ),
        ]

        if output_file:
            self._write_csv_report(records, output_file)

        return records

    def detect_stale_access(self, records: list[AccessRecord], max_age_days: int = 90) -> list[AccessRecord]:
        """Detect stale access records that haven't been used recently."""
        stale_records = []
        cutoff_date = datetime.now() - timedelta(days=max_age_days)

        for record in records:
            if record.last_accessed is None or record.last_accessed < cutoff_date:
                stale_records.append(record)

        return stale_records

    def create_review_cycle(self, reviewer: str, access_records: list[AccessRecord]) -> AccessReview:
        """Create a new access review cycle."""
        review_id = f"review_{int(time.time())}"
        now = datetime.now()

        # Detect stale access
        stale_access = self.detect_stale_access(access_records)
        findings = []
        if stale_access:
            findings.append(f"Found {len(stale_access)} stale access records")

        review = AccessReview(
            review_id=review_id,
            review_period_start=now - timedelta(days=90),
            review_period_end=now,
            reviewer=reviewer,
            access_records=access_records,
            attestation_date=None,
            findings=findings,
            actions_taken=[],
            created_at=now,
            status="pending",
        )

        # Save review
        self._save_review(review)

        return review

    def attest_review(self, review_id: str, reviewer: str, actions_taken: list[str]) -> bool:
        """Attest to completion of an access review."""
        review = self._load_review(review_id)
        if not review:
            return False

        if review.reviewer != reviewer:
            return False

        review.attestation_date = datetime.now()
        review.actions_taken = actions_taken
        review.status = "completed"

        # Update metrics
        ACCESS_REVIEWS_COMPLETED_TOTAL.inc()

        # Save updated review
        self._save_review(review)

        return True

    def get_pending_reviews(self) -> list[AccessReview]:
        """Get all pending access reviews."""
        reviews_map = {}
        if not self.reviews_file.exists():
            return []

        with open(self.reviews_file) as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    # Convert datetime strings back
                    data["review_period_start"] = datetime.fromisoformat(data["review_period_start"])
                    data["review_period_end"] = datetime.fromisoformat(data["review_period_end"])
                    data["created_at"] = datetime.fromisoformat(data["created_at"])
                    if data.get("attestation_date"):
                        data["attestation_date"] = datetime.fromisoformat(data["attestation_date"])
                    else:
                        data["attestation_date"] = None

                    # Convert access records
                    data["access_records"] = [AccessRecord(**record) for record in data["access_records"]]

                    review = AccessReview(**data)
                    review_id = review.review_id

                    # Keep the latest version of each review
                    if review_id not in reviews_map:
                        reviews_map[review_id] = review
                    else:
                        existing = reviews_map[review_id]
                        # If this one has an attestation_date and the existing doesn't, use this one
                        if review.attestation_date and not existing.attestation_date:
                            reviews_map[review_id] = review
                        # If both have attestation_date, use the more recent one
                        elif (
                            review.attestation_date
                            and existing.attestation_date
                            and review.attestation_date > existing.attestation_date
                        ):
                            reviews_map[review_id] = review

        return [r for r in reviews_map.values() if r.status == "pending"]

    def _write_csv_report(self, records: list[AccessRecord], output_file: Path):
        """Write access records to CSV file."""
        with open(output_file, "w", newline="") as csvfile:
            fieldnames = [
                "user_id",
                "resource_type",
                "resource_id",
                "permission",
                "granted_at",
                "last_accessed",
                "granted_by",
                "justification",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for record in records:
                writer.writerow(
                    {
                        "user_id": record.user_id,
                        "resource_type": record.resource_type,
                        "resource_id": record.resource_id,
                        "permission": record.permission,
                        "granted_at": record.granted_at.isoformat(),
                        "last_accessed": record.last_accessed.isoformat() if record.last_accessed else "Never",
                        "granted_by": record.granted_by,
                        "justification": record.justification,
                    }
                )

    def _save_review(self, review: AccessReview):
        """Save review to JSONL file."""
        data = asdict(review)
        # Convert datetimes to ISO strings for JSON serialization
        data["review_period_start"] = review.review_period_start.isoformat()
        data["review_period_end"] = review.review_period_end.isoformat()
        data["created_at"] = review.created_at.isoformat()
        if review.attestation_date:
            data["attestation_date"] = review.attestation_date.isoformat()

        # Convert AccessRecord datetimes
        for record in data["access_records"]:
            record["granted_at"] = record["granted_at"].isoformat()
            if record["last_accessed"]:
                record["last_accessed"] = record["last_accessed"].isoformat()

        with open(self.reviews_file, "a") as f:
            f.write(json.dumps(data) + "\n")

    def _load_review(self, review_id: str) -> AccessReview | None:
        """Load a specific review by ID."""
        if not self.reviews_file.exists():
            return None

        latest_review = None
        with open(self.reviews_file) as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    if data["review_id"] == review_id:
                        # Convert datetime strings back to datetime objects
                        data["review_period_start"] = datetime.fromisoformat(data["review_period_start"])
                        data["review_period_end"] = datetime.fromisoformat(data["review_period_end"])
                        data["created_at"] = datetime.fromisoformat(data["created_at"])
                        if data.get("attestation_date"):
                            data["attestation_date"] = datetime.fromisoformat(data["attestation_date"])
                        else:
                            data["attestation_date"] = None

                        # Convert access record datetime strings back
                        for record in data["access_records"]:
                            record["granted_at"] = datetime.fromisoformat(record["granted_at"])
                            if record["last_accessed"]:
                                record["last_accessed"] = datetime.fromisoformat(record["last_accessed"])

                        # Convert access records to AccessRecord objects
                        data["access_records"] = [AccessRecord(**record) for record in data["access_records"]]

                        # Keep the latest version (by attestation_date or created_at)
                        current_review = AccessReview(**data)
                        if latest_review is None:
                            latest_review = current_review
                        else:
                            # If this one has an attestation_date and the previous doesn't, use this one
                            if current_review.attestation_date and not latest_review.attestation_date:
                                latest_review = current_review
                            # If both have attestation_date, use the more recent one
                            elif (
                                current_review.attestation_date
                                and latest_review.attestation_date
                                and current_review.attestation_date > latest_review.attestation_date
                            ):
                                latest_review = current_review

        return latest_review


def main():
    """CLI interface for access review attestation workflow."""
    parser = argparse.ArgumentParser(description="Access Review Attestation Workflow")
    parser.add_argument(
        "action", choices=["export", "create-review", "attest", "list-pending"], help="Action to perform"
    )
    parser.add_argument("--reviewer", help="Reviewer name for review operations")
    parser.add_argument("--review-id", help="Review ID for attestation")
    parser.add_argument("--actions", nargs="*", help="Actions taken during review")
    parser.add_argument("--output", type=Path, help="Output file for export")
    parser.add_argument("--max-age-days", type=int, default=90, help="Maximum age in days for stale access detection")

    args = parser.parse_args()

    workflow = AccessReviewAttestationWorkflow()

    if args.action == "export":
        records = workflow.export_access_records(args.output)
        stale = workflow.detect_stale_access(records, args.max_age_days)

        print(f"Exported {len(records)} access records")
        print(f"Found {len(stale)} stale access records")

        if args.output:
            print(f"Report written to {args.output}")

    elif args.action == "create-review":
        if not args.reviewer:
            parser.error("--reviewer required for create-review")

        records = workflow.export_access_records()
        review = workflow.create_review_cycle(args.reviewer, records)

        print(f"Created review {review.review_id}")
        print(f"Found {len(review.findings)} issues")

    elif args.action == "attest":
        if not args.reviewer or not args.review_id or not args.actions:
            parser.error("--reviewer, --review-id, and --actions required for attest")

        success = workflow.attest_review(args.review_id, args.reviewer, args.actions)

        if success:
            print(f"Successfully attested review {args.review_id}")
        else:
            print(f"Failed to attest review {args.review_id}")

    elif args.action == "list-pending":
        pending = workflow.get_pending_reviews()

        if not pending:
            print("No pending reviews")
        else:
            print(f"Found {len(pending)} pending reviews:")
            for review in pending:
                print(f"  {review.review_id}: {review.reviewer} ({review.created_at.date()})")


if __name__ == "__main__":
    main()
