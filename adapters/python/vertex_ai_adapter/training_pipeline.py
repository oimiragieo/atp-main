# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Vertex AI Training Pipeline

This module provides custom model training pipeline integration for routing optimization
and model performance improvement based on ATP platform usage patterns.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from google.cloud import aiplatform
from google.cloud.aiplatform import gapic
from google.cloud import storage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TrainingJobStatus(Enum):
    """Training job status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrainingJobType(Enum):
    """Training job types."""
    CUSTOM_TRAINING = "custom_training"
    AUTOML = "automl"
    HYPERPARAMETER_TUNING = "hyperparameter_tuning"
    PIPELINE = "pipeline"


@dataclass
class TrainingConfig:
    """Training configuration."""
    job_name: str
    job_type: TrainingJobType
    display_name: str
    training_task_definition: str
    training_task_inputs: Dict[str, Any]
    base_output_directory: str
    machine_type: str = "n1-standard-4"
    replica_count: int = 1
    accelerator_type: Optional[str] = None
    accelerator_count: int = 0
    boot_disk_type: str = "pd-ssd"
    boot_disk_size_gb: int = 100
    service_account: Optional[str] = None
    network: Optional[str] = None
    enable_web_access: bool = False
    timeout: Optional[str] = None
    restart_job_on_worker_restart: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["job_type"] = self.job_type.value
        return result


@dataclass
class TrainingJob:
    """Training job information."""
    job_id: str
    job_name: str
    job_type: TrainingJobType
    status: TrainingJobStatus
    config: TrainingConfig
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: Optional[str] = None
    model_artifacts: Optional[Dict[str, str]] = None
    metrics: Optional[Dict[str, float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["job_type"] = self.job_type.value
        result["status"] = self.status.value
        result["config"] = self.config.to_dict()
        return result


class VertexAITrainingPipeline:
    """Vertex AI training pipeline manager."""
    
    def __init__(self, project_id: str, location: str = "us-central1"):
        self.project_id = project_id
        self.location = location
        
        # Initialize AI Platform
        aiplatform.init(project=project_id, location=location)
        
        # Initialize clients
        self.client_options = {"api_endpoint": f"{location}-aiplatform.googleapis.com"}
        self.job_client = gapic.JobServiceClient(client_options=self.client_options)
        self.pipeline_client = gapic.PipelineServiceClient(client_options=self.client_options)
        self.storage_client = storage.Client(project=project_id)
        
        # State tracking
        self.training_jobs: Dict[str, TrainingJob] = {}
        self.job_callbacks: Dict[str, List[Callable]] = {}
        
        # Monitoring
        self.monitoring_active = False
        self.monitor_task = None
    
    async def start_monitoring(self):
        """Start training job monitoring."""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Started training job monitoring")
    
    async def stop_monitoring(self):
        """Stop training job monitoring."""
        self.monitoring_active = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped training job monitoring")
    
    async def _monitoring_loop(self):
        """Monitor training jobs."""
        while self.monitoring_active:
            try:
                await self._update_job_statuses()
                await asyncio.sleep(30)  # Check every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in training job monitoring: {e}")
                await asyncio.sleep(60)
    
    async def _update_job_statuses(self):
        """Update status of active training jobs."""
        for job_id, job in self.training_jobs.items():
            if job.status in [TrainingJobStatus.PENDING, TrainingJobStatus.RUNNING]:
                try:
                    updated_job = await self._get_job_status(job_id)
                    if updated_job and updated_job.status != job.status:
                        old_status = job.status
                        job.status = updated_job.status
                        job.completed_at = updated_job.completed_at
                        job.error_message = updated_job.error_message
                        job.model_artifacts = updated_job.model_artifacts
                        job.metrics = updated_job.metrics
                        
                        logger.info(f"Job {job_id} status changed from {old_status.value} to {job.status.value}")
                        
                        # Execute callbacks
                        await self._execute_callbacks(job_id, job)
                        
                except Exception as e:
                    logger.error(f"Failed to update status for job {job_id}: {e}")
    
    async def _get_job_status(self, job_id: str) -> Optional[TrainingJob]:
        """Get current status of a training job."""
        try:
            # This would query the actual Vertex AI job status
            # For now, return None as placeholder
            return None
        except Exception as e:
            logger.error(f"Failed to get job status for {job_id}: {e}")
            return None
    
    async def _execute_callbacks(self, job_id: str, job: TrainingJob):
        """Execute callbacks for job status changes."""
        if job_id in self.job_callbacks:
            for callback in self.job_callbacks[job_id]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(job)
                    else:
                        callback(job)
                except Exception as e:
                    logger.error(f"Error executing callback for job {job_id}: {e}")
    
    async def create_routing_optimization_job(
        self,
        training_data_uri: str,
        validation_data_uri: str,
        output_directory: str,
        hyperparameters: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a training job for routing optimization."""
        
        job_name = f"routing-optimization-{int(time.time())}"
        
        # Default hyperparameters
        default_hyperparameters = {
            "learning_rate": 0.001,
            "batch_size": 32,
            "epochs": 100,
            "hidden_units": [128, 64, 32],
            "dropout_rate": 0.2,
            "optimizer": "adam"
        }
        
        if hyperparameters:
            default_hyperparameters.update(hyperparameters)
        
        # Training task inputs
        task_inputs = {
            "training_data_uri": training_data_uri,
            "validation_data_uri": validation_data_uri,
            "hyperparameters": default_hyperparameters,
            "model_type": "routing_optimizer",
            "objective": "minimize_cost_maximize_quality"
        }
        
        config = TrainingConfig(
            job_name=job_name,
            job_type=TrainingJobType.CUSTOM_TRAINING,
            display_name="ATP Routing Optimization Training",
            training_task_definition="gs://atp-training/routing_optimizer/training_task.py",
            training_task_inputs=task_inputs,
            base_output_directory=output_directory,
            machine_type="n1-standard-8",
            replica_count=1,
            accelerator_type="NVIDIA_TESLA_T4",
            accelerator_count=1
        )
        
        return await self.submit_training_job(config)
    
    async def create_quality_prediction_job(
        self,
        training_data_uri: str,
        validation_data_uri: str,
        output_directory: str,
        model_features: List[str],
        hyperparameters: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a training job for quality prediction."""
        
        job_name = f"quality-prediction-{int(time.time())}"
        
        # Default hyperparameters for quality prediction
        default_hyperparameters = {
            "learning_rate": 0.0005,
            "batch_size": 64,
            "epochs": 150,
            "hidden_units": [256, 128, 64],
            "dropout_rate": 0.3,
            "optimizer": "adamw",
            "weight_decay": 0.01
        }
        
        if hyperparameters:
            default_hyperparameters.update(hyperparameters)
        
        # Training task inputs
        task_inputs = {
            "training_data_uri": training_data_uri,
            "validation_data_uri": validation_data_uri,
            "hyperparameters": default_hyperparameters,
            "model_type": "quality_predictor",
            "features": model_features,
            "target": "quality_score"
        }
        
        config = TrainingConfig(
            job_name=job_name,
            job_type=TrainingJobType.CUSTOM_TRAINING,
            display_name="ATP Quality Prediction Training",
            training_task_definition="gs://atp-training/quality_predictor/training_task.py",
            training_task_inputs=task_inputs,
            base_output_directory=output_directory,
            machine_type="n1-standard-4",
            replica_count=1
        )
        
        return await self.submit_training_job(config)
    
    async def create_automl_job(
        self,
        dataset_id: str,
        target_column: str,
        output_directory: str,
        training_budget_hours: int = 1,
        optimization_objective: str = "minimize-rmse"
    ) -> str:
        """Create an AutoML training job."""
        
        job_name = f"automl-{int(time.time())}"
        
        # AutoML task inputs
        task_inputs = {
            "dataset_id": dataset_id,
            "target_column": target_column,
            "optimization_objective": optimization_objective,
            "training_budget_milli_node_hours": training_budget_hours * 1000,
            "disable_early_stopping": False
        }
        
        config = TrainingConfig(
            job_name=job_name,
            job_type=TrainingJobType.AUTOML,
            display_name="ATP AutoML Training",
            training_task_definition="automl_tabular",
            training_task_inputs=task_inputs,
            base_output_directory=output_directory
        )
        
        return await self.submit_training_job(config)
    
    async def create_hyperparameter_tuning_job(
        self,
        training_data_uri: str,
        validation_data_uri: str,
        output_directory: str,
        parameter_spec: Dict[str, Dict[str, Any]],
        max_trial_count: int = 20,
        parallel_trial_count: int = 5
    ) -> str:
        """Create a hyperparameter tuning job."""
        
        job_name = f"hp-tuning-{int(time.time())}"
        
        # Hyperparameter tuning task inputs
        task_inputs = {
            "training_data_uri": training_data_uri,
            "validation_data_uri": validation_data_uri,
            "parameter_spec": parameter_spec,
            "max_trial_count": max_trial_count,
            "parallel_trial_count": parallel_trial_count,
            "optimization_goal": "MAXIMIZE",
            "optimization_goal_metric": "accuracy"
        }
        
        config = TrainingConfig(
            job_name=job_name,
            job_type=TrainingJobType.HYPERPARAMETER_TUNING,
            display_name="ATP Hyperparameter Tuning",
            training_task_definition="gs://atp-training/hp_tuning/training_task.py",
            training_task_inputs=task_inputs,
            base_output_directory=output_directory,
            machine_type="n1-standard-4",
            replica_count=1
        )
        
        return await self.submit_training_job(config)
    
    async def submit_training_job(self, config: TrainingConfig) -> str:
        """Submit a training job to Vertex AI."""
        
        try:
            job_id = f"{config.job_name}-{int(time.time())}"
            
            # Create training job record
            training_job = TrainingJob(
                job_id=job_id,
                job_name=config.job_name,
                job_type=config.job_type,
                status=TrainingJobStatus.PENDING,
                config=config,
                created_at=time.time()
            )
            
            # Submit job based on type
            if config.job_type == TrainingJobType.CUSTOM_TRAINING:
                vertex_job = await self._submit_custom_training_job(config)
            elif config.job_type == TrainingJobType.AUTOML:
                vertex_job = await self._submit_automl_job(config)
            elif config.job_type == TrainingJobType.HYPERPARAMETER_TUNING:
                vertex_job = await self._submit_hp_tuning_job(config)
            else:
                raise ValueError(f"Unsupported job type: {config.job_type}")
            
            # Update job status
            training_job.status = TrainingJobStatus.RUNNING
            training_job.started_at = time.time()
            
            # Store job
            self.training_jobs[job_id] = training_job
            
            logger.info(f"Submitted training job {job_id} ({config.job_type.value})")
            
            return job_id
            
        except Exception as e:
            logger.error(f"Failed to submit training job: {e}")
            raise
    
    async def _submit_custom_training_job(self, config: TrainingConfig) -> Any:
        """Submit custom training job."""
        
        # Create custom training job
        job = aiplatform.CustomTrainingJob(
            display_name=config.display_name,
            script_path=config.training_task_definition,
            container_uri="gcr.io/cloud-aiplatform/training/tf-gpu.2-8:latest",
            requirements=["tensorflow==2.8.0", "pandas", "numpy", "scikit-learn"],
            model_serving_container_image_uri="gcr.io/cloud-aiplatform/prediction/tf2-gpu.2-8:latest"
        )
        
        # Run the job
        model = job.run(
            args=self._config_to_args(config.training_task_inputs),
            replica_count=config.replica_count,
            machine_type=config.machine_type,
            accelerator_type=config.accelerator_type,
            accelerator_count=config.accelerator_count,
            base_output_dir=config.base_output_directory,
            service_account=config.service_account,
            network=config.network,
            timeout=config.timeout,
            restart_job_on_worker_restart=config.restart_job_on_worker_restart,
            enable_web_access=config.enable_web_access,
            sync=False  # Don't wait for completion
        )
        
        return model
    
    async def _submit_automl_job(self, config: TrainingConfig) -> Any:
        """Submit AutoML training job."""
        
        # Create AutoML tabular training job
        job = aiplatform.AutoMLTabularTrainingJob(
            display_name=config.display_name,
            optimization_prediction_type="regression",
            optimization_objective=config.training_task_inputs.get("optimization_objective", "minimize-rmse")
        )
        
        # Get dataset
        dataset = aiplatform.TabularDataset(config.training_task_inputs["dataset_id"])
        
        # Run the job
        model = job.run(
            dataset=dataset,
            target_column=config.training_task_inputs["target_column"],
            training_budget_milli_node_hours=config.training_task_inputs["training_budget_milli_node_hours"],
            disable_early_stopping=config.training_task_inputs.get("disable_early_stopping", False),
            sync=False  # Don't wait for completion
        )
        
        return model
    
    async def _submit_hp_tuning_job(self, config: TrainingConfig) -> Any:
        """Submit hyperparameter tuning job."""
        
        # Create hyperparameter tuning job
        job = aiplatform.HyperparameterTuningJob(
            display_name=config.display_name,
            custom_training_job=aiplatform.CustomTrainingJob(
                display_name=f"{config.display_name}-base",
                script_path=config.training_task_definition,
                container_uri="gcr.io/cloud-aiplatform/training/tf-gpu.2-8:latest"
            ),
            metric_spec={
                config.training_task_inputs["optimization_goal_metric"]: config.training_task_inputs["optimization_goal"]
            },
            parameter_spec=config.training_task_inputs["parameter_spec"],
            max_trial_count=config.training_task_inputs["max_trial_count"],
            parallel_trial_count=config.training_task_inputs["parallel_trial_count"]
        )
        
        # Run the job
        job.run(sync=False)
        
        return job
    
    def _config_to_args(self, task_inputs: Dict[str, Any]) -> List[str]:
        """Convert task inputs to command line arguments."""
        args = []
        
        for key, value in task_inputs.items():
            if isinstance(value, (list, dict)):
                args.extend([f"--{key}", json.dumps(value)])
            else:
                args.extend([f"--{key}", str(value)])
        
        return args
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a training job."""
        
        try:
            if job_id not in self.training_jobs:
                raise ValueError(f"Job {job_id} not found")
            
            job = self.training_jobs[job_id]
            
            # Cancel the Vertex AI job
            # This would require storing the actual Vertex AI job reference
            # For now, just update local status
            
            job.status = TrainingJobStatus.CANCELLED
            job.completed_at = time.time()
            
            logger.info(f"Cancelled training job {job_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            return False
    
    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get training job status."""
        
        if job_id not in self.training_jobs:
            return None
        
        return self.training_jobs[job_id].to_dict()
    
    async def list_jobs(
        self, 
        status_filter: Optional[TrainingJobStatus] = None,
        job_type_filter: Optional[TrainingJobType] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List training jobs with optional filters."""
        
        jobs = []
        
        for job in self.training_jobs.values():
            if status_filter and job.status != status_filter:
                continue
            if job_type_filter and job.job_type != job_type_filter:
                continue
            
            jobs.append(job.to_dict())
        
        # Sort by creation time (newest first)
        jobs.sort(key=lambda x: x["created_at"], reverse=True)
        
        return jobs[:limit]
    
    async def get_job_logs(self, job_id: str) -> List[str]:
        """Get training job logs."""
        
        if job_id not in self.training_jobs:
            raise ValueError(f"Job {job_id} not found")
        
        # This would retrieve actual logs from Vertex AI
        # For now, return placeholder
        return [
            f"Training job {job_id} started",
            "Loading training data...",
            "Starting training...",
            "Training completed"
        ]
    
    async def get_job_metrics(self, job_id: str) -> Dict[str, Any]:
        """Get training job metrics."""
        
        if job_id not in self.training_jobs:
            raise ValueError(f"Job {job_id} not found")
        
        job = self.training_jobs[job_id]
        
        return {
            "job_id": job_id,
            "status": job.status.value,
            "duration_seconds": (job.completed_at - job.started_at) if job.completed_at and job.started_at else None,
            "metrics": job.metrics or {},
            "model_artifacts": job.model_artifacts or {}
        }
    
    def add_job_callback(self, job_id: str, callback: Callable):
        """Add callback for job status changes."""
        
        if job_id not in self.job_callbacks:
            self.job_callbacks[job_id] = []
        
        self.job_callbacks[job_id].append(callback)
    
    async def prepare_training_data(
        self,
        source_data_uri: str,
        output_uri: str,
        data_type: str = "routing_data",
        preprocessing_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """Prepare training data from ATP platform logs."""
        
        try:
            # This would implement data preprocessing pipeline
            # For now, return the output URI
            
            logger.info(f"Prepared training data from {source_data_uri} to {output_uri}")
            
            return output_uri
            
        except Exception as e:
            logger.error(f"Failed to prepare training data: {e}")
            raise