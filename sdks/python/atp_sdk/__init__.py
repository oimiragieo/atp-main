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
ATP Python SDK

A comprehensive Python SDK for the ATP (AI Traffic Platform) with async support,
streaming capabilities, and enterprise features.
"""

from .auth import AuthManager
from .client import AsyncATPClient, ATPClient
from .config import ATPConfig
from .exceptions import (
    ATPError,
    AuthenticationError,
    InsufficientCreditsError,
    ModelNotFoundError,
    RateLimitError,
    ValidationError,
)
from .models import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    CostInfo,
    ModelInfo,
    PolicyInfo,
    ProviderInfo,
    StreamingResponse,
    UsageStats,
)
from .streaming import StreamingClient

__version__ = "1.0.0"
__author__ = "ATP Project Contributors"
__email__ = "support@atp.company.com"

__all__ = [
    # Main clients
    "ATPClient",
    "AsyncATPClient",
    # Models
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "StreamingResponse",
    "ModelInfo",
    "ProviderInfo",
    "CostInfo",
    "UsageStats",
    "PolicyInfo",
    # Exceptions
    "ATPError",
    "AuthenticationError",
    "RateLimitError",
    "ModelNotFoundError",
    "InsufficientCreditsError",
    "ValidationError",
    # Utilities
    "StreamingClient",
    "AuthManager",
    "ATPConfig",
]
