"""Tests for GAP-347: PEFT fine-tune pipeline skeleton (LoRA)."""

import json
import os
import tempfile

from router_service.peft_fine_tune_pipeline import LoRAConfig, PEFTFineTunePipeline, TrainingConfig


class TestLoRAConfig:
    """Test LoRA configuration."""

    def test_default_config(self):
        """Test default LoRA configuration."""
        config = LoRAConfig()
        assert config.rank == 16
        assert config.alpha == 32
        assert config.dropout == 0.05
        assert config.target_modules == ["q_proj", "k_proj", "v_proj", "o_proj"]

    def test_custom_config(self):
        """Test custom LoRA configuration."""
        config = LoRAConfig(rank=8, alpha=16, dropout=0.1)
        assert config.rank == 8
        assert config.alpha == 16
        assert config.dropout == 0.1

    def test_to_dict(self):
        """Test configuration serialization."""
        config = LoRAConfig(rank=8)
        config_dict = config.to_dict()
        assert config_dict["rank"] == 8
        assert "target_modules" in config_dict


class TestTrainingConfig:
    """Test training configuration."""

    def test_default_config(self):
        """Test default training configuration."""
        config = TrainingConfig(
            base_model="test-model",
            lora_config=LoRAConfig(),
            output_dir="/tmp/output",  # noqa: S108
            training_data_path="/tmp/data.json",  # noqa: S108
        )

        assert config.base_model == "test-model"
        assert config.num_epochs == 3
        assert config.batch_size == 4
        assert config.learning_rate == 2e-4

    def test_to_dict(self):
        """Test training configuration serialization."""
        config = TrainingConfig(
            base_model="test-model",
            lora_config=LoRAConfig(),
            output_dir="/tmp/output",  # noqa: S108
            training_data_path="/tmp/data.json",  # noqa: S108
        )

        config_dict = config.to_dict()
        assert config_dict["base_model"] == "test-model"
        assert "lora_config" in config_dict


class TestPEFTFineTunePipeline:
    """Test PEFT fine-tuning pipeline."""

    def setup_method(self):
        """Reset pipeline before each test."""
        self.pipeline = PEFTFineTunePipeline()

    def test_create_training_config(self):
        """Test training configuration creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.pipeline.create_training_config(
                base_model="test-model",
                training_data_path=os.path.join(tmpdir, "data.json"),
                output_dir=os.path.join(tmpdir, "output"),
                lora_rank=8,
            )

            assert config.base_model == "test-model"
            assert config.lora_config.rank == 8
            assert config.num_epochs == 3

    def test_generate_provenance_record(self):
        """Test provenance record generation."""
        config = TrainingConfig(
            base_model="test-model",
            lora_config=LoRAConfig(),
            output_dir="/tmp/output",  # noqa: S108
            training_data_path="/tmp/data.json",  # noqa: S108
        )

        provenance = self.pipeline.generate_provenance_record(config, "test-job-123")

        assert provenance["job_id"] == "test-job-123"
        assert "timestamp" in provenance
        assert "content_hash" in provenance
        assert provenance["framework"] == "peft-lora"

    def test_save_provenance_record(self):
        """Test provenance record saving."""
        provenance = {"test": "data"}

        with tempfile.TemporaryDirectory() as tmpdir:
            record_path = self.pipeline.save_provenance_record(provenance, tmpdir)

            assert os.path.exists(record_path)
            with open(record_path) as f:
                saved_data = json.load(f)
                assert saved_data["test"] == "data"

    def test_dry_run_training(self):
        """Test dry run training simulation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = TrainingConfig(
                base_model="test-model",
                lora_config=LoRAConfig(),
                output_dir=tmpdir,
                training_data_path=os.path.join(tmpdir, "data.json"),
            )

            result = self.pipeline.dry_run_training(config)

            assert result["status"] == "completed"
            assert result["dry_run"] is True
            assert "training_time_seconds" in result
            assert "provenance" in result
            assert "job_id" in result

    def test_get_job_history(self):
        """Test job history retrieval."""
        # Initially empty
        history = self.pipeline.get_job_history()
        assert history == []

        # After a dry run
        with tempfile.TemporaryDirectory() as tmpdir:
            config = TrainingConfig(
                base_model="test-model",
                lora_config=LoRAConfig(),
                output_dir=tmpdir,
                training_data_path=os.path.join(tmpdir, "data.json"),
            )

            self.pipeline.dry_run_training(config)
            history = self.pipeline.get_job_history()
            assert len(history) == 1

    def test_get_job_status(self):
        """Test job status retrieval."""
        # Non-existent job
        status = self.pipeline.get_job_status("non-existent")
        assert status is None

        # After creating a job
        with tempfile.TemporaryDirectory() as tmpdir:
            config = TrainingConfig(
                base_model="test-model",
                lora_config=LoRAConfig(),
                output_dir=tmpdir,
                training_data_path=os.path.join(tmpdir, "data.json"),
            )

            result = self.pipeline.dry_run_training(config)
            job_id = result["job_id"]

            status = self.pipeline.get_job_status(job_id)
            assert status is not None
            assert status["job_id"] == job_id

    def test_validate_training_config_valid(self):
        """Test validation of valid training config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a dummy data file
            data_file = os.path.join(tmpdir, "data.json")
            with open(data_file, "w") as f:
                json.dump({"test": "data"}, f)

            config = TrainingConfig(
                base_model="test-model", lora_config=LoRAConfig(), output_dir=tmpdir, training_data_path=data_file
            )

            errors = self.pipeline.validate_training_config(config)
            assert errors == []

    def test_validate_training_config_invalid(self):
        """Test validation of invalid training config."""
        config = TrainingConfig(
            base_model="",  # Invalid: empty
            lora_config=LoRAConfig(rank=-1),  # Invalid: negative rank
            output_dir="",
            training_data_path="/nonexistent/file.json",
        )

        errors = self.pipeline.validate_training_config(config)
        assert len(errors) > 0
        assert any("base_model" in error for error in errors)
        assert any("rank" in error for error in errors)
        assert any("training_data_path" in error for error in errors)

    def test_validate_training_config_missing_data_file(self):
        """Test validation when training data file doesn't exist."""
        config = TrainingConfig(
            base_model="test-model",
            lora_config=LoRAConfig(),
            output_dir="/tmp",  # noqa: S108
            training_data_path="/nonexistent/file.json",
        )

        errors = self.pipeline.validate_training_config(config)
        assert any("training_data_path does not exist" in error for error in errors)

    def test_metric_updates(self):
        """Test that metrics are updated during operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = TrainingConfig(
                base_model="test-model",
                lora_config=LoRAConfig(),
                output_dir=tmpdir,
                training_data_path=os.path.join(tmpdir, "data.json"),
            )

            # This should update the training time histogram
            result = self.pipeline.dry_run_training(config)
            assert result["training_time_seconds"] >= 0
