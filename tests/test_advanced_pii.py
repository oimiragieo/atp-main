"""
Tests for Advanced PII Detection and Redaction System
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "memory-gateway"))

from advanced_pii import (
    AdvancedPIISystem,
    DataClassification,
    PIIDetector,
    PIIMatch,
    PIIRedactor,
    PIIType,
    RedactionAction,
    RedactionPolicy,
    detect_pii,
    redact_object,
    redact_text,
)


class TestPIIDetector:
    """Test PII detection functionality"""

    def test_rule_based_detection(self):
        """Test rule-based PII detection"""
        detector = PIIDetector()

        text = "Contact John Doe at john.doe@example.com or call (555) 123-4567. SSN: 123-45-6789"
        matches = detector.detect_pii_rules(text)

        # Should detect email, phone, and SSN
        pii_types = [match.pii_type for match in matches]
        assert PIIType.EMAIL in pii_types
        assert PIIType.PHONE in pii_types
        assert PIIType.SSN in pii_types

        # Check specific matches
        email_match = next(m for m in matches if m.pii_type == PIIType.EMAIL)
        assert email_match.text == "john.doe@example.com"
        assert email_match.confidence == 1.0
        assert email_match.detection_method == "regex"

    def test_custom_patterns(self):
        """Test custom pattern addition"""
        detector = PIIDetector()

        # Add custom pattern for employee ID
        detector.add_custom_pattern(PIIType.CUSTOM, r"\bEMP\d{6}\b", "employee_id")

        text = "Employee EMP123456 has access to the system"
        matches = detector.detect_pii_rules(text)

        custom_matches = [m for m in matches if m.pii_type == PIIType.CUSTOM]
        assert len(custom_matches) == 1
        assert custom_matches[0].text == "EMP123456"
        assert custom_matches[0].detection_method == "custom_employee_id"

    def test_ip_address_detection(self):
        """Test IP address detection"""
        detector = PIIDetector()

        text = "Server IP is 192.168.1.100 and external IP is 203.0.113.42"
        matches = detector.detect_pii_rules(text)

        ip_matches = [m for m in matches if m.pii_type == PIIType.IP_ADDRESS]
        assert len(ip_matches) == 2
        assert "192.168.1.100" in [m.text for m in ip_matches]
        assert "203.0.113.42" in [m.text for m in ip_matches]

    def test_credit_card_detection(self):
        """Test credit card number detection"""
        detector = PIIDetector()

        text = "Credit card: 4532 1234 5678 9012 and 5555-4444-3333-2222"
        matches = detector.detect_pii_rules(text)

        cc_matches = [m for m in matches if m.pii_type == PIIType.CREDIT_CARD]
        assert len(cc_matches) == 2

    @patch("memory_gateway.advanced_pii.TRANSFORMERS_AVAILABLE", True)
    @patch("memory_gateway.advanced_pii.pipeline")
    def test_ml_detection_mock(self, mock_pipeline):
        """Test ML-based detection with mocked transformers"""
        # Mock the NER pipeline
        mock_ner = Mock()
        mock_ner.return_value = [{"entity_group": "PER", "score": 0.95, "start": 8, "end": 16, "word": "John Doe"}]
        mock_pipeline.return_value = mock_ner

        detector = PIIDetector()
        detector.ml_models["ner_pipeline"] = mock_ner

        text = "Contact John Doe for more information"
        matches = detector.detect_pii_ml(text)

        assert len(matches) == 1
        assert matches[0].pii_type == PIIType.PERSON_NAME
        assert matches[0].text == "John Doe"
        assert matches[0].confidence == 0.95
        assert matches[0].detection_method == "bert_ner"

    def test_deduplication(self):
        """Test match deduplication"""
        detector = PIIDetector()

        # Create overlapping matches
        matches = [
            PIIMatch(PIIType.PERSON_NAME, 0, 8, "John Doe", 0.9, "method1"),
            PIIMatch(PIIType.PERSON_NAME, 5, 8, "Doe", 0.8, "method2"),  # Overlaps
            PIIMatch(PIIType.EMAIL, 20, 35, "test@example.com", 1.0, "regex"),
        ]

        deduplicated = detector._deduplicate_matches(matches)

        # Should keep the higher confidence match and the non-overlapping email
        assert len(deduplicated) == 2
        assert deduplicated[0].text == "John Doe"  # Higher confidence
        assert deduplicated[1].text == "test@example.com"

    def test_context_extraction(self):
        """Test context extraction around matches"""
        detector = PIIDetector()

        text = "This is a long sentence with john.doe@example.com in the middle of it"
        context = detector._get_context(text, 30, 49)  # Position of email

        assert "john.doe@example.com" in context
        assert len(context) <= 100  # Default window is 50 chars each side


class TestPIIRedactor:
    """Test PII redaction functionality"""

    def test_default_policies(self):
        """Test default redaction policies"""
        redactor = PIIRedactor()

        # Should have policies for common PII types
        policy_types = [p.pii_type for p in redactor.policies]
        assert PIIType.EMAIL in policy_types
        assert PIIType.PHONE in policy_types
        assert PIIType.SSN in policy_types
        assert PIIType.CREDIT_CARD in policy_types

    def test_replace_action(self):
        """Test replace redaction action"""
        redactor = PIIRedactor()

        match = PIIMatch(PIIType.EMAIL, 0, 19, "john.doe@example.com", 1.0, "regex")
        policy = RedactionPolicy(PIIType.EMAIL, RedactionAction.REPLACE, "[EMAIL]")

        result = redactor._apply_redaction_action("john.doe@example.com", match, policy)
        assert result == "[EMAIL]"

    def test_mask_action(self):
        """Test mask redaction action"""
        redactor = PIIRedactor()

        match = PIIMatch(PIIType.PHONE, 0, 14, "(555) 123-4567", 1.0, "regex")
        policy = RedactionPolicy(PIIType.PHONE, RedactionAction.MASK, visible_chars=4, preserve_format=True)

        result = redactor._apply_redaction_action("(555) 123-4567", match, policy)
        # Should preserve format and show last 4 characters
        assert result.endswith("4567")
        assert "(" in result and ")" in result and " " in result and "-" in result

    def test_hash_action(self):
        """Test hash redaction action"""
        redactor = PIIRedactor()

        match = PIIMatch(PIIType.SSN, 0, 11, "123-45-6789", 1.0, "regex")
        policy = RedactionPolicy(PIIType.SSN, RedactionAction.HASH)

        result = redactor._apply_redaction_action("123-45-6789", match, policy)
        assert result.startswith("[HASH:")
        assert result.endswith("]")
        assert len(result) == 15  # [HASH:8chars]

    def test_remove_action(self):
        """Test remove redaction action"""
        redactor = PIIRedactor()

        match = PIIMatch(PIIType.EMAIL, 0, 19, "john.doe@example.com", 1.0, "regex")
        policy = RedactionPolicy(PIIType.EMAIL, RedactionAction.REMOVE)

        result = redactor._apply_redaction_action("john.doe@example.com", match, policy)
        assert result == ""

    def test_text_redaction(self):
        """Test complete text redaction"""
        redactor = PIIRedactor()

        text = "Contact john.doe@example.com or (555) 123-4567"
        matches = [
            PIIMatch(PIIType.EMAIL, 8, 27, "john.doe@example.com", 1.0, "regex"),
            PIIMatch(PIIType.PHONE, 31, 45, "(555) 123-4567", 1.0, "regex"),
        ]

        redacted_text, audit_entry = redactor.redact_text(text, matches, DataClassification.CONFIDENTIAL)

        assert "john.doe@example.com" not in redacted_text
        assert "(555) 123-4567" not in redacted_text
        assert "[REDACTED-EMAIL]" in redacted_text
        assert audit_entry is not None
        assert len(audit_entry.pii_matches) == 2

    def test_data_classification_policies(self):
        """Test different policies for different data classifications"""
        # Create policies for different classifications
        policies = [
            RedactionPolicy(
                PIIType.EMAIL, RedactionAction.MASK, visible_chars=3, data_classifications={DataClassification.PUBLIC}
            ),
            RedactionPolicy(
                PIIType.EMAIL,
                RedactionAction.REPLACE,
                "[CONFIDENTIAL-EMAIL]",
                data_classifications={DataClassification.CONFIDENTIAL},
            ),
        ]

        redactor = PIIRedactor(policies)

        # Test public classification
        public_policy = redactor.get_policy(PIIType.EMAIL, DataClassification.PUBLIC)
        assert public_policy.action == RedactionAction.MASK

        # Test confidential classification
        confidential_policy = redactor.get_policy(PIIType.EMAIL, DataClassification.CONFIDENTIAL)
        assert confidential_policy.action == RedactionAction.REPLACE


class TestAdvancedPIISystem:
    """Test complete PII system"""

    def test_complete_processing(self):
        """Test complete PII processing pipeline"""
        system = AdvancedPIISystem()

        text = "John Doe's email is john.doe@example.com and phone is (555) 123-4567"

        result = system.process_text(
            text, DataClassification.CONFIDENTIAL, tenant_id="test_tenant", user_id="test_user"
        )

        # Should not contain original PII
        assert "john.doe@example.com" not in result
        assert "(555) 123-4567" not in result

        # Should contain redacted versions
        assert "[REDACTED-EMAIL]" in result or "***" in result

    def test_process_with_matches(self):
        """Test processing with return matches"""
        system = AdvancedPIISystem()

        text = "Contact john.doe@example.com for details"

        redacted_text, matches, audit_entry = system.process_text(
            text, DataClassification.CONFIDENTIAL, return_matches=True
        )

        assert isinstance(matches, list)
        assert len(matches) > 0
        assert matches[0].pii_type == PIIType.EMAIL
        assert audit_entry is not None

    def test_audit_trail_storage(self):
        """Test audit trail storage and retrieval"""
        with tempfile.TemporaryDirectory() as temp_dir:
            system = AdvancedPIISystem()
            system.audit_storage_path = temp_dir

            text = "Test email: test@example.com"
            system.process_text(text, DataClassification.CONFIDENTIAL, tenant_id="test_tenant")

            # Check audit trail
            audit_entries = system.get_audit_trail(tenant_id="test_tenant")
            assert len(audit_entries) == 1
            assert audit_entries[0]["tenant_id"] == "test_tenant"

    def test_data_subject_request_export(self):
        """Test GDPR data subject export request"""
        with tempfile.TemporaryDirectory() as temp_dir:
            system = AdvancedPIISystem()
            system.audit_storage_path = temp_dir

            # Process some text with PII
            text = "User john.doe@example.com made a request"
            system.process_text(text, DataClassification.CONFIDENTIAL, user_id="john.doe@example.com")

            # Handle export request
            result = system.handle_data_subject_request("john.doe@example.com", "export")

            assert result["request_type"] == "export"
            assert result["entries_found"] >= 1
            assert "data" in result

    def test_data_subject_request_delete(self):
        """Test GDPR data subject deletion request"""
        system = AdvancedPIISystem()

        result = system.handle_data_subject_request("john.doe@example.com", "delete")

        assert result["request_type"] == "delete"
        assert result["status"] == "deletion_scheduled"


class TestConvenienceFunctions:
    """Test convenience functions"""

    def test_detect_pii_function(self):
        """Test standalone detect_pii function"""
        text = "Email: test@example.com, Phone: (555) 123-4567"
        matches = detect_pii(text)

        assert len(matches) >= 2
        pii_types = [match.pii_type for match in matches]
        assert PIIType.EMAIL in pii_types
        assert PIIType.PHONE in pii_types

    def test_redact_text_function(self):
        """Test standalone redact_text function"""
        text = "Contact john.doe@example.com for support"
        result = redact_text(text, DataClassification.CONFIDENTIAL)

        assert "john.doe@example.com" not in result
        assert "[REDACTED-EMAIL]" in result or "***" in result

    def test_redact_object_function(self):
        """Test redact_object function with nested data"""
        data = {
            "user": {
                "name": "John Doe",
                "email": "john.doe@example.com",
                "contacts": [
                    {"type": "phone", "value": "(555) 123-4567"},
                    {"type": "email", "value": "john.work@company.com"},
                ],
            },
            "message": "Please call (555) 987-6543 for assistance",
        }

        result = redact_object(data, DataClassification.CONFIDENTIAL)

        # Check that emails are redacted
        assert "john.doe@example.com" not in str(result)
        assert "john.work@company.com" not in str(result)

        # Check that phone numbers are redacted
        assert "(555) 123-4567" not in str(result)
        assert "(555) 987-6543" not in str(result)

        # Structure should be preserved
        assert "user" in result
        assert "contacts" in result["user"]
        assert isinstance(result["user"]["contacts"], list)


class TestConfigurationLoading:
    """Test configuration loading and custom patterns"""

    def test_config_loading(self):
        """Test loading configuration from file"""
        config_data = {"enable_ml_detection": False, "confidence_threshold": 0.9, "context_window": 100}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            detector = PIIDetector(config_path)
            assert detector.config["enable_ml_detection"] is False
            assert detector.config["confidence_threshold"] == 0.9
            assert detector.config["context_window"] == 100
        finally:
            Path(config_path).unlink()

    def test_invalid_regex_pattern(self):
        """Test handling of invalid regex patterns"""
        detector = PIIDetector()

        with pytest.raises(ValueError):
            detector.add_custom_pattern(PIIType.CUSTOM, "[invalid regex", "bad_pattern")


class TestMetricsIntegration:
    """Test metrics integration"""

    @patch("memory_gateway.advanced_pii.METRICS_AVAILABLE", True)
    @patch("memory_gateway.advanced_pii._CTR_PII_DETECTIONS")
    @patch("memory_gateway.advanced_pii._CTR_REDACTIONS")
    def test_metrics_recording(self, mock_redactions, mock_detections):
        """Test that metrics are recorded properly"""
        system = AdvancedPIISystem()

        text = "Email: test@example.com"
        system.process_text(text, DataClassification.CONFIDENTIAL)

        # Should record detection and redaction metrics
        mock_detections.labels.assert_called()
        mock_redactions.labels.assert_called()


class TestErrorHandling:
    """Test error handling and edge cases"""

    def test_empty_text(self):
        """Test handling of empty text"""
        system = AdvancedPIISystem()

        result = system.process_text("", DataClassification.CONFIDENTIAL)
        assert result == ""

    def test_no_pii_text(self):
        """Test handling of text with no PII"""
        system = AdvancedPIISystem()

        text = "This is a simple message with no personal information."
        result = system.process_text(text, DataClassification.CONFIDENTIAL)
        assert result == text  # Should be unchanged

    def test_very_long_text(self):
        """Test handling of very long text"""
        system = AdvancedPIISystem()

        # Create text longer than max_text_length
        long_text = "This is a test. " * 1000 + "Email: test@example.com"
        result = system.process_text(long_text, DataClassification.CONFIDENTIAL)

        # Should still process (may be truncated for ML)
        assert isinstance(result, str)

    def test_malformed_audit_storage(self):
        """Test handling of malformed audit storage"""
        with tempfile.TemporaryDirectory() as temp_dir:
            system = AdvancedPIISystem()
            system.audit_storage_path = temp_dir

            # Create malformed audit file
            audit_file = Path(temp_dir) / "pii_audit_2023-01-01.jsonl"
            with open(audit_file, "w") as f:
                f.write("invalid json line\n")
                f.write('{"valid": "json"}\n')

            # Should handle malformed entries gracefully
            entries = system.get_audit_trail()
            assert len(entries) == 1  # Only the valid entry


if __name__ == "__main__":
    pytest.main([__file__])
