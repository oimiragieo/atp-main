"""
Tests for Advanced Loop Detection and Abuse Prevention System
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'router_service'))

from abuse_prevention import (
    AbusePreventionSystem, LoopDetector, RateLimiter, AnomalyDetector,
    CircuitBreaker, RequestSignature, RequestContext, BlockReason, ThreatLevel,
    check_request_abuse, end_request_tracking, get_abuse_statistics
)


class TestCircuitBreak