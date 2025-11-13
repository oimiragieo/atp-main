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
ATP SDK Data Models

Pydantic models for ATP API requests and responses.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, validator


class ChatMessage(BaseModel):
    """A chat message in a conversation."""
    
    role: str = Field(..., description="The role of the message sender (user, assistant, system)")
    content: str = Field(..., description="The content of the message")
    name: Optional[str] = Field(None, description="Optional name of the message sender")
    function_call: Optional[Dict[str, Any]] = Field(None, description="Function call data")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(None, description="Tool calls data")
    
    @validator('role')
    def validate_role(cls, v):
        if v not in ['user', 'assistant', 'system', 'function', 'tool']:
            raise ValueError('Role must be one of: user, assistant, system, function, tool')
        return v


class ChatRequest(BaseModel):
    """Request for chat completion."""
    
    messages: List[ChatMessage] = Field(..., description="List of messages in the conversation")
    model: Optional[str] = Field(None, description="Specific model to use")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(None, gt=0, description="Maximum tokens to generate")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Nucleus sampling parameter")
    frequency_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0, description="Frequency penalty")
    presence_penalty: Optional[float] = Field(None, ge=-2.0, le=2.0, description="Presence penalty")
    stop: Optional[Union[str, List[str]]] = Field(None, description="Stop sequences")
    stream: bool = Field(False, description="Whether to stream the response")
    functions: Optional[List[Dict[str, Any]]] = Field(None, description="Available functions")
    function_call: Optional[Union[str, Dict[str, str]]] = Field(None, description="Function call preference")
    tools: Optional[List[Dict[str, Any]]] = Field(None, description="Available tools")
    tool_choice: Optional[Union[str, Dict[str, Any]]] = Field(None, description="Tool choice preference")
    user: Optional[str] = Field(None, description="User identifier for tracking")
    
    # ATP-specific parameters
    cost_limit: Optional[float] = Field(None, description="Maximum cost for this request")
    quality_preference: Optional[str] = Field(None, description="Quality preference (speed, balanced, quality)")
    provider_preference: Optional[List[str]] = Field(None, description="Preferred providers")
    
    class Config:
        extra = "allow"  # Allow additional model-specific parameters


class Usage(BaseModel):
    """Token usage information."""
    
    prompt_tokens: int = Field(..., description="Number of tokens in the prompt")
    completion_tokens: int = Field(..., description="Number of tokens in the completion")
    total_tokens: int = Field(..., description="Total number of tokens")


class Choice(BaseModel):
    """A completion choice."""
    
    index: int = Field(..., description="Index of this choice")
    message: ChatMessage = Field(..., description="The generated message")
    finish_reason: Optional[str] = Field(None, description="Reason for completion finish")
    logprobs: Optional[Dict[str, Any]] = Field(None, description="Log probabilities")


class ChatResponse(BaseModel):
    """Response from chat completion."""
    
    id: str = Field(..., description="Unique identifier for the completion")
    object: str = Field(..., description="Object type (chat.completion)")
    created: int = Field(..., description="Unix timestamp of creation")
    model: str = Field(..., description="Model used for completion")
    choices: List[Choice] = Field(..., description="List of completion choices")
    usage: Usage = Field(..., description="Token usage information")
    
    # ATP-specific fields
    provider: Optional[str] = Field(None, description="Provider used")
    cost: Optional[float] = Field(None, description="Cost of the request")
    latency: Optional[float] = Field(None, description="Request latency in seconds")
    quality_score: Optional[float] = Field(None, description="Quality score (0-1)")


class StreamingChoice(BaseModel):
    """A streaming completion choice."""
    
    index: int = Field(..., description="Index of this choice")
    delta: ChatMessage = Field(..., description="The incremental message delta")
    finish_reason: Optional[str] = Field(None, description="Reason for completion finish")


class StreamingResponse(BaseModel):
    """Streaming response chunk."""
    
    id: str = Field(..., description="Unique identifier for the completion")
    object: str = Field(..., description="Object type (chat.completion.chunk)")
    created: int = Field(..., description="Unix timestamp of creation")
    model: str = Field(..., description="Model used for completion")
    choices: List[StreamingChoice] = Field(..., description="List of streaming choices")
    
    # ATP-specific fields
    provider: Optional[str] = Field(None, description="Provider used")


class ModelCapabilities(BaseModel):
    """Model capabilities information."""
    
    chat: bool = Field(False, description="Supports chat completions")
    completion: bool = Field(False, description="Supports text completions")
    embedding: bool = Field(False, description="Supports embeddings")
    image_generation: bool = Field(False, description="Supports image generation")
    image_analysis: bool = Field(False, description="Supports image analysis")
    function_calling: bool = Field(False, description="Supports function calling")
    tool_use: bool = Field(False, description="Supports tool use")
    streaming: bool = Field(False, description="Supports streaming responses")


class ModelPricing(BaseModel):
    """Model pricing information."""
    
    input_cost_per_token: float = Field(..., description="Cost per input token")
    output_cost_per_token: float = Field(..., description="Cost per output token")
    currency: str = Field("USD", description="Currency for pricing")
    billing_unit: str = Field("token", description="Billing unit")


class ModelInfo(BaseModel):
    """Information about an available model."""
    
    id: str = Field(..., description="Model identifier")
    name: str = Field(..., description="Human-readable model name")
    provider: str = Field(..., description="Provider name")
    description: Optional[str] = Field(None, description="Model description")
    capabilities: ModelCapabilities = Field(..., description="Model capabilities")
    pricing: ModelPricing = Field(..., description="Model pricing")
    context_length: int = Field(..., description="Maximum context length")
    max_output_tokens: int = Field(..., description="Maximum output tokens")
    created: datetime = Field(..., description="Model creation date")
    updated: datetime = Field(..., description="Model last update date")
    status: str = Field(..., description="Model status (active, deprecated, etc.)")
    tags: List[str] = Field(default_factory=list, description="Model tags")


class ProviderStatus(BaseModel):
    """Provider status information."""
    
    available: bool = Field(..., description="Whether provider is available")
    latency: Optional[float] = Field(None, description="Average latency in seconds")
    error_rate: Optional[float] = Field(None, description="Error rate (0-1)")
    last_check: datetime = Field(..., description="Last health check time")


class ProviderInfo(BaseModel):
    """Information about a provider."""
    
    id: str = Field(..., description="Provider identifier")
    name: str = Field(..., description="Provider name")
    description: Optional[str] = Field(None, description="Provider description")
    status: ProviderStatus = Field(..., description="Provider status")
    models: List[str] = Field(..., description="Available model IDs")
    regions: List[str] = Field(..., description="Available regions")
    capabilities: List[str] = Field(..., description="Provider capabilities")


class CostBreakdown(BaseModel):
    """Cost breakdown by category."""
    
    compute: float = Field(0.0, description="Compute costs")
    storage: float = Field(0.0, description="Storage costs")
    network: float = Field(0.0, description="Network costs")
    ai_ml: float = Field(0.0, description="AI/ML service costs")
    other: float = Field(0.0, description="Other costs")


class CostInfo(BaseModel):
    """Cost information and breakdown."""
    
    total_cost: float = Field(..., description="Total cost")
    currency: str = Field("USD", description="Currency")
    period_start: datetime = Field(..., description="Period start date")
    period_end: datetime = Field(..., description="Period end date")
    breakdown: CostBreakdown = Field(..., description="Cost breakdown")
    daily_costs: List[Dict[str, float]] = Field(..., description="Daily cost data")
    top_models: List[Dict[str, Any]] = Field(..., description="Top models by cost")
    top_providers: List[Dict[str, Any]] = Field(..., description="Top providers by cost")


class UsageMetrics(BaseModel):
    """Usage metrics."""
    
    total_requests: int = Field(..., description="Total number of requests")
    total_tokens: int = Field(..., description="Total tokens processed")
    total_input_tokens: int = Field(..., description="Total input tokens")
    total_output_tokens: int = Field(..., description="Total output tokens")
    average_latency: float = Field(..., description="Average latency in seconds")
    error_rate: float = Field(..., description="Error rate (0-1)")
    success_rate: float = Field(..., description="Success rate (0-1)")


class UsageStats(BaseModel):
    """Usage statistics."""
    
    period_start: datetime = Field(..., description="Period start date")
    period_end: datetime = Field(..., description="Period end date")
    metrics: UsageMetrics = Field(..., description="Usage metrics")
    daily_usage: List[Dict[str, Any]] = Field(..., description="Daily usage data")
    model_usage: List[Dict[str, Any]] = Field(..., description="Usage by model")
    provider_usage: List[Dict[str, Any]] = Field(..., description="Usage by provider")


class PolicyRule(BaseModel):
    """A policy rule."""
    
    condition: str = Field(..., description="Rule condition")
    action: str = Field(..., description="Action to take")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Rule parameters")


class PolicyInfo(BaseModel):
    """Policy information."""
    
    id: str = Field(..., description="Policy identifier")
    name: str = Field(..., description="Policy name")
    description: Optional[str] = Field(None, description="Policy description")
    tenant_id: str = Field(..., description="Tenant ID")
    project_id: Optional[str] = Field(None, description="Project ID")
    rules: List[PolicyRule] = Field(..., description="Policy rules")
    enabled: bool = Field(True, description="Whether policy is enabled")
    created: datetime = Field(..., description="Policy creation date")
    updated: datetime = Field(..., description="Policy last update date")
    created_by: str = Field(..., description="Policy creator")


class EmbeddingRequest(BaseModel):
    """Request for embeddings."""
    
    input: Union[str, List[str]] = Field(..., description="Text to embed")
    model: Optional[str] = Field(None, description="Embedding model to use")
    encoding_format: str = Field("float", description="Encoding format")
    user: Optional[str] = Field(None, description="User identifier")


class Embedding(BaseModel):
    """An embedding vector."""
    
    object: str = Field("embedding", description="Object type")
    embedding: List[float] = Field(..., description="Embedding vector")
    index: int = Field(..., description="Index in the input list")


class EmbeddingResponse(BaseModel):
    """Response from embedding request."""
    
    object: str = Field("list", description="Object type")
    data: List[Embedding] = Field(..., description="List of embeddings")
    model: str = Field(..., description="Model used")
    usage: Usage = Field(..., description="Token usage")
    
    # ATP-specific fields
    provider: Optional[str] = Field(None, description="Provider used")
    cost: Optional[float] = Field(None, description="Cost of the request")


class ImageGenerationRequest(BaseModel):
    """Request for image generation."""
    
    prompt: str = Field(..., description="Text prompt for image generation")
    model: Optional[str] = Field(None, description="Image generation model")
    n: int = Field(1, ge=1, le=10, description="Number of images to generate")
    size: str = Field("1024x1024", description="Image size")
    quality: str = Field("standard", description="Image quality")
    style: Optional[str] = Field(None, description="Image style")
    response_format: str = Field("url", description="Response format (url or b64_json)")
    user: Optional[str] = Field(None, description="User identifier")


class ImageData(BaseModel):
    """Generated image data."""
    
    url: Optional[str] = Field(None, description="Image URL")
    b64_json: Optional[str] = Field(None, description="Base64 encoded image")
    revised_prompt: Optional[str] = Field(None, description="Revised prompt used")


class ImageGenerationResponse(BaseModel):
    """Response from image generation."""
    
    created: int = Field(..., description="Unix timestamp of creation")
    data: List[ImageData] = Field(..., description="Generated images")
    
    # ATP-specific fields
    provider: Optional[str] = Field(None, description="Provider used")
    cost: Optional[float] = Field(None, description="Cost of the request")