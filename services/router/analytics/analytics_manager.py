"""Main analytics manager for enterprise AI platform."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .analytics_config import AnalyticsConfig
from .request_analyzer import RequestAnalyzer
from .performance_analyzer import PerformanceAnalyzer
from .business_intelligence import BusinessIntelligenceEngine
from .anomaly_detector import AnomalyDetector
from .trend_analyzer import TrendAnalyzer
from .insights_generator import InsightsGenerator

logger = logging.getLogger(__name__)


class AnalyticsManager:
    """Main manager for all analytics and intelligence operations."""
    
    def __init__(self, config: Optional[AnalyticsConfig] = None):
        self.config = config or AnalyticsConfig.from_environment()
        
        # Initialize analytics components
        self.request_analyzer = RequestAnalyzer(self.config) if self.config.request_analytics_enabled else None
        self.performance_analyzer = PerformanceAnalyzer(self.config) if self.config.performance_analytics_enabled else None
        self.business_intelligence = BusinessIntelligenceEngine(self.config) if self.config.business_intelligence_enabled else None
        self.anomaly_detector = AnomalyDetector(self.config) if self.config.anomaly_detection_enabled else None
        self.trend_analyzer = TrendAnalyzer(self.config) if self.config.trend_analysis_enabled else None
        self.insights_generator = InsightsGenerator(self.config) if self.config.insights_enabled else None
        
        # Analytics state
        self._last_analysis_time = 0
        self._analysis_results_cache = {}
        self._background_tasks = set()
        
        logger.info("Analytics manager initialized with enabled components: %s", self._get_enabled_components())
    
    def _get_enabled_components(self) -> List[str]:
        """Get list of enabled analytics components."""
        components = []
        if self.request_analyzer:
            components.append("request_analyzer")
        if self.performance_analyzer:
            components.append("performance_analyzer")
        if self.business_intelligence:
            components.append("business_intelligence")
        if self.anomaly_detector:
            components.append("anomaly_detector")
        if self.trend_analyzer:
            components.append("trend_analyzer")
        if self.insights_generator:
            components.append("insights_generator")
        return components
    
    async def run_comprehensive_analysis(
        self,
        request_data: List[Dict[str, Any]],
        performance_data: Optional[List[Dict[str, Any]]] = None,
        cost_data: Optional[List[Dict[str, Any]]] = None,
        time_window_hours: int = 24
    ) -> Dict[str, Any]:
        """Run comprehensive analytics across all enabled components."""
        try:
            analysis_start_time = time.time()
            
            # Validate input data
            if not request_data:
                return {"error": "No request data provided for analysis"}
            
            logger.info(f"Starting comprehensive analysis with {len(request_data)} request records")
            
            # Initialize results structure
            analysis_results = {
                "analysis_timestamp": analysis_start_time,
                "time_window_hours": time_window_hours,
                "data_summary": {
                    "request_records": len(request_data),
                    "performance_records": len(performance_data) if performance_data else 0,
                    "cost_records": len(cost_data) if cost_data else 0
                },
                "enabled_components": self._get_enabled_components(),
                "component_results": {}
            }
            
            # Run analytics components in parallel where possible
            analysis_tasks = []
            
            # Request pattern analysis
            if self.request_analyzer:
                analysis_tasks.append(
                    self._run_request_analysis(request_data, time_window_hours)
                )
            
            # Performance analysis
            if self.performance_analyzer and (performance_data or request_data):
                metrics_data = performance_data or request_data
                analysis_tasks.append(
                    self._run_performance_analysis(metrics_data, time_window_hours)
                )
            
            # Business intelligence analysis
            if self.business_intelligence:
                analysis_tasks.append(
                    self._run_business_intelligence(request_data, cost_data or [], performance_data or [])
                )
            
            # Anomaly detection
            if self.anomaly_detector:
                analysis_tasks.append(
                    self._run_anomaly_detection(request_data)
                )
            
            # Trend analysis
            if self.trend_analyzer:
                analysis_tasks.append(
                    self._run_trend_analysis(request_data)
                )
            
            # Execute all analysis tasks
            if analysis_tasks:
                component_results = await asyncio.gather(*analysis_tasks, return_exceptions=True)
                
                # Process results
                component_names = []
                if self.request_analyzer:
                    component_names.append("request_analysis")
                if self.performance_analyzer:
                    component_names.append("performance_analysis")
                if self.business_intelligence:
                    component_names.append("business_intelligence")
                if self.anomaly_detector:
                    component_names.append("anomaly_detection")
                if self.trend_analyzer:
                    component_names.append("trend_analysis")
                
                for i, result in enumerate(component_results):
                    if i < len(component_names):
                        component_name = component_names[i]
                        if isinstance(result, Exception):
                            logger.error(f"Error in {component_name}: {result}")
                            analysis_results["component_results"][component_name] = {"error": str(result)}
                        else:
                            analysis_results["component_results"][component_name] = result
            
            # Generate comprehensive insights
            if self.insights_generator:
                insights_result = await self._generate_comprehensive_insights(analysis_results["component_results"])
                analysis_results["insights"] = insights_result
            
            # Calculate analysis duration
            analysis_duration = time.time() - analysis_start_time
            analysis_results["analysis_duration_seconds"] = analysis_duration
            
            # Cache results
            self._analysis_results_cache = analysis_results
            self._last_analysis_time = analysis_start_time
            
            logger.info(f"Comprehensive analysis completed in {analysis_duration:.2f} seconds")
            
            return analysis_results
        
        except Exception as e:
            logger.error(f"Error in comprehensive analysis: {e}")
            return {"error": str(e)}
    
    async def _run_request_analysis(self, request_data: List[Dict[str, Any]], time_window_hours: int) -> Dict[str, Any]:
        """Run request pattern analysis."""
        try:
            return await self.request_analyzer.analyze_request_patterns(request_data, time_window_hours)
        except Exception as e:
            logger.error(f"Error in request analysis: {e}")
            return {"error": str(e)}
    
    async def _run_performance_analysis(self, metrics_data: List[Dict[str, Any]], time_window_hours: int) -> Dict[str, Any]:
        """Run performance analysis."""
        try:
            return await self.performance_analyzer.analyze_performance_metrics(metrics_data, time_window_hours)
        except Exception as e:
            logger.error(f"Error in performance analysis: {e}")
            return {"error": str(e)}
    
    async def _run_business_intelligence(
        self,
        request_data: List[Dict[str, Any]],
        cost_data: List[Dict[str, Any]],
        performance_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Run business intelligence analysis."""
        try:
            return await self.business_intelligence.generate_business_insights(
                request_data, cost_data, performance_data
            )
        except Exception as e:
            logger.error(f"Error in business intelligence: {e}")
            return {"error": str(e)}
    
    async def _run_anomaly_detection(self, request_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run anomaly detection."""
        try:
            return await self.anomaly_detector.detect_anomalies(request_data)
        except Exception as e:
            logger.error(f"Error in anomaly detection: {e}")
            return {"error": str(e)}
    
    async def _run_trend_analysis(self, request_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run trend analysis."""
        try:
            return await self.trend_analyzer.analyze_trends(request_data)
        except Exception as e:
            logger.error(f"Error in trend analysis: {e}")
            return {"error": str(e)}
    
    async def _generate_comprehensive_insights(self, component_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive insights from all component results."""
        try:
            analytics_data = component_results.get("request_analysis", {})
            performance_data = component_results.get("performance_analysis", {})
            business_data = component_results.get("business_intelligence", {})
            anomaly_data = component_results.get("anomaly_detection", {})
            trend_data = component_results.get("trend_analysis", {})
            
            return await self.insights_generator.generate_comprehensive_insights(
                analytics_data, performance_data, business_data, anomaly_data, trend_data
            )
        except Exception as e:
            logger.error(f"Error generating insights: {e}")
            return {"error": str(e)}
    
    async def analyze_real_time_metrics(self, current_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze real-time metrics for immediate insights."""
        try:
            real_time_results = {
                "timestamp": time.time(),
                "metrics": current_metrics,
                "alerts": [],
                "recommendations": []
            }
            
            # Real-time anomaly detection
            if self.anomaly_detector:
                anomaly_prediction = await self.anomaly_detector.predict_anomaly_likelihood(current_metrics)
                real_time_results["anomaly_prediction"] = anomaly_prediction
                
                # Generate alert if high anomaly likelihood
                if anomaly_prediction.get("likelihood_percentage", 0) > 80:
                    real_time_results["alerts"].append({
                        "type": "anomaly_alert",
                        "severity": "high",
                        "message": f"High anomaly likelihood detected: {anomaly_prediction.get('likelihood_percentage', 0):.1f}%",
                        "timestamp": time.time()
                    })
            
            # Real-time performance checks
            if current_metrics.get("response_time_ms", 0) > 10000:  # > 10 seconds
                real_time_results["alerts"].append({
                    "type": "performance_alert",
                    "severity": "high",
                    "message": f"High response time detected: {current_metrics.get('response_time_ms', 0)}ms",
                    "timestamp": time.time()
                })
            
            # Real-time error detection
            if current_metrics.get("status_code", 200) >= 500:
                real_time_results["alerts"].append({
                    "type": "error_alert",
                    "severity": "critical",
                    "message": f"Server error detected: {current_metrics.get('status_code', 500)}",
                    "timestamp": time.time()
                })
            
            return real_time_results
        
        except Exception as e:
            logger.error(f"Error in real-time analysis: {e}")
            return {"error": str(e)}
    
    async def get_analytics_dashboard_data(self) -> Dict[str, Any]:
        """Get data for analytics dashboard."""
        try:
            dashboard_data = {
                "timestamp": time.time(),
                "system_status": "operational",
                "components_status": {},
                "key_metrics": {},
                "recent_insights": [],
                "alerts": []
            }
            
            # Component status
            for component_name in self._get_enabled_components():
                dashboard_data["components_status"][component_name] = "active"
            
            # Get cached analysis results
            if self._analysis_results_cache:
                component_results = self._analysis_results_cache.get("component_results", {})
                
                # Extract key metrics
                if "performance_analysis" in component_results:
                    perf_data = component_results["performance_analysis"]
                    latency_stats = perf_data.get("latency_analysis", {}).get("statistics", {})
                    error_stats = perf_data.get("error_analysis", {})
                    
                    dashboard_data["key_metrics"].update({
                        "avg_response_time_ms": latency_stats.get("mean_ms", 0),
                        "p95_response_time_ms": latency_stats.get("p95_ms", 0),
                        "error_rate_percent": error_stats.get("error_rate_percent", 0),
                        "total_requests": error_stats.get("total_requests", 0)
                    })
                
                if "business_intelligence" in component_results:
                    bi_data = component_results["business_intelligence"]
                    cost_analysis = bi_data.get("cost_analysis", {})
                    
                    dashboard_data["key_metrics"].update({
                        "total_cost_usd": cost_analysis.get("total_cost_usd", 0),
                        "avg_cost_per_request": cost_analysis.get("average_cost_per_entry", 0)
                    })
                
                # Get recent insights
                if "insights" in self._analysis_results_cache:
                    insights_data = self._analysis_results_cache["insights"]
                    recent_insights = insights_data.get("insights", [])[:5]  # Top 5 insights
                    dashboard_data["recent_insights"] = recent_insights
                    
                    # Convert high-priority insights to alerts
                    for insight in recent_insights:
                        if insight.get("calculated_priority", 0) > 0.8:
                            dashboard_data["alerts"].append({
                                "type": "insight_alert",
                                "severity": "high" if insight.get("severity", 0) > 0.7 else "medium",
                                "message": insight.get("title", "High-priority insight detected"),
                                "description": insight.get("description", ""),
                                "timestamp": time.time()
                            })
            
            # Get anomaly history
            if self.anomaly_detector:
                recent_anomalies = self.anomaly_detector.get_anomaly_history(hours=1)
                high_severity_anomalies = [a for a in recent_anomalies if a.get("severity_score", 0) > 0.8]
                
                for anomaly in high_severity_anomalies[:3]:  # Top 3 recent anomalies
                    dashboard_data["alerts"].append({
                        "type": "anomaly_alert",
                        "severity": "high",
                        "message": f"Anomaly detected: {anomaly.get('anomaly_type', 'unknown')}",
                        "description": anomaly.get("description", ""),
                        "timestamp": anomaly.get("timestamp", time.time())
                    })
            
            return dashboard_data
        
        except Exception as e:
            logger.error(f"Error getting dashboard data: {e}")
            return {"error": str(e)}
    
    async def export_analytics_data(self, format_type: str = "json", time_range_hours: int = 24) -> Dict[str, Any]:
        """Export analytics data in specified format."""
        try:
            if not self.config.export_enabled:
                return {"error": "Export functionality is disabled"}
            
            if format_type not in self.config.export_formats:
                return {"error": f"Export format '{format_type}' not supported"}
            
            export_data = {
                "export_timestamp": time.time(),
                "format": format_type,
                "time_range_hours": time_range_hours,
                "data": {}
            }
            
            # Include cached analysis results
            if self._analysis_results_cache:
                export_data["data"]["analysis_results"] = self._analysis_results_cache
            
            # Include component-specific data
            if self.anomaly_detector:
                export_data["data"]["anomaly_history"] = self.anomaly_detector.get_anomaly_history(time_range_hours)
            
            if self.insights_generator:
                export_data["data"]["insights_history"] = self.insights_generator.get_insights_history(time_range_hours // 24)
            
            # Add metadata
            export_data["metadata"] = {
                "enabled_components": self._get_enabled_components(),
                "configuration": {
                    "confidence_threshold": self.config.insights_confidence_threshold,
                    "anomaly_sensitivity": self.config.anomaly_sensitivity,
                    "trend_window_days": self.config.trend_window_days
                }
            }
            
            return export_data
        
        except Exception as e:
            logger.error(f"Error exporting analytics data: {e}")
            return {"error": str(e)}
    
    def start_background_analysis(self) -> None:
        """Start background analytics processing."""
        if not self.config.enabled:
            logger.info("Analytics is disabled, skipping background analysis")
            return
        
        # Create background task for periodic analysis
        task = asyncio.create_task(self._background_analysis_loop())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        
        logger.info("Background analytics processing started")
    
    async def _background_analysis_loop(self) -> None:
        """Background loop for periodic analytics processing."""
        while True:
            try:
                await asyncio.sleep(self.config.analysis_interval_minutes * 60)
                
                # Check if we have recent data to analyze
                # In a real implementation, this would fetch data from the database
                logger.debug("Background analysis cycle - would fetch and analyze recent data")
                
                # Placeholder for background analysis
                # This would typically:
                # 1. Fetch recent request/performance data
                # 2. Run incremental analysis
                # 3. Update trends and patterns
                # 4. Generate alerts if needed
                
            except asyncio.CancelledError:
                logger.info("Background analysis loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in background analysis loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    def stop_background_analysis(self) -> None:
        """Stop background analytics processing."""
        for task in self._background_tasks:
            task.cancel()
        self._background_tasks.clear()
        logger.info("Background analytics processing stopped")
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get analytics system status."""
        return {
            "enabled": self.config.enabled,
            "components": {
                "request_analyzer": self.request_analyzer is not None,
                "performance_analyzer": self.performance_analyzer is not None,
                "business_intelligence": self.business_intelligence is not None,
                "anomaly_detector": self.anomaly_detector is not None,
                "trend_analyzer": self.trend_analyzer is not None,
                "insights_generator": self.insights_generator is not None
            },
            "last_analysis_time": self._last_analysis_time,
            "background_tasks_active": len(self._background_tasks),
            "cache_status": "populated" if self._analysis_results_cache else "empty"
        }
    
    def update_configuration(self, new_config: Dict[str, Any]) -> None:
        """Update analytics configuration."""
        try:
            # Update specific configuration values
            if "insights_confidence_threshold" in new_config and self.insights_generator:
                self.insights_generator.update_confidence_threshold(new_config["insights_confidence_threshold"])
            
            if "anomaly_sensitivity" in new_config and self.anomaly_detector:
                self.anomaly_detector.update_sensitivity(new_config["anomaly_sensitivity"])
            
            if "forecast_horizon_days" in new_config and self.trend_analyzer:
                self.trend_analyzer.update_forecast_horizon(new_config["forecast_horizon_days"])
            
            logger.info("Analytics configuration updated")
        
        except Exception as e:
            logger.error(f"Error updating configuration: {e}")


# Global analytics manager instance
_analytics_manager: Optional[AnalyticsManager] = None


def get_analytics_manager() -> AnalyticsManager:
    """Get the global analytics manager instance."""
    global _analytics_manager
    if _analytics_manager is None:
        _analytics_manager = AnalyticsManager()
    return _analytics_manager


def initialize_analytics_manager(config: Optional[AnalyticsConfig] = None) -> AnalyticsManager:
    """Initialize the global analytics manager with custom configuration."""
    global _analytics_manager
    _analytics_manager = AnalyticsManager(config)
    return _analytics_manager