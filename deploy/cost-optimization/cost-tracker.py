#!/usr/bin/env python3
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
Advanced Cost Tracking and FinOps Automation System

This module provides comprehensive cost tracking, forecasting, and optimization
recommendations across multi-cloud environments.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
import boto3
from google.cloud import billing_v1, monitoring_v3
from azure.identity import DefaultAzureCredential
from azure.mgmt.consumption import ConsumptionManagementClient
from azure.mgmt.costmanagement import CostManagementClient
import prometheus_client
from prometheus_client import Gauge, Counter, Histogram

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CloudProvider(Enum):
    """Supported cloud providers"""
    GCP = "gcp"
    AWS = "aws"
    AZURE = "azure"

class CostCategory(Enum):
    """Cost categories for attribution"""
    COMPUTE = "compute"
    STORAGE = "storage"
    NETWORK = "network"
    DATABASE = "database"
    AI_ML = "ai_ml"
    MONITORING = "monitoring"
    SECURITY = "security"
    OTHER = "other"

@dataclass
class CostData:
    """Cost data structure"""
    provider: CloudProvider
    service: str
    category: CostCategory
    tenant_id: str
    project_id: str
    cost: float
    currency: str
    timestamp: datetime
    resource_id: str
    tags: Dict[str, str]

@dataclass
class CostForecast:
    """Cost forecast structure"""
    provider: CloudProvider
    category: CostCategory
    tenant_id: str
    project_id: str
    forecasted_cost: float
    confidence_interval: tuple
    forecast_period: str
    model_accuracy: float
    timestamp: datetime

@dataclass
class CostAnomaly:
    """Cost anomaly detection result"""
    provider: CloudProvider
    service: str
    tenant_id: str
    project_id: str
    expected_cost: float
    actual_cost: float
    anomaly_score: float
    severity: str
    timestamp: datetime
    description: str

@dataclass
class OptimizationRecommendation:
    """Cost optimization recommendation"""
    provider: CloudProvider
    resource_type: str
    resource_id: str
    tenant_id: str
    project_id: str
    current_cost: float
    potential_savings: float
    recommendation: str
    confidence: float
    implementation_effort: str
    timestamp: datetime

class PrometheusMetrics:
    """Prometheus metrics for cost tracking"""
    
    def __init__(self):
        self.cost_gauge = Gauge(
            'atp_cost_current',
            'Current cost by provider, service, tenant, and project',
            ['provider', 'service', 'category', 'tenant_id', 'project_id']
        )
        
        self.cost_forecast_gauge = Gauge(
            'atp_cost_forecast',
            'Forecasted cost by provider, category, tenant, and project',
            ['provider', 'category', 'tenant_id', 'project_id', 'period']
        )
        
        self.anomaly_counter = Counter(
            'atp_cost_anomalies_total',
            'Total number of cost anomalies detected',
            ['provider', 'service', 'tenant_id', 'project_id', 'severity']
        )
        
        self.savings_gauge = Gauge(
            'atp_potential_savings',
            'Potential cost savings from optimization recommendations',
            ['provider', 'resource_type', 'tenant_id', 'project_id']
        )

class GCPCostCollector:
    """Google Cloud Platform cost data collector"""
    
    def __init__(self, project_id: str, billing_account_id: str):
        self.project_id = project_id
        self.billing_account_id = billing_account_id
        self.billing_client = billing_v1.CloudBillingClient()
        self.monitoring_client = monitoring_v3.MetricServiceClient()
    
    async def collect_cost_data(self, start_date: datetime, end_date: datetime) -> List[CostData]:
        """Collect cost data from GCP"""
        try:
            # Query billing data
            request = billing_v1.ListProjectBillingInfoRequest(
                name=f"billingAccounts/{self.billing_account_id}"
            )
            
            cost_data = []
            # Implementation would query actual GCP billing API
            # This is a simplified example
            
            logger.info(f"Collected {len(cost_data)} cost records from GCP")
            return cost_data
            
        except Exception as e:
            logger.error(f"Error collecting GCP cost data: {e}")
            return []

class AWSCostCollector:
    """Amazon Web Services cost data collector"""
    
    def __init__(self, region: str = 'us-east-1'):
        self.ce_client = boto3.client('ce', region_name=region)
        self.cloudwatch = boto3.client('cloudwatch', region_name=region)
    
    async def collect_cost_data(self, start_date: datetime, end_date: datetime) -> List[CostData]:
        """Collect cost data from AWS"""
        try:
            response = self.ce_client.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='DAILY',
                Metrics=['BlendedCost'],
                GroupBy=[
                    {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                    {'Type': 'TAG', 'Key': 'tenant_id'},
                    {'Type': 'TAG', 'Key': 'project_id'}
                ]
            )
            
            cost_data = []
            for result in response['ResultsByTime']:
                for group in result['Groups']:
                    service = group['Keys'][0]
                    tenant_id = group['Keys'][1] if len(group['Keys']) > 1 else 'unknown'
                    project_id = group['Keys'][2] if len(group['Keys']) > 2 else 'unknown'
                    
                    cost = float(group['Metrics']['BlendedCost']['Amount'])
                    
                    cost_data.append(CostData(
                        provider=CloudProvider.AWS,
                        service=service,
                        category=self._categorize_service(service),
                        tenant_id=tenant_id,
                        project_id=project_id,
                        cost=cost,
                        currency=group['Metrics']['BlendedCost']['Unit'],
                        timestamp=datetime.strptime(result['TimePeriod']['Start'], '%Y-%m-%d'),
                        resource_id='',
                        tags={}
                    ))
            
            logger.info(f"Collected {len(cost_data)} cost records from AWS")
            return cost_data
            
        except Exception as e:
            logger.error(f"Error collecting AWS cost data: {e}")
            return []
    
    def _categorize_service(self, service: str) -> CostCategory:
        """Categorize AWS service into cost category"""
        service_lower = service.lower()
        
        if any(keyword in service_lower for keyword in ['ec2', 'lambda', 'fargate', 'batch']):
            return CostCategory.COMPUTE
        elif any(keyword in service_lower for keyword in ['s3', 'ebs', 'efs']):
            return CostCategory.STORAGE
        elif any(keyword in service_lower for keyword in ['rds', 'dynamodb', 'redshift']):
            return CostCategory.DATABASE
        elif any(keyword in service_lower for keyword in ['sagemaker', 'comprehend', 'rekognition']):
            return CostCategory.AI_ML
        elif any(keyword in service_lower for keyword in ['cloudwatch', 'x-ray']):
            return CostCategory.MONITORING
        elif any(keyword in service_lower for keyword in ['vpc', 'cloudfront', 'route53']):
            return CostCategory.NETWORK
        else:
            return CostCategory.OTHER

class AzureCostCollector:
    """Microsoft Azure cost data collector"""
    
    def __init__(self, subscription_id: str):
        self.subscription_id = subscription_id
        self.credential = DefaultAzureCredential()
        self.consumption_client = ConsumptionManagementClient(
            self.credential, subscription_id
        )
        self.cost_client = CostManagementClient(self.credential)
    
    async def collect_cost_data(self, start_date: datetime, end_date: datetime) -> List[CostData]:
        """Collect cost data from Azure"""
        try:
            # Query Azure consumption API
            cost_data = []
            # Implementation would query actual Azure billing API
            # This is a simplified example
            
            logger.info(f"Collected {len(cost_data)} cost records from Azure")
            return cost_data
            
        except Exception as e:
            logger.error(f"Error collecting Azure cost data: {e}")
            return []

class CostForecaster:
    """Machine learning-based cost forecasting"""
    
    def __init__(self):
        self.models = {}
        self.model_accuracy = {}
    
    def train_forecast_model(self, historical_data: List[CostData], 
                           provider: CloudProvider, category: CostCategory) -> None:
        """Train forecasting model for specific provider and category"""
        try:
            # Filter data for specific provider and category
            filtered_data = [
                d for d in historical_data 
                if d.provider == provider and d.category == category
            ]
            
            if len(filtered_data) < 30:  # Need at least 30 days of data
                logger.warning(f"Insufficient data for {provider.value}/{category.value} forecasting")
                return
            
            # Prepare data for training
            df = pd.DataFrame([asdict(d) for d in filtered_data])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            
            # Feature engineering
            df['day_of_week'] = df['timestamp'].dt.dayofweek
            df['day_of_month'] = df['timestamp'].dt.day
            df['month'] = df['timestamp'].dt.month
            df['days_since_start'] = (df['timestamp'] - df['timestamp'].min()).dt.days
            
            # Prepare features and target
            features = ['day_of_week', 'day_of_month', 'month', 'days_since_start']
            X = df[features]
            y = df['cost']
            
            # Train multiple models and select best
            models = {
                'linear': LinearRegression(),
                'random_forest': RandomForestRegressor(n_estimators=100, random_state=42)
            }
            
            best_model = None
            best_score = -float('inf')
            
            for name, model in models.items():
                model.fit(X, y)
                score = model.score(X, y)
                
                if score > best_score:
                    best_score = score
                    best_model = model
            
            # Store model and accuracy
            model_key = f"{provider.value}_{category.value}"
            self.models[model_key] = best_model
            self.model_accuracy[model_key] = best_score
            
            logger.info(f"Trained forecast model for {model_key} with accuracy: {best_score:.3f}")
            
        except Exception as e:
            logger.error(f"Error training forecast model: {e}")
    
    def generate_forecast(self, provider: CloudProvider, category: CostCategory,
                         tenant_id: str, project_id: str, days_ahead: int = 30) -> Optional[CostForecast]:
        """Generate cost forecast"""
        try:
            model_key = f"{provider.value}_{category.value}"
            
            if model_key not in self.models:
                logger.warning(f"No trained model for {model_key}")
                return None
            
            model = self.models[model_key]
            accuracy = self.model_accuracy[model_key]
            
            # Generate future dates
            future_dates = pd.date_range(
                start=datetime.now(),
                periods=days_ahead,
                freq='D'
            )
            
            # Prepare features for prediction
            future_features = []
            for date in future_dates:
                features = [
                    date.dayofweek,
                    date.day,
                    date.month,
                    (date - datetime.now()).days
                ]
                future_features.append(features)
            
            # Make predictions
            predictions = model.predict(future_features)
            total_forecast = float(np.sum(predictions))
            
            # Calculate confidence interval (simplified)
            std_error = np.std(predictions)
            confidence_interval = (
                total_forecast - 1.96 * std_error,
                total_forecast + 1.96 * std_error
            )
            
            return CostForecast(
                provider=provider,
                category=category,
                tenant_id=tenant_id,
                project_id=project_id,
                forecasted_cost=total_forecast,
                confidence_interval=confidence_interval,
                forecast_period=f"{days_ahead}_days",
                model_accuracy=accuracy,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error generating forecast: {e}")
            return None

class CostAnomalyDetector:
    """Statistical anomaly detection for cost data"""
    
    def __init__(self, sensitivity: float = 2.0):
        self.sensitivity = sensitivity
        self.baselines = {}
    
    def update_baseline(self, cost_data: List[CostData]) -> None:
        """Update baseline statistics for anomaly detection"""
        try:
            # Group by provider, service, tenant, project
            grouped_data = {}
            
            for data in cost_data:
                key = f"{data.provider.value}_{data.service}_{data.tenant_id}_{data.project_id}"
                
                if key not in grouped_data:
                    grouped_data[key] = []
                
                grouped_data[key].append(data.cost)
            
            # Calculate baseline statistics
            for key, costs in grouped_data.items():
                if len(costs) >= 7:  # Need at least a week of data
                    self.baselines[key] = {
                        'mean': np.mean(costs),
                        'std': np.std(costs),
                        'median': np.median(costs),
                        'q75': np.percentile(costs, 75),
                        'q95': np.percentile(costs, 95)
                    }
            
            logger.info(f"Updated baselines for {len(self.baselines)} cost groups")
            
        except Exception as e:
            logger.error(f"Error updating baselines: {e}")
    
    def detect_anomalies(self, current_data: List[CostData]) -> List[CostAnomaly]:
        """Detect cost anomalies"""
        anomalies = []
        
        try:
            for data in current_data:
                key = f"{data.provider.value}_{data.service}_{data.tenant_id}_{data.project_id}"
                
                if key not in self.baselines:
                    continue
                
                baseline = self.baselines[key]
                
                # Z-score based anomaly detection
                z_score = abs(data.cost - baseline['mean']) / baseline['std']
                
                if z_score > self.sensitivity:
                    # Determine severity
                    if data.cost > baseline['q95']:
                        severity = 'critical'
                    elif data.cost > baseline['q75']:
                        severity = 'warning'
                    else:
                        severity = 'info'
                    
                    anomaly = CostAnomaly(
                        provider=data.provider,
                        service=data.service,
                        tenant_id=data.tenant_id,
                        project_id=data.project_id,
                        expected_cost=baseline['mean'],
                        actual_cost=data.cost,
                        anomaly_score=z_score,
                        severity=severity,
                        timestamp=data.timestamp,
                        description=f"Cost anomaly detected: {data.cost:.2f} vs expected {baseline['mean']:.2f}"
                    )
                    
                    anomalies.append(anomaly)
            
            logger.info(f"Detected {len(anomalies)} cost anomalies")
            return anomalies
            
        except Exception as e:
            logger.error(f"Error detecting anomalies: {e}")
            return []

class CostOptimizer:
    """Cost optimization recommendation engine"""
    
    def __init__(self):
        self.optimization_rules = self._load_optimization_rules()
    
    def _load_optimization_rules(self) -> Dict[str, Any]:
        """Load optimization rules configuration"""
        return {
            'compute': {
                'idle_threshold': 0.05,  # 5% CPU utilization
                'rightsizing_threshold': 0.8,  # 80% utilization
                'spot_instance_savings': 0.7  # 70% savings with spot instances
            },
            'storage': {
                'unused_threshold': 30,  # days without access
                'lifecycle_savings': 0.5  # 50% savings with lifecycle policies
            },
            'database': {
                'idle_connection_threshold': 0.1,  # 10% connection utilization
                'reserved_instance_savings': 0.3  # 30% savings with reserved instances
            }
        }
    
    async def generate_recommendations(self, cost_data: List[CostData],
                                     utilization_data: Dict[str, float]) -> List[OptimizationRecommendation]:
        """Generate cost optimization recommendations"""
        recommendations = []
        
        try:
            # Group cost data by resource
            resource_costs = {}
            for data in cost_data:
                if data.resource_id not in resource_costs:
                    resource_costs[data.resource_id] = []
                resource_costs[data.resource_id].append(data)
            
            # Analyze each resource
            for resource_id, costs in resource_costs.items():
                if not costs:
                    continue
                
                latest_cost = costs[-1]
                avg_cost = sum(c.cost for c in costs) / len(costs)
                
                # Get utilization data
                utilization = utilization_data.get(resource_id, 1.0)
                
                # Generate recommendations based on category
                if latest_cost.category == CostCategory.COMPUTE:
                    rec = self._analyze_compute_optimization(
                        latest_cost, avg_cost, utilization
                    )
                elif latest_cost.category == CostCategory.STORAGE:
                    rec = self._analyze_storage_optimization(
                        latest_cost, avg_cost, utilization
                    )
                elif latest_cost.category == CostCategory.DATABASE:
                    rec = self._analyze_database_optimization(
                        latest_cost, avg_cost, utilization
                    )
                
                if rec:
                    recommendations.append(rec)
            
            logger.info(f"Generated {len(recommendations)} optimization recommendations")
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            return []
    
    def _analyze_compute_optimization(self, cost_data: CostData, avg_cost: float,
                                    utilization: float) -> Optional[OptimizationRecommendation]:
        """Analyze compute resource optimization"""
        rules = self.optimization_rules['compute']
        
        if utilization < rules['idle_threshold']:
            return OptimizationRecommendation(
                provider=cost_data.provider,
                resource_type='compute',
                resource_id=cost_data.resource_id,
                tenant_id=cost_data.tenant_id,
                project_id=cost_data.project_id,
                current_cost=avg_cost,
                potential_savings=avg_cost * 0.9,  # 90% savings by terminating
                recommendation="Consider terminating idle compute resource",
                confidence=0.9,
                implementation_effort="low",
                timestamp=datetime.now()
            )
        elif utilization > rules['rightsizing_threshold']:
            return OptimizationRecommendation(
                provider=cost_data.provider,
                resource_type='compute',
                resource_id=cost_data.resource_id,
                tenant_id=cost_data.tenant_id,
                project_id=cost_data.project_id,
                current_cost=avg_cost,
                potential_savings=avg_cost * 0.3,  # 30% savings by rightsizing
                recommendation="Consider upgrading to larger instance size",
                confidence=0.7,
                implementation_effort="medium",
                timestamp=datetime.now()
            )
        
        return None
    
    def _analyze_storage_optimization(self, cost_data: CostData, avg_cost: float,
                                    utilization: float) -> Optional[OptimizationRecommendation]:
        """Analyze storage optimization"""
        rules = self.optimization_rules['storage']
        
        if utilization < 0.1:  # Low access pattern
            return OptimizationRecommendation(
                provider=cost_data.provider,
                resource_type='storage',
                resource_id=cost_data.resource_id,
                tenant_id=cost_data.tenant_id,
                project_id=cost_data.project_id,
                current_cost=avg_cost,
                potential_savings=avg_cost * rules['lifecycle_savings'],
                recommendation="Implement lifecycle policy to move to cheaper storage tier",
                confidence=0.8,
                implementation_effort="low",
                timestamp=datetime.now()
            )
        
        return None
    
    def _analyze_database_optimization(self, cost_data: CostData, avg_cost: float,
                                     utilization: float) -> Optional[OptimizationRecommendation]:
        """Analyze database optimization"""
        rules = self.optimization_rules['database']
        
        if utilization < rules['idle_connection_threshold']:
            return OptimizationRecommendation(
                provider=cost_data.provider,
                resource_type='database',
                resource_id=cost_data.resource_id,
                tenant_id=cost_data.tenant_id,
                project_id=cost_data.project_id,
                current_cost=avg_cost,
                potential_savings=avg_cost * rules['reserved_instance_savings'],
                recommendation="Consider reserved instances or connection pooling",
                confidence=0.7,
                implementation_effort="medium",
                timestamp=datetime.now()
            )
        
        return None

class CostTrackingSystem:
    """Main cost tracking and FinOps automation system"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.metrics = PrometheusMetrics()
        
        # Initialize collectors
        self.collectors = {}
        if 'gcp' in config:
            self.collectors[CloudProvider.GCP] = GCPCostCollector(
                config['gcp']['project_id'],
                config['gcp']['billing_account_id']
            )
        
        if 'aws' in config:
            self.collectors[CloudProvider.AWS] = AWSCostCollector(
                config['aws'].get('region', 'us-east-1')
            )
        
        if 'azure' in config:
            self.collectors[CloudProvider.AZURE] = AzureCostCollector(
                config['azure']['subscription_id']
            )
        
        # Initialize components
        self.forecaster = CostForecaster()
        self.anomaly_detector = CostAnomalyDetector()
        self.optimizer = CostOptimizer()
        
        # Storage for historical data
        self.historical_data = []
    
    async def collect_all_cost_data(self) -> List[CostData]:
        """Collect cost data from all configured providers"""
        all_cost_data = []
        end_date = datetime.now()
        start_date = end_date - timedelta(days=1)  # Last 24 hours
        
        tasks = []
        for provider, collector in self.collectors.items():
            task = collector.collect_cost_data(start_date, end_date)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                all_cost_data.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Error collecting cost data: {result}")
        
        return all_cost_data
    
    async def run_cost_analysis(self) -> None:
        """Run comprehensive cost analysis"""
        try:
            logger.info("Starting cost analysis cycle")
            
            # Collect current cost data
            current_data = await self.collect_all_cost_data()
            
            if not current_data:
                logger.warning("No cost data collected")
                return
            
            # Update historical data
            self.historical_data.extend(current_data)
            
            # Keep only last 90 days of data
            cutoff_date = datetime.now() - timedelta(days=90)
            self.historical_data = [
                d for d in self.historical_data 
                if d.timestamp >= cutoff_date
            ]
            
            # Update Prometheus metrics
            self._update_cost_metrics(current_data)
            
            # Train forecasting models
            await self._train_forecasting_models()
            
            # Generate forecasts
            forecasts = await self._generate_forecasts()
            self._update_forecast_metrics(forecasts)
            
            # Detect anomalies
            self.anomaly_detector.update_baseline(self.historical_data)
            anomalies = self.anomaly_detector.detect_anomalies(current_data)
            self._update_anomaly_metrics(anomalies)
            
            # Generate optimization recommendations
            utilization_data = await self._collect_utilization_data()
            recommendations = await self.optimizer.generate_recommendations(
                current_data, utilization_data
            )
            self._update_optimization_metrics(recommendations)
            
            # Send alerts if needed
            await self._send_alerts(anomalies, recommendations)
            
            logger.info("Cost analysis cycle completed")
            
        except Exception as e:
            logger.error(f"Error in cost analysis: {e}")
    
    def _update_cost_metrics(self, cost_data: List[CostData]) -> None:
        """Update Prometheus cost metrics"""
        for data in cost_data:
            self.metrics.cost_gauge.labels(
                provider=data.provider.value,
                service=data.service,
                category=data.category.value,
                tenant_id=data.tenant_id,
                project_id=data.project_id
            ).set(data.cost)
    
    def _update_forecast_metrics(self, forecasts: List[CostForecast]) -> None:
        """Update Prometheus forecast metrics"""
        for forecast in forecasts:
            self.metrics.cost_forecast_gauge.labels(
                provider=forecast.provider.value,
                category=forecast.category.value,
                tenant_id=forecast.tenant_id,
                project_id=forecast.project_id,
                period=forecast.forecast_period
            ).set(forecast.forecasted_cost)
    
    def _update_anomaly_metrics(self, anomalies: List[CostAnomaly]) -> None:
        """Update Prometheus anomaly metrics"""
        for anomaly in anomalies:
            self.metrics.anomaly_counter.labels(
                provider=anomaly.provider.value,
                service=anomaly.service,
                tenant_id=anomaly.tenant_id,
                project_id=anomaly.project_id,
                severity=anomaly.severity
            ).inc()
    
    def _update_optimization_metrics(self, recommendations: List[OptimizationRecommendation]) -> None:
        """Update Prometheus optimization metrics"""
        for rec in recommendations:
            self.metrics.savings_gauge.labels(
                provider=rec.provider.value,
                resource_type=rec.resource_type,
                tenant_id=rec.tenant_id,
                project_id=rec.project_id
            ).set(rec.potential_savings)
    
    async def _train_forecasting_models(self) -> None:
        """Train forecasting models for all provider/category combinations"""
        if len(self.historical_data) < 30:
            logger.warning("Insufficient historical data for forecasting")
            return
        
        # Get unique combinations
        combinations = set()
        for data in self.historical_data:
            combinations.add((data.provider, data.category))
        
        # Train models for each combination
        for provider, category in combinations:
            self.forecaster.train_forecast_model(
                self.historical_data, provider, category
            )
    
    async def _generate_forecasts(self) -> List[CostForecast]:
        """Generate cost forecasts"""
        forecasts = []
        
        # Get unique tenant/project combinations
        combinations = set()
        for data in self.historical_data:
            combinations.add((data.provider, data.category, data.tenant_id, data.project_id))
        
        # Generate forecasts for each combination
        for provider, category, tenant_id, project_id in combinations:
            forecast = self.forecaster.generate_forecast(
                provider, category, tenant_id, project_id
            )
            if forecast:
                forecasts.append(forecast)
        
        return forecasts
    
    async def _collect_utilization_data(self) -> Dict[str, float]:
        """Collect resource utilization data"""
        # This would integrate with monitoring systems to get actual utilization
        # For now, return mock data
        return {}
    
    async def _send_alerts(self, anomalies: List[CostAnomaly], 
                          recommendations: List[OptimizationRecommendation]) -> None:
        """Send alerts for anomalies and high-value recommendations"""
        # Critical anomalies
        critical_anomalies = [a for a in anomalies if a.severity == 'critical']
        
        # High-value recommendations (>$1000 potential savings)
        high_value_recs = [r for r in recommendations if r.potential_savings > 1000]
        
        if critical_anomalies or high_value_recs:
            logger.info(f"Sending alerts for {len(critical_anomalies)} anomalies and {len(high_value_recs)} recommendations")
            # Implementation would send actual alerts via email, Slack, etc.

async def main():
    """Main function to run the cost tracking system"""
    config = {
        'gcp': {
            'project_id': 'your-gcp-project',
            'billing_account_id': 'your-billing-account'
        },
        'aws': {
            'region': 'us-west-2'
        },
        'azure': {
            'subscription_id': 'your-subscription-id'
        }
    }
    
    # Start Prometheus metrics server
    prometheus_client.start_http_server(8000)
    
    # Initialize cost tracking system
    cost_tracker = CostTrackingSystem(config)
    
    # Run analysis every hour
    while True:
        await cost_tracker.run_cost_analysis()
        await asyncio.sleep(3600)  # 1 hour

if __name__ == "__main__":
    asyncio.run(main())