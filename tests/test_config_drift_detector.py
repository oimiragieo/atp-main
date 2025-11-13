#!/usr/bin/env python3
"""Tests for Config Drift & Security Baseline Detector."""

import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from tools.config_drift_detector import (
    ConfigDriftDetector,
    ConfigFile,
    DriftAlert,
)


class TestConfigDriftDetector:
    """Test suite for ConfigDriftDetector."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.baseline_store = self.temp_dir / "baselines.json"
        self.detector = ConfigDriftDetector(self.baseline_store)

    def teardown_method(self):
        """Clean up test fixtures."""
        # Clean up temp directory
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_test_config(self, name: str, content: str) -> Path:
        """Create a test configuration file."""
        config_path = self.temp_dir / name
        config_path.write_text(content)
        return config_path

    def test_initialization(self):
        """Test detector initialization."""
        assert self.detector.baselines == {}
        assert self.detector.baseline_store == self.baseline_store

    def test_calculate_hash(self):
        """Test hash calculation."""
        config_path = self.create_test_config("test.json", '{"key": "value"}')
        hash_value = self.detector._calculate_hash(config_path)
        assert len(hash_value) == 64  # SHA256 hex length

        # Same content should produce same hash
        config_path2 = self.create_test_config("test2.json", '{"key": "value"}')
        hash_value2 = self.detector._calculate_hash(config_path2)
        assert hash_value == hash_value2

        # Different content should produce different hash
        config_path3 = self.create_test_config("test3.json", '{"key": "different"}')
        hash_value3 = self.detector._calculate_hash(config_path3)
        assert hash_value != hash_value3

    def test_get_security_level(self):
        """Test security level determination."""
        # High security files
        high_path = self.temp_dir / "secrets.json"
        assert self.detector._get_security_level(high_path) == "high"

        # Medium security files
        medium_path = self.temp_dir / "config.json"
        assert self.detector._get_security_level(medium_path) == "medium"

        # Low security files
        low_path = self.temp_dir / "readme.txt"
        assert self.detector._get_security_level(low_path) == "low"

    def test_should_exclude(self):
        """Test file exclusion logic."""
        exclude_patterns = {".git", "node_modules"}

        # Should exclude
        git_path = self.temp_dir / ".git" / "config"
        assert self.detector._should_exclude(git_path, exclude_patterns)

        node_path = self.temp_dir / "node_modules" / "package.json"
        assert self.detector._should_exclude(node_path, exclude_patterns)

        # Should exclude baseline store
        assert self.detector._should_exclude(self.baseline_store, exclude_patterns)

        # Should exclude other hidden files
        hidden_path = self.temp_dir / ".hidden" / "config"
        assert self.detector._should_exclude(hidden_path, exclude_patterns)

        # Should not exclude normal files
        normal_path = self.temp_dir / "config.json"
        assert not self.detector._should_exclude(normal_path, exclude_patterns)

    def test_establish_baseline(self):
        """Test baseline establishment."""
        # Create test config files
        config1 = self.create_test_config("config.json", '{"setting": "value"}')
        config2 = self.create_test_config("secrets.json", '{"secret": "key"}')

        # Establish baseline
        count = self.detector.establish_baseline(self.temp_dir)
        assert count == 2

        # Check baselines were created
        assert str(config1) in self.detector.baselines
        assert str(config2) in self.detector.baselines

        # Check baseline data
        baseline1 = self.detector.baselines[str(config1)]
        assert baseline1.path == str(config1)
        assert baseline1.security_level == "medium"  # config.json

        baseline2 = self.detector.baselines[str(config2)]
        assert baseline2.path == str(config2)
        assert baseline2.security_level == "high"  # secrets.json

        # Check baselines were saved
        assert self.baseline_store.exists()

    def test_scan_no_drift(self):
        """Test scanning when no drift has occurred."""
        # Create and baseline config
        self.create_test_config("config.json", '{"setting": "value"}')
        self.detector.establish_baseline(self.temp_dir)

        # Scan for drift
        alerts = self.detector.scan_for_drift(self.temp_dir)
        assert len(alerts) == 0

    def test_scan_modified_file(self):
        """Test scanning detects modified files."""
        # Create and baseline config
        config = self.create_test_config("config.json", '{"setting": "value"}')
        self.detector.establish_baseline(self.temp_dir)

        # Modify the file
        time.sleep(0.1)  # Ensure different timestamp
        config.write_text('{"setting": "modified"}')

        # Scan for drift
        alerts = self.detector.scan_for_drift(self.temp_dir)
        assert len(alerts) == 1

        alert = alerts[0]
        assert alert.file_path == str(config)
        assert alert.change_type == "modified"
        assert alert.security_level == "medium"
        assert alert.baseline_hash != alert.current_hash

    def test_scan_deleted_file(self):
        """Test scanning detects deleted files."""
        # Create and baseline config
        config = self.create_test_config("config.json", '{"setting": "value"}')
        self.detector.establish_baseline(self.temp_dir)

        # Delete the file
        config.unlink()

        # Scan for drift
        alerts = self.detector.scan_for_drift(self.temp_dir)
        assert len(alerts) == 1

        alert = alerts[0]
        assert alert.file_path == str(config)
        assert alert.change_type == "deleted"
        assert alert.security_level == "medium"
        assert alert.current_hash == ""

    def test_scan_new_file(self):
        """Test scanning detects new files."""
        # Establish baseline (empty)
        self.detector.establish_baseline(self.temp_dir)

        # Create new config file
        config = self.create_test_config("new_config.json", '{"new": "setting"}')

        # Scan for drift
        alerts = self.detector.scan_for_drift(self.temp_dir)
        assert len(alerts) == 1

        alert = alerts[0]
        assert alert.file_path == str(config)
        assert alert.change_type == "new"
        assert alert.security_level == "medium"
        assert alert.baseline_hash == ""

    def test_exclude_patterns(self):
        """Test exclusion patterns work correctly."""
        # Create config in excluded directory
        excluded_dir = self.temp_dir / "node_modules"
        excluded_dir.mkdir()
        config = excluded_dir / "config.json"
        config.write_text('{"excluded": "config"}')

        # Establish baseline
        count = self.detector.establish_baseline(self.temp_dir)
        assert count == 0  # Should exclude node_modules

        # Create non-excluded config
        self.create_test_config("normal.json", '{"normal": "config"}')
        count = self.detector.establish_baseline(self.temp_dir)
        assert count == 1

    def test_list_baselines(self):
        """Test listing baselines."""
        # Initially empty
        baselines = self.detector.list_baselines()
        assert len(baselines) == 0

        # Add baseline
        config = self.create_test_config("config.json", '{"test": "data"}')
        self.detector.establish_baseline(self.temp_dir)

        baselines = self.detector.list_baselines()
        assert len(baselines) == 1
        assert baselines[0].path == str(config)

    def test_baseline_persistence(self):
        """Test baseline persistence across detector instances."""
        # Create baseline with first detector
        config = self.create_test_config("config.json", '{"persistent": "test"}')
        detector1 = ConfigDriftDetector(self.baseline_store)
        detector1.establish_baseline(self.temp_dir)

        # Create second detector and verify it loads baselines
        detector2 = ConfigDriftDetector(self.baseline_store)
        assert len(detector2.baselines) == 1
        assert str(config) in detector2.baselines

    def test_scan_with_exclude_patterns(self):
        """Test scanning with custom exclude patterns."""
        # Create configs
        config1 = self.create_test_config("config.json", '{"include": "this"}')
        config2 = self.create_test_config("temp_config.json", '{"exclude": "this"}')

        # Establish baseline
        self.detector.establish_baseline(self.temp_dir)

        # Modify both files
        config1.write_text('{"include": "modified"}')
        config2.write_text('{"exclude": "modified"}')

        # Scan with exclude pattern
        alerts = self.detector.scan_for_drift(self.temp_dir, ["temp_config.json"])
        assert len(alerts) == 1
        assert alerts[0].file_path == str(config1)

    @patch("tools.config_drift_detector.CONFIG_DRIFT_ALERTS_TOTAL")
    def test_metrics_integration(self, mock_metric):
        """Test metrics integration."""
        # Create and baseline config
        config = self.create_test_config("config.json", '{"test": "metrics"}')
        self.detector.establish_baseline(self.temp_dir)

        # Modify file to trigger alert
        config.write_text('{"test": "modified"}')

        # Scan for drift
        self.detector.scan_for_drift(self.temp_dir)

        # Verify metric was incremented
        if mock_metric:
            mock_metric.inc.assert_called_once()


class TestConfigFile:
    """Test ConfigFile dataclass."""

    def test_config_file_creation(self):
        """Test ConfigFile creation."""
        config = ConfigFile(
            path="/path/to/config.json",
            hash_value="abc123",
            last_modified=1234567890.0,
            file_size=1024,
            security_level="medium",
        )

        assert config.path == "/path/to/config.json"
        assert config.hash_value == "abc123"
        assert config.last_modified == 1234567890.0
        assert config.file_size == 1024
        assert config.security_level == "medium"


class TestDriftAlert:
    """Test DriftAlert dataclass."""

    def test_drift_alert_creation(self):
        """Test DriftAlert creation."""
        alert = DriftAlert(
            file_path="/path/to/config.json",
            baseline_hash="old_hash",
            current_hash="new_hash",
            change_type="modified",
            security_level="high",
            timestamp=1234567890.0,
        )

        assert alert.file_path == "/path/to/config.json"
        assert alert.baseline_hash == "old_hash"
        assert alert.current_hash == "new_hash"
        assert alert.change_type == "modified"
        assert alert.security_level == "high"
        assert alert.timestamp == 1234567890.0


class TestCLI:
    """Test CLI interface."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cli_baseline(self, capsys):
        """Test CLI baseline command."""
        from tools.config_drift_detector import main

        # Create test config
        config = self.temp_dir / "config.json"
        config.write_text('{"test": "baseline"}')

        # Run baseline command
        with patch("sys.argv", ["config_drift_detector.py", "baseline", str(self.temp_dir)]):
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "Established baselines for 1 configuration files" in captured.out

    def test_cli_scan_no_drift(self, capsys):
        """Test CLI scan command with no drift."""
        from tools.config_drift_detector import main

        # Create and baseline config
        config = self.temp_dir / "config.json"
        config.write_text('{"test": "no_drift"}')

        # Baseline first
        with patch("sys.argv", ["config_drift_detector.py", "baseline", str(self.temp_dir)]):
            main()

        # Scan
        with patch("sys.argv", ["config_drift_detector.py", "scan", str(self.temp_dir)]):
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "No configuration drift detected" in captured.out

    def test_cli_scan_with_drift(self, capsys):
        """Test CLI scan command with drift."""
        from tools.config_drift_detector import main

        # Create and baseline config
        config = self.temp_dir / "config.json"
        config.write_text('{"test": "original"}')

        # Baseline first
        with patch("sys.argv", ["config_drift_detector.py", "baseline", str(self.temp_dir)]):
            main()

        # Modify file
        config.write_text('{"test": "modified"}')

        # Scan
        with patch("sys.argv", ["config_drift_detector.py", "scan", str(self.temp_dir)]):
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "Found 1 configuration drift" in captured.out
        assert "MODIFIED:" in captured.out

    def test_cli_list_baselines(self, capsys):
        """Test CLI list-baselines command."""
        from tools.config_drift_detector import main

        # Create and baseline config with unique baseline store
        config = self.temp_dir / "config.json"
        config.write_text('{"test": "list"}')
        unique_baseline = self.temp_dir / "unique_baselines.json"

        # Baseline first with unique store
        with patch("sys.argv", ["config_drift_detector.py", "baseline", str(self.temp_dir)]):
            with patch("tools.config_drift_detector.ConfigDriftDetector") as mock_detector:
                mock_instance = mock_detector.return_value
                mock_instance.baseline_store = unique_baseline
                mock_instance.establish_baseline.return_value = 1
                main()

        # List baselines with unique store
        with patch("sys.argv", ["config_drift_detector.py", "list-baselines"]):
            with patch("tools.config_drift_detector.ConfigDriftDetector") as mock_detector:
                mock_instance = mock_detector.return_value
                mock_instance.baseline_store = unique_baseline
                mock_instance.list_baselines.return_value = [
                    ConfigFile(
                        path=str(config),
                        hash_value="testhash",
                        last_modified=1234567890.0,
                        file_size=1024,
                        security_level="medium",
                    )
                ]
                result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "Established baselines for 1 files" in captured.out
        assert "config.json" in captured.out

    def test_cli_alert_flag(self, capsys):
        """Test CLI alert flag."""
        from tools.config_drift_detector import main

        # Create and baseline config
        config = self.temp_dir / "config.json"
        config.write_text('{"test": "alert"}')

        # Baseline first
        with patch("sys.argv", ["config_drift_detector.py", "baseline", str(self.temp_dir)]):
            main()

        # Modify file
        config.write_text('{"test": "modified"}')

        # Scan with alert flag
        with patch("sys.argv", ["config_drift_detector.py", "scan", str(self.temp_dir), "--alert"]):
            result = main()

        assert result == 1  # Should return 1 for alerts
        captured = capsys.readouterr()
        assert "ALERT: Configuration drift detected!" in captured.out
