"""Advanced analytics and insights system for enterprise AI platform."""

from .analytics_config import AnalyticsConfig
from .analytics_manager import AnalyticsManager, get_analytics_manager
from .anomaly_detector import AnomalyDetector
from .business_intelligence import BusinessIntelligenceEngine
from .insights_generator import InsightsGenerator
from .performance_analyzer import PerformanceAnalyzer
from .request_analyzer import RequestAnalyzer
from .trend_analyzer import TrendAnalyzer

__all__ = [
    "AnalyticsManager",
    "get_analytics_manager",
    "AnalyticsConfig",
    "RequestAnalyzer",
    "PerformanceAnalyzer",
    "BusinessIntelligenceEngine",
    "AnomalyDetector",
    "TrendAnalyzer",
    "InsightsGenerator",
]
