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
Vertex AI A/B Testing Framework

This module provides A/B testing capabilities for Vertex AI models,
including experiment design, traffic splitting, statistical analysis,
and automated decision making.
"""

import asyncio
import json
import logging
import time
import math
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
from scipy import stats

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExperimentStatus(Enum):
    """A/B test experiment status."""
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ExperimentType(Enum):
    """A/B test experiment types."""
    PERFORMANCE = "performance"
    COST = "cost"
    QUALITY = "quality"
    LATENCY = "latency"
    ACCURACY = "accuracy"
    CUSTOM = "custom"


class StatisticalTest(Enum):
    """Statistical test types."""
    T_TEST = "t_test"
    MANN_WHITNEY = "mann_whitney"
    CHI_SQUARE = "chi_square"
    BOOTSTRAP = "bootstrap"


@dataclass
class ExperimentConfig:
    """A/B test experiment configuration."""
    experiment_id: str
    name: str
    description: str
    experiment_type: ExperimentType
    control_model_id: str
    treatment_model_ids: List[str]
    traffic_allocation: Dict[str, float]  # model_id -> percentage
    success_metric: str
    minimum_sample_size: int
    maximum_duration_days: int
    significance_level: float = 0.05
    statistical_power: float = 0.8
    minimum_detectable_effect: float = 0.05
    early_stopping_enabled: bool = True
    early_stopping_threshold: float = 0.01
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["experiment_type"] = self.experiment_type.value
        return result


@dataclass
class ExperimentVariant:
    """A/B test experiment variant."""
    variant_id: str
    model_id: str
    traffic_percentage: float
    sample_count: int = 0
    success_count: int = 0
    total_value: float = 0.0
    metrics: Dict[str, List[float]] = None
    
    def __post_init__(self):
        if self.metrics is None:
            self.metrics = {}
    
    @property
    def success_rate(self) -> float:
        return self.success_count / self.sample_count if self.sample_count > 0 else 0.0
    
    @property
    def average_value(self) -> float:
        return self.total_value / self.sample_count if self.sample_count > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "model_id": self.model_id,
            "traffic_percentage": self.traffic_percentage,
            "sample_count": self.sample_count,
            "success_count": self.success_count,
            "success_rate": self.success_rate,
            "total_value": self.total_value,
            "average_value": self.average_value,
            "metrics": {k: {"count": len(v), "mean": np.mean(v), "std": np.std(v)} 
                       for k, v in self.metrics.items()}
        }


@dataclass
class ExperimentResult:
    """A/B test experiment result."""
    experiment_id: str
    control_variant: ExperimentVariant
    treatment_variants: List[ExperimentVariant]
    statistical_significance: Dict[str, Dict[str, Any]]
    confidence_intervals: Dict[str, Dict[str, Tuple[float, float]]]
    effect_sizes: Dict[str, float]
    recommendations: List[str]
    winner: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "control_variant": self.control_variant.to_dict(),
            "treatment_variants": [v.to_dict() for v in self.treatment_variants],
            "statistical_significance": self.statistical_significance,
            "confidence_intervals": self.confidence_intervals,
            "effect_sizes": self.effect_sizes,
            "recommendations": self.recommendations,
            "winner": self.winner
        }


@dataclass
class Experiment:
    """A/B test experiment."""
    config: ExperimentConfig
    status: ExperimentStatus
    variants: Dict[str, ExperimentVariant]
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[ExperimentResult] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "status": self.status.value,
            "variants": {k: v.to_dict() for k, v in self.variants.items()},
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result.to_dict() if self.result else None
        }


class VertexAIABTesting:
    """Vertex AI A/B testing framework."""
    
    def __init__(self, model_manager, monitoring_system):
        self.model_manager = model_manager
        self.monitoring_system = monitoring_system
        
        # State tracking
        self.experiments: Dict[str, Experiment] = {}
        self.active_experiments: Dict[str, str] = {}  # endpoint_id -> experiment_id
        
        # Monitoring
        self.monitoring_active = False
        self.monitor_task = None
    
    async def start_monitoring(self):
        """Start A/B test monitoring."""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Started A/B testing monitoring")
    
    async def stop_monitoring(self):
        """Stop A/B test monitoring."""
        self.monitoring_active = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped A/B testing monitoring")
    
    async def _monitoring_loop(self):
        """Monitor running experiments."""
        while self.monitoring_active:
            try:
                await self._update_experiment_metrics()
                await self._check_experiment_completion()
                await asyncio.sleep(300)  # Check every 5 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in A/B testing monitoring: {e}")
                await asyncio.sleep(300)
    
    async def _update_experiment_metrics(self):
        """Update metrics for running experiments."""
        for experiment_id, experiment in self.experiments.items():
            if experiment.status == ExperimentStatus.RUNNING:
                try:
                    await self._collect_experiment_metrics(experiment)
                except Exception as e:
                    logger.error(f"Failed to update metrics for experiment {experiment_id}: {e}")
    
    async def _collect_experiment_metrics(self, experiment: Experiment):
        """Collect metrics for an experiment."""
        # Get metrics from monitoring system for each variant
        for variant_id, variant in experiment.variants.items():
            try:
                # Get model metrics from monitoring system
                metrics = await self.monitoring_system.get_model_metrics(
                    variant.model_id, 
                    time_range_hours=1
                )
                
                if metrics:
                    # Update variant metrics based on experiment type
                    if experiment.config.experiment_type == ExperimentType.PERFORMANCE:
                        self._update_performance_metrics(variant, metrics)
                    elif experiment.config.experiment_type == ExperimentType.LATENCY:
                        self._update_latency_metrics(variant, metrics)
                    elif experiment.config.experiment_type == ExperimentType.COST:
                        self._update_cost_metrics(variant, metrics)
                    elif experiment.config.experiment_type == ExperimentType.QUALITY:
                        self._update_quality_metrics(variant, metrics)
                
            except Exception as e:
                logger.error(f"Failed to collect metrics for variant {variant_id}: {e}")
    
    def _update_performance_metrics(self, variant: ExperimentVariant, metrics: List[Dict[str, Any]]):
        """Update performance metrics for a variant."""
        for metric in metrics:
            # Update sample count
            variant.sample_count += metric.get("request_count", 0)
            
            # Update success count (requests without errors)
            error_count = metric.get("error_count", 0)
            success_count = metric.get("request_count", 0) - error_count
            variant.success_count += success_count
            
            # Store detailed metrics
            if "performance" not in variant.metrics:
                variant.metrics["performance"] = []
            
            if metric.get("request_count", 0) > 0:
                performance_score = success_count / metric.get("request_count", 1)
                variant.metrics["performance"].append(performance_score)
    
    def _update_latency_metrics(self, variant: ExperimentVariant, metrics: List[Dict[str, Any]]):
        """Update latency metrics for a variant."""
        for metric in metrics:
            variant.sample_count += metric.get("request_count", 0)
            
            # Store latency values
            if "latency" not in variant.metrics:
                variant.metrics["latency"] = []
            
            latency_p95 = metric.get("latency_p95", 0)
            if latency_p95 > 0:
                variant.metrics["latency"].append(latency_p95)
                variant.total_value += latency_p95
    
    def _update_cost_metrics(self, variant: ExperimentVariant, metrics: List[Dict[str, Any]]):
        """Update cost metrics for a variant."""
        for metric in metrics:
            variant.sample_count += metric.get("request_count", 0)
            
            # Store cost values (would need to be calculated based on usage)
            if "cost" not in variant.metrics:
                variant.metrics["cost"] = []
            
            # Placeholder cost calculation
            estimated_cost = metric.get("request_count", 0) * 0.001  # $0.001 per request
            variant.metrics["cost"].append(estimated_cost)
            variant.total_value += estimated_cost
    
    def _update_quality_metrics(self, variant: ExperimentVariant, metrics: List[Dict[str, Any]]):
        """Update quality metrics for a variant."""
        for metric in metrics:
            variant.sample_count += metric.get("request_count", 0)
            
            # Store quality scores (would need to be provided by quality assessment)
            if "quality" not in variant.metrics:
                variant.metrics["quality"] = []
            
            # Placeholder quality score
            quality_score = metric.get("accuracy_score", 0.8)  # Default quality
            variant.metrics["quality"].append(quality_score)
            variant.total_value += quality_score
    
    async def _check_experiment_completion(self):
        """Check if experiments should be completed."""
        for experiment_id, experiment in self.experiments.items():
            if experiment.status == ExperimentStatus.RUNNING:
                try:
                    should_complete = await self._should_complete_experiment(experiment)
                    if should_complete:
                        await self.complete_experiment(experiment_id)
                except Exception as e:
                    logger.error(f"Failed to check completion for experiment {experiment_id}: {e}")
    
    async def _should_complete_experiment(self, experiment: Experiment) -> bool:
        """Check if an experiment should be completed."""
        
        # Check maximum duration
        if experiment.started_at:
            duration_days = (time.time() - experiment.started_at) / (24 * 3600)
            if duration_days >= experiment.config.maximum_duration_days:
                return True
        
        # Check minimum sample size
        total_samples = sum(variant.sample_count for variant in experiment.variants.values())
        if total_samples < experiment.config.minimum_sample_size:
            return False
        
        # Check early stopping conditions
        if experiment.config.early_stopping_enabled:
            return await self._check_early_stopping(experiment)
        
        return False
    
    async def _check_early_stopping(self, experiment: Experiment) -> bool:
        """Check early stopping conditions."""
        try:
            # Perform statistical analysis
            result = await self._analyze_experiment(experiment)
            
            # Check if any treatment is significantly better
            for treatment_id, significance in result.statistical_significance.items():
                if significance.get("p_value", 1.0) < experiment.config.early_stopping_threshold:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to check early stopping: {e}")
            return False
    
    async def create_experiment(self, config: ExperimentConfig) -> str:
        """Create a new A/B test experiment."""
        
        try:
            # Validate configuration
            await self._validate_experiment_config(config)
            
            # Create variants
            variants = {}
            
            # Control variant
            control_variant = ExperimentVariant(
                variant_id="control",
                model_id=config.control_model_id,
                traffic_percentage=config.traffic_allocation.get(config.control_model_id, 50.0)
            )
            variants["control"] = control_variant
            
            # Treatment variants
            for i, treatment_id in enumerate(config.treatment_model_ids):
                treatment_variant = ExperimentVariant(
                    variant_id=f"treatment_{i+1}",
                    model_id=treatment_id,
                    traffic_percentage=config.traffic_allocation.get(treatment_id, 50.0)
                )
                variants[f"treatment_{i+1}"] = treatment_variant
            
            # Create experiment
            experiment = Experiment(
                config=config,
                status=ExperimentStatus.DRAFT,
                variants=variants,
                created_at=time.time()
            )
            
            self.experiments[config.experiment_id] = experiment
            
            logger.info(f"Created A/B test experiment {config.experiment_id}")
            
            return config.experiment_id
            
        except Exception as e:
            logger.error(f"Failed to create experiment: {e}")
            raise
    
    async def _validate_experiment_config(self, config: ExperimentConfig):
        """Validate experiment configuration."""
        
        # Check traffic allocation sums to 100%
        total_traffic = sum(config.traffic_allocation.values())
        if abs(total_traffic - 100.0) > 0.01:
            raise ValueError(f"Traffic allocation must sum to 100%, got {total_traffic}")
        
        # Check models exist
        all_models = [config.control_model_id] + config.treatment_model_ids
        for model_id in all_models:
            # This would check if model exists in model manager
            pass
        
        # Check minimum sample size is reasonable
        if config.minimum_sample_size < 100:
            raise ValueError("Minimum sample size should be at least 100")
        
        # Check significance level
        if not 0.01 <= config.significance_level <= 0.1:
            raise ValueError("Significance level should be between 0.01 and 0.1")
    
    async def start_experiment(self, experiment_id: str, endpoint_name: str) -> bool:
        """Start an A/B test experiment."""
        
        try:
            if experiment_id not in self.experiments:
                raise ValueError(f"Experiment {experiment_id} not found")
            
            experiment = self.experiments[experiment_id]
            
            if experiment.status != ExperimentStatus.DRAFT:
                raise ValueError(f"Experiment {experiment_id} is not in draft status")
            
            # Set up traffic split
            traffic_split = {
                variant.model_id: variant.traffic_percentage
                for variant in experiment.variants.values()
            }
            
            # Apply traffic split using model manager
            from .model_manager import TrafficSplit, TrafficSplitStrategy
            
            split_config = TrafficSplit(
                strategy=TrafficSplitStrategy.PERCENTAGE,
                splits=traffic_split,
                created_at=time.time(),
                created_by="ab_testing",
                description=f"A/B test experiment {experiment_id}"
            )
            
            success = await self.model_manager.update_traffic_split(endpoint_name, split_config)
            
            if success:
                experiment.status = ExperimentStatus.RUNNING
                experiment.started_at = time.time()
                self.active_experiments[endpoint_name] = experiment_id
                
                logger.info(f"Started A/B test experiment {experiment_id}")
                return True
            else:
                raise Exception("Failed to apply traffic split")
                
        except Exception as e:
            logger.error(f"Failed to start experiment {experiment_id}: {e}")
            return False
    
    async def pause_experiment(self, experiment_id: str) -> bool:
        """Pause an A/B test experiment."""
        
        try:
            if experiment_id not in self.experiments:
                raise ValueError(f"Experiment {experiment_id} not found")
            
            experiment = self.experiments[experiment_id]
            
            if experiment.status != ExperimentStatus.RUNNING:
                raise ValueError(f"Experiment {experiment_id} is not running")
            
            experiment.status = ExperimentStatus.PAUSED
            
            logger.info(f"Paused A/B test experiment {experiment_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to pause experiment {experiment_id}: {e}")
            return False
    
    async def resume_experiment(self, experiment_id: str) -> bool:
        """Resume a paused A/B test experiment."""
        
        try:
            if experiment_id not in self.experiments:
                raise ValueError(f"Experiment {experiment_id} not found")
            
            experiment = self.experiments[experiment_id]
            
            if experiment.status != ExperimentStatus.PAUSED:
                raise ValueError(f"Experiment {experiment_id} is not paused")
            
            experiment.status = ExperimentStatus.RUNNING
            
            logger.info(f"Resumed A/B test experiment {experiment_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to resume experiment {experiment_id}: {e}")
            return False
    
    async def complete_experiment(self, experiment_id: str) -> ExperimentResult:
        """Complete an A/B test experiment and analyze results."""
        
        try:
            if experiment_id not in self.experiments:
                raise ValueError(f"Experiment {experiment_id} not found")
            
            experiment = self.experiments[experiment_id]
            
            if experiment.status not in [ExperimentStatus.RUNNING, ExperimentStatus.PAUSED]:
                raise ValueError(f"Experiment {experiment_id} is not active")
            
            # Analyze results
            result = await self._analyze_experiment(experiment)
            
            # Update experiment
            experiment.status = ExperimentStatus.COMPLETED
            experiment.completed_at = time.time()
            experiment.result = result
            
            # Remove from active experiments
            for endpoint_name, exp_id in list(self.active_experiments.items()):
                if exp_id == experiment_id:
                    del self.active_experiments[endpoint_name]
                    break
            
            logger.info(f"Completed A/B test experiment {experiment_id}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to complete experiment {experiment_id}: {e}")
            raise
    
    async def _analyze_experiment(self, experiment: Experiment) -> ExperimentResult:
        """Analyze experiment results."""
        
        # Get control and treatment variants
        control_variant = experiment.variants["control"]
        treatment_variants = [v for k, v in experiment.variants.items() if k != "control"]
        
        # Perform statistical analysis
        statistical_significance = {}
        confidence_intervals = {}
        effect_sizes = {}
        recommendations = []
        winner = None
        
        metric_name = experiment.config.success_metric
        
        for treatment_variant in treatment_variants:
            # Get metric values
            control_values = control_variant.metrics.get(metric_name, [])
            treatment_values = treatment_variant.metrics.get(metric_name, [])
            
            if len(control_values) == 0 or len(treatment_values) == 0:
                continue
            
            # Perform statistical test
            test_result = self._perform_statistical_test(
                control_values, 
                treatment_values, 
                StatisticalTest.T_TEST
            )
            
            statistical_significance[treatment_variant.variant_id] = test_result
            
            # Calculate confidence interval
            ci = self._calculate_confidence_interval(
                treatment_values, 
                experiment.config.significance_level
            )
            confidence_intervals[treatment_variant.variant_id] = {metric_name: ci}
            
            # Calculate effect size
            effect_size = self._calculate_effect_size(control_values, treatment_values)
            effect_sizes[treatment_variant.variant_id] = effect_size
            
            # Generate recommendations
            if test_result["p_value"] < experiment.config.significance_level:
                if effect_size > 0:
                    recommendations.append(
                        f"Treatment {treatment_variant.variant_id} shows significant improvement "
                        f"(p={test_result['p_value']:.4f}, effect size={effect_size:.3f})"
                    )
                    if winner is None or effect_size > effect_sizes.get(winner, 0):
                        winner = treatment_variant.variant_id
                else:
                    recommendations.append(
                        f"Treatment {treatment_variant.variant_id} shows significant degradation "
                        f"(p={test_result['p_value']:.4f}, effect size={effect_size:.3f})"
                    )
            else:
                recommendations.append(
                    f"Treatment {treatment_variant.variant_id} shows no significant difference "
                    f"(p={test_result['p_value']:.4f})"
                )
        
        # Overall recommendation
        if winner:
            recommendations.append(f"Recommend promoting {winner} to full traffic")
        else:
            recommendations.append("No clear winner found, consider extending experiment or trying different variants")
        
        return ExperimentResult(
            experiment_id=experiment.config.experiment_id,
            control_variant=control_variant,
            treatment_variants=treatment_variants,
            statistical_significance=statistical_significance,
            confidence_intervals=confidence_intervals,
            effect_sizes=effect_sizes,
            recommendations=recommendations,
            winner=winner
        )
    
    def _perform_statistical_test(
        self, 
        control_values: List[float], 
        treatment_values: List[float],
        test_type: StatisticalTest
    ) -> Dict[str, Any]:
        """Perform statistical test."""
        
        try:
            if test_type == StatisticalTest.T_TEST:
                statistic, p_value = stats.ttest_ind(treatment_values, control_values)
                
                return {
                    "test_type": "t_test",
                    "statistic": float(statistic),
                    "p_value": float(p_value),
                    "degrees_of_freedom": len(control_values) + len(treatment_values) - 2
                }
            
            elif test_type == StatisticalTest.MANN_WHITNEY:
                statistic, p_value = stats.mannwhitneyu(treatment_values, control_values)
                
                return {
                    "test_type": "mann_whitney",
                    "statistic": float(statistic),
                    "p_value": float(p_value)
                }
            
            else:
                raise ValueError(f"Unsupported test type: {test_type}")
                
        except Exception as e:
            logger.error(f"Statistical test failed: {e}")
            return {
                "test_type": test_type.value,
                "error": str(e),
                "p_value": 1.0
            }
    
    def _calculate_confidence_interval(
        self, 
        values: List[float], 
        significance_level: float
    ) -> Tuple[float, float]:
        """Calculate confidence interval."""
        
        try:
            confidence_level = 1 - significance_level
            mean = np.mean(values)
            sem = stats.sem(values)
            interval = stats.t.interval(confidence_level, len(values) - 1, loc=mean, scale=sem)
            
            return (float(interval[0]), float(interval[1]))
            
        except Exception as e:
            logger.error(f"Confidence interval calculation failed: {e}")
            return (0.0, 0.0)
    
    def _calculate_effect_size(self, control_values: List[float], treatment_values: List[float]) -> float:
        """Calculate Cohen's d effect size."""
        
        try:
            control_mean = np.mean(control_values)
            treatment_mean = np.mean(treatment_values)
            
            control_std = np.std(control_values, ddof=1)
            treatment_std = np.std(treatment_values, ddof=1)
            
            # Pooled standard deviation
            n1, n2 = len(control_values), len(treatment_values)
            pooled_std = math.sqrt(((n1 - 1) * control_std**2 + (n2 - 1) * treatment_std**2) / (n1 + n2 - 2))
            
            # Cohen's d
            cohens_d = (treatment_mean - control_mean) / pooled_std
            
            return float(cohens_d)
            
        except Exception as e:
            logger.error(f"Effect size calculation failed: {e}")
            return 0.0
    
    async def get_experiment_status(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Get experiment status."""
        
        if experiment_id not in self.experiments:
            return None
        
        return self.experiments[experiment_id].to_dict()
    
    async def list_experiments(
        self, 
        status_filter: Optional[ExperimentStatus] = None
    ) -> List[Dict[str, Any]]:
        """List experiments with optional status filter."""
        
        experiments = []
        
        for experiment in self.experiments.values():
            if status_filter is None or experiment.status == status_filter:
                experiments.append(experiment.to_dict())
        
        # Sort by creation time (newest first)
        experiments.sort(key=lambda x: x["created_at"], reverse=True)
        
        return experiments
    
    async def calculate_sample_size(
        self,
        baseline_rate: float,
        minimum_detectable_effect: float,
        significance_level: float = 0.05,
        statistical_power: float = 0.8
    ) -> int:
        """Calculate required sample size for experiment."""
        
        try:
            # Calculate effect size
            effect_size = minimum_detectable_effect / math.sqrt(baseline_rate * (1 - baseline_rate))
            
            # Calculate sample size using power analysis
            alpha = significance_level
            beta = 1 - statistical_power
            
            z_alpha = stats.norm.ppf(1 - alpha / 2)
            z_beta = stats.norm.ppf(1 - beta)
            
            sample_size = 2 * ((z_alpha + z_beta) / effect_size) ** 2
            
            return int(math.ceil(sample_size))
            
        except Exception as e:
            logger.error(f"Sample size calculation failed: {e}")
            return 1000  # Default fallback