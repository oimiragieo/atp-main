"""GAP-347: PEFT fine-tune pipeline skeleton (LoRA).

Provides a framework for parameter-efficient fine-tuning using LoRA adapters.
Includes training configuration, provenance tracking, and metrics collection.
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from metrics.registry import REGISTRY


@dataclass
class LoRAConfig:
    """Configuration for LoRA fine-tuning."""

    rank: int = 16
    alpha: int = 32
    dropout: float = 0.05
    target_modules: list[str] = None

    def __post_init__(self):
        if self.target_modules is None:
            self.target_modules = ["q_proj", "k_proj", "v_proj", "o_proj"]

    def to_dict(self) -> dict[str, Any]:
        return {"rank": self.rank, "alpha": self.alpha, "dropout": self.dropout, "target_modules": self.target_modules}


@dataclass
class TrainingConfig:
    """Complete training configuration for PEFT fine-tuning."""

    base_model: str
    lora_config: LoRAConfig
    output_dir: str
    training_data_path: str
    num_epochs: int = 3
    batch_size: int = 4
    learning_rate: float = 2e-4
    warmup_steps: int = 100
    save_steps: int = 500
    eval_steps: int = 500
    max_seq_length: int = 512
    gradient_accumulation_steps: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_model": self.base_model,
            "lora_config": self.lora_config.to_dict(),
            "output_dir": self.output_dir,
            "training_data_path": self.training_data_path,
            "num_epochs": self.num_epochs,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "warmup_steps": self.warmup_steps,
            "save_steps": self.save_steps,
            "eval_steps": self.eval_steps,
            "max_seq_length": self.max_seq_length,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
        }


class PEFTFineTunePipeline:
    """PEFT fine-tuning pipeline with LoRA and provenance tracking."""

    def __init__(self):
        # GAP-347: PEFT fine-tuning metrics
        self._peft_jobs_completed_total = REGISTRY.counter("peft_jobs_completed_total")
        self._peft_jobs_failed_total = REGISTRY.counter("peft_jobs_failed_total")
        self._peft_training_time_seconds = REGISTRY.histogram(
            "peft_training_time_seconds", buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0, 1800.0, 3600.0]
        )

        # Default configurations
        self._default_lora_config = LoRAConfig()
        self._job_history: list[dict[str, Any]] = []

    def create_training_config(
        self, base_model: str, training_data_path: str, output_dir: str, lora_rank: int = 16, **kwargs
    ) -> TrainingConfig:
        """Create a training configuration for PEFT fine-tuning.

        Args:
            base_model: Base model to fine-tune
            training_data_path: Path to training data
            output_dir: Output directory for adapters
            lora_rank: LoRA rank (default 16)
            **kwargs: Additional training parameters

        Returns:
            TrainingConfig: Complete training configuration
        """
        lora_config = LoRAConfig(rank=lora_rank)

        # Override default config with kwargs
        for key, value in kwargs.items():
            if hasattr(lora_config, key):
                setattr(lora_config, key, value)

        config = TrainingConfig(
            base_model=base_model, lora_config=lora_config, output_dir=output_dir, training_data_path=training_data_path
        )

        # Override training config with remaining kwargs
        for key, value in kwargs.items():
            if hasattr(config, key) and key not in ["rank", "alpha", "dropout", "target_modules"]:
                setattr(config, key, value)

        return config

    def generate_provenance_record(self, config: TrainingConfig, job_id: str) -> dict[str, Any]:
        """Generate provenance record for training job.

        Args:
            config: Training configuration
            job_id: Unique job identifier

        Returns:
            Dict containing provenance information
        """
        timestamp = int(time.time())

        # Create content hash for reproducibility
        config_str = json.dumps(config.to_dict(), sort_keys=True)
        content_hash = hashlib.sha256(config_str.encode()).hexdigest()

        provenance = {
            "job_id": job_id,
            "timestamp": timestamp,
            "config": config.to_dict(),
            "content_hash": content_hash,
            "pipeline_version": "1.0.0",
            "framework": "peft-lora",
        }

        return provenance

    def save_provenance_record(self, provenance: dict[str, Any], output_dir: str) -> str:
        """Save provenance record to file.

        Args:
            provenance: Provenance record
            output_dir: Directory to save record

        Returns:
            Path to saved record file
        """
        os.makedirs(output_dir, exist_ok=True)
        record_path = os.path.join(output_dir, "provenance.json")

        with open(record_path, "w") as f:
            json.dump(provenance, f, indent=2)

        return record_path

    def dry_run_training(self, config: TrainingConfig) -> dict[str, Any]:
        """Perform a dry run of the training process (no actual training).

        Args:
            config: Training configuration

        Returns:
            Dict with dry run results
        """
        start_time = time.time()

        # Simulate training steps
        total_steps = (1000 // config.batch_size) * config.num_epochs  # Rough estimate
        simulated_steps = min(10, total_steps)  # Just simulate first few steps

        # Simulate some processing time
        time.sleep(0.1 * simulated_steps)

        end_time = time.time()
        training_time = end_time - start_time

        # Record metrics
        self._peft_training_time_seconds.observe(training_time)

        result = {
            "job_id": f"dry_run_{int(start_time)}",
            "status": "completed",
            "training_time_seconds": training_time,
            "simulated_steps": simulated_steps,
            "total_estimated_steps": total_steps,
            "config": config.to_dict(),
            "dry_run": True,
        }

        # Generate and save provenance
        provenance = self.generate_provenance_record(config, result["job_id"])
        result["provenance"] = provenance

        # Store in job history
        self._job_history.append(result)

        return result

    def get_job_history(self) -> list[dict[str, Any]]:
        """Get history of all training jobs."""
        return self._job_history.copy()

    def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        """Get status of a specific job."""
        for job in self._job_history:
            if job.get("job_id") == job_id:
                return job.copy()
        return None

    def validate_training_config(self, config: TrainingConfig) -> list[str]:
        """Validate training configuration.

        Args:
            config: Configuration to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check required fields
        if not config.base_model:
            errors.append("base_model is required")

        if not config.training_data_path:
            errors.append("training_data_path is required")

        if not os.path.exists(config.training_data_path):
            errors.append(f"training_data_path does not exist: {config.training_data_path}")

        if not config.output_dir:
            errors.append("output_dir is required")

        # Validate LoRA config
        if config.lora_config.rank <= 0:
            errors.append("LoRA rank must be positive")

        if config.lora_config.alpha <= 0:
            errors.append("LoRA alpha must be positive")

        # Validate training parameters
        if config.num_epochs <= 0:
            errors.append("num_epochs must be positive")

        if config.batch_size <= 0:
            errors.append("batch_size must be positive")

        if config.learning_rate <= 0:
            errors.append("learning_rate must be positive")

        return errors


# Global instance
peft_pipeline = PEFTFineTunePipeline()
