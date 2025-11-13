"""Tests for GAP-328: Access Review Attestation Workflow"""

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from tools.access_review_attestation import (
    AccessRecord,
    AccessReview,
    AccessReviewAttestationWorkflow,
)


class TestAccessReviewAttestationWorkflow(unittest.TestCase):
    """Test Access Review Attestation Workflow functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.workflow = AccessReviewAttestationWorkflow(self.temp_dir)

        # Create mock access records
        self.mock_records = [
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

    def tearDown(self):
        """Clean up test fixtures."""
        # Remove temp files
        for file in self.temp_dir.glob("*"):
            file.unlink()
        self.temp_dir.rmdir()

    def test_export_access_records(self):
        """Test exporting access records."""
        records = self.workflow.export_access_records()

        self.assertIsInstance(records, list)
        self.assertTrue(len(records) > 0)

        # Check record structure
        record = records[0]
        self.assertIsInstance(record, AccessRecord)
        self.assertTrue(hasattr(record, "user_id"))
        self.assertTrue(hasattr(record, "resource_type"))
        self.assertTrue(hasattr(record, "permission"))

    def test_export_access_records_with_csv_output(self):
        """Test exporting access records to CSV."""
        output_file = self.temp_dir / "access_report.csv"
        self.workflow.export_access_records(output_file)

        self.assertTrue(output_file.exists())

        # Check CSV content
        with open(output_file) as f:
            content = f.read()
            self.assertIn("user_id", content)
            self.assertIn("resource_type", content)
            self.assertIn("permission", content)

    def test_detect_stale_access(self):
        """Test detection of stale access records."""
        # Test with default 90-day threshold
        stale_records = self.workflow.detect_stale_access(self.mock_records)

        # user3 has never been accessed (None) and user2 was accessed 45 days ago
        # With 90-day threshold, only user3 should be stale
        self.assertEqual(len(stale_records), 1)
        self.assertEqual(stale_records[0].user_id, "user3")

        # Test with 30-day threshold
        stale_records_30 = self.workflow.detect_stale_access(self.mock_records, max_age_days=30)

        # user2 was accessed 45 days ago (>30 days) and user3 never accessed
        self.assertEqual(len(stale_records_30), 2)
        user_ids = {r.user_id for r in stale_records_30}
        self.assertEqual(user_ids, {"user2", "user3"})

    def test_create_review_cycle(self):
        """Test creating a new access review cycle."""
        reviewer = "security_team"
        review = self.workflow.create_review_cycle(reviewer, self.mock_records)

        self.assertIsInstance(review, AccessReview)
        self.assertEqual(review.reviewer, reviewer)
        self.assertEqual(review.status, "pending")
        self.assertIsNotNone(review.review_id)
        self.assertTrue(review.review_id.startswith("review_"))

        # Check that stale access was detected
        self.assertTrue(len(review.findings) > 0)
        self.assertIn("stale", review.findings[0].lower())

        # Check that review was saved
        self.assertTrue(self.workflow.reviews_file.exists())

    def test_attest_review(self):
        """Test attesting to completion of an access review."""
        # Create a review first
        reviewer = "security_team"
        review = self.workflow.create_review_cycle(reviewer, self.mock_records)
        review_id = review.review_id

        # Attest to the review
        actions_taken = ["Revoked access for user3", "Approved access for user1"]
        success = self.workflow.attest_review(review_id, reviewer, actions_taken)

        self.assertTrue(success)

        # Load the review and check it was updated
        updated_review = self.workflow._load_review(review_id)
        self.assertIsNotNone(updated_review)
        self.assertEqual(updated_review.status, "completed")
        self.assertIsNotNone(updated_review.attestation_date)
        self.assertEqual(updated_review.actions_taken, actions_taken)

    def test_attest_review_wrong_reviewer(self):
        """Test attesting with wrong reviewer fails."""
        # Create a review first
        reviewer = "security_team"
        review = self.workflow.create_review_cycle(reviewer, self.mock_records)
        review_id = review.review_id

        # Try to attest with wrong reviewer
        wrong_reviewer = "different_team"
        actions_taken = ["Some actions"]
        success = self.workflow.attest_review(review_id, wrong_reviewer, actions_taken)

        self.assertFalse(success)

    def test_get_pending_reviews(self):
        """Test getting pending reviews."""
        # Initially no reviews
        pending = self.workflow.get_pending_reviews()
        self.assertEqual(len(pending), 0)

        # Create a review
        reviewer = "security_team"
        review = self.workflow.create_review_cycle(reviewer, self.mock_records)

        # Should now have one pending review
        pending = self.workflow.get_pending_reviews()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].review_id, review.review_id)

        # After attesting, should have no pending reviews
        self.workflow.attest_review(review.review_id, reviewer, ["Actions taken"])
        pending = self.workflow.get_pending_reviews()
        self.assertEqual(len(pending), 0)

    def test_review_persistence(self):
        """Test that reviews are properly persisted and loaded."""
        # Create a review
        reviewer = "security_team"
        review = self.workflow.create_review_cycle(reviewer, self.mock_records)
        original_id = review.review_id

        # Create a new workflow instance (simulating restart)
        new_workflow = AccessReviewAttestationWorkflow(self.temp_dir)

        # Load the review
        loaded_review = new_workflow._load_review(original_id)

        self.assertIsNotNone(loaded_review)
        self.assertEqual(loaded_review.review_id, original_id)
        self.assertEqual(loaded_review.reviewer, reviewer)
        self.assertEqual(loaded_review.status, "pending")
        self.assertEqual(len(loaded_review.access_records), len(self.mock_records))

    @patch("tools.access_review_attestation.ACCESS_REVIEWS_COMPLETED_TOTAL")
    def test_metrics_increment_on_attestation(self, mock_metric):
        """Test that metrics are incremented when review is attested."""
        # Create and attest to a review
        reviewer = "security_team"
        review = self.workflow.create_review_cycle(reviewer, self.mock_records)
        self.workflow.attest_review(review.review_id, reviewer, ["Actions"])

        # Check that metric was incremented
        mock_metric.inc.assert_called_once()

    def test_cli_export(self):
        """Test CLI export functionality."""
        import subprocess
        import sys

        # Run CLI export
        result = subprocess.run(
            [sys.executable, "tools/access_review_attestation.py", "export"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Exported", result.stdout)
        self.assertIn("access records", result.stdout)

    def test_cli_create_review(self):
        """Test CLI create review functionality."""
        import subprocess
        import sys

        # Run CLI create review
        result = subprocess.run(
            [sys.executable, "tools/access_review_attestation.py", "create-review", "--reviewer", "test_reviewer"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Created review", result.stdout)

    def test_cli_list_pending(self):
        """Test CLI list pending reviews functionality."""
        import subprocess
        import sys

        # First create a review
        subprocess.run(
            [sys.executable, "tools/access_review_attestation.py", "create-review", "--reviewer", "test_reviewer"],
            capture_output=True,
            cwd=Path(__file__).parent.parent,
        )

        # Then list pending
        result = subprocess.run(
            [sys.executable, "tools/access_review_attestation.py", "list-pending"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("pending reviews", result.stdout)
        self.assertIn("test_reviewer", result.stdout)


if __name__ == "__main__":
    unittest.main()
