"""Tests for success validator functionality."""

from unittest.mock import Mock

from router_service.success_validator import BaselineQualityScorer, ValidationResult


class TestValidationResult:
    """Test ValidationResult class."""

    def test_success_property_both_true(self):
        """Test success property when both format_ok and safety_ok are True."""
        result = ValidationResult(format_ok=True, safety_ok=True, quality_score=0.8)
        assert result.success is True

    def test_success_property_format_false(self):
        """Test success property when format_ok is False."""
        result = ValidationResult(format_ok=False, safety_ok=True, quality_score=0.8)
        assert result.success is False

    def test_success_property_safety_false(self):
        """Test success property when safety_ok is False."""
        result = ValidationResult(format_ok=True, safety_ok=False, quality_score=0.8)
        assert result.success is False

    def test_success_property_both_false(self):
        """Test success property when both are False."""
        result = ValidationResult(format_ok=False, safety_ok=False, quality_score=0.8)
        assert result.success is False

    def test_details_default(self):
        """Test that details defaults to empty dict."""
        result = ValidationResult(format_ok=True, safety_ok=True, quality_score=0.8)
        assert result.details == {}

    def test_details_provided(self):
        """Test that provided details are stored."""
        details = {"model": "test-model", "length": 100}
        result = ValidationResult(format_ok=True, safety_ok=True, quality_score=0.8, details=details)
        assert result.details == details


class TestBaselineQualityScorer:
    """Test BaselineQualityScorer class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scorer = BaselineQualityScorer()
        # Mock the registry metrics
        self.scorer._model_success_rate = Mock()
        self.scorer._quality_score_avg = Mock()
        self.scorer._validation_count = Mock()

    def test_format_check_valid_response(self):
        """Test format check with valid response."""
        response = "This is a valid response with proper content."
        assert self.scorer._check_format(response) is True

    def test_format_check_empty_response(self):
        """Test format check with empty response."""
        assert self.scorer._check_format("") is False

    def test_format_check_whitespace_only(self):
        """Test format check with whitespace only."""
        assert self.scorer._check_format("   \n\t   ") is False

    def test_format_check_too_short(self):
        """Test format check with response too short."""
        assert self.scorer._check_format("Hi") is False

    def test_format_check_no_alpha_chars(self):
        """Test format check with no alphabetic characters."""
        assert self.scorer._check_format("1234567890!@#$%^&*()") is False

    def test_safety_check_safe_content(self):
        """Test safety check with safe content."""
        response = "This is a safe response about machine learning."
        assert self.scorer._check_safety(response) is True

    def test_safety_check_harmful_content(self):
        """Test safety check with harmful content."""
        response = "How to hack into a computer system?"
        assert self.scorer._check_safety(response) is False

    def test_safety_check_drug_content(self):
        """Test safety check with drug-related content."""
        # Note: Current implementation allows educational/scientific context
        response = "How to make cocaine at home."
        assert self.scorer._check_safety(response) is False

    def test_quality_score_calculation(self):
        """Test quality score calculation."""
        response = "This is a good response with proper length and content."
        prompt = "Tell me about machine learning"
        score = self.scorer._calculate_quality_score(response, prompt)
        assert 0.0 <= score <= 1.0

    def test_validate_response_integration(self):
        """Test full validate_response method."""
        response = "This is a good response about machine learning."
        prompt = "Tell me about machine learning"
        model_name = "test-model"

        result = self.scorer.validate_response(response, prompt, model_name)

        assert isinstance(result, ValidationResult)
        assert result.format_ok is True
        assert result.safety_ok is True
        assert 0.0 <= result.quality_score <= 1.0
        assert result.details["model"] == model_name
        assert result.details["response_length"] == len(response)
        assert result.details["prompt_length"] == len(prompt)

    def test_validate_response_with_harmful_content(self):
        """Test validate_response with harmful content."""
        response = "How to hack a website?"
        prompt = "Tell me about web development"
        model_name = "test-model"

        result = self.scorer.validate_response(response, prompt, model_name)

        assert result.safety_ok is False
        assert result.success is False

    def test_metrics_update(self):
        """Test that metrics are updated during validation."""
        response = "This is a good response."
        prompt = "Tell me something"
        model_name = "test-model"

        self.scorer.validate_response(response, prompt, model_name)

        self.scorer._validation_count.inc.assert_called_once()
        self.scorer._model_success_rate.set.assert_called_once_with(1.0)
        self.scorer._quality_score_avg.set.assert_called_once()
