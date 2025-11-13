#!/usr/bin/env python3
"""
Enterprise AI Platform - Base Adapter Interface

Defines the standard interface that all adapters must implement.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, AsyncIterator
from dataclasses import dataclass
from enum import Enum

class AdapterCapability(Enum):
    """Capabilities that an adapter can support."""
    TEXT_GENERATION = "text_generation"
    STREAMING = "streaming"
    FUNCTION_CALLING = "function_calling"
    VISION = "vision"
    EMBEDDINGS = "embeddings"
    FINE_TUNING = "fine_tuning"

@dataclass
class AdapterInfo:
    """Information about an adapter."""
    name: str
    provider: str
    version: str
    capabilities: List[AdapterCapability]
    models: List[str]
    pricing_model: str  # 'per_token', 'per_request', 'per_minute'
    max_tokens: int
    supports_streaming: bool = False
    supports_functions: bool = False

@dataclass
class AdapterRequest:
    """Standard request format for all adapters."""
    prompt: str
    model: str
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stream: bool = False
    functions: Optional[List[Dict]] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class AdapterResponse:
    """Standard response format from all adapters."""
    content: str
    model: str
    usage: Dict[str, int]  # tokens used
    cost: float  # estimated cost in USD
    latency_ms: int
    metadata: Optional[Dict[str, Any]] = None

class BaseAdapter(ABC):
    """Base class that all adapters must inherit from."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = self.__class__.__name__.replace('Adapter', '').lower()
    
    @abstractmethod
    async def get_info(self) -> AdapterInfo:
        """Get information about this adapter."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the adapter is healthy and can handle requests."""
        pass
    
    @abstractmethod
    async def generate(self, request: AdapterRequest) -> AdapterResponse:
        """Generate a response for the given request."""
        pass
    
    @abstractmethod
    async def stream_generate(self, request: AdapterRequest) -> AsyncIterator[str]:
        """Generate a streaming response for the given request."""
        pass
    
    async def estimate_cost(self, request: AdapterRequest) -> float:
        """Estimate the cost for a request."""
        # Default implementation - adapters should override this
        return 0.0
    
    async def validate_request(self, request: AdapterRequest) -> bool:
        """Validate that a request can be handled by this adapter."""
        info = await self.get_info()
        
        # Check if model is supported
        if request.model not in info.models:
            return False
        
        # Check token limits
        if request.max_tokens and request.max_tokens > info.max_tokens:
            return False
        
        # Check streaming support
        if request.stream and not info.supports_streaming:
            return False
        
        # Check function calling support
        if request.functions and not info.supports_functions:
            return False
        
        return True
    
    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.name})"