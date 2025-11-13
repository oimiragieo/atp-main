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

"""ATP Router Service Data Models.

Pydantic models defining the request/response structures for the ATP router service.
These models ensure type safety and validation for all API interactions.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TaskMetadata(BaseModel):
    task_type: Optional[str] = Field(default=None, description="Caller supplied task type if known")
    cluster_hint: Optional[str] = Field(default=None, description="Heuristic cluster classification output")
    prompt_hash: Optional[str] = None
    received_at: Optional[datetime] = None


class AskRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=100000, description="The input prompt text")
    conversation_id: Optional[str] = Field(default=None, max_length=100, description="Conversation identifier")
    turn_id: Optional[str] = Field(default=None, max_length=100, description="Turn identifier")
    quality: str = Field(default="balanced", description="Quality tier: fast|balanced|high")
    max_cost_usd: float = Field(default=0.05, ge=0.001, le=10.0, description="Maximum cost in USD")
    latency_slo_ms: int = Field(default=2000, ge=100, le=30000, description="Latency SLO in milliseconds")
    context_refs: list[str] = Field(default_factory=list, max_length=50, description="Context reference IDs")
    tenant: str = Field(default="public", max_length=50, description="Tenant identifier")
    task_type: Optional[str] = Field(default=None, max_length=50, description="Optional caller-declared task type")
    session_id: Optional[str] = Field(
        default=None, max_length=100, description="Session ID for consistency enforcement"
    )
    consistency_level: Optional[str] = Field(default="EVENTUAL", description="Consistency level: EVENTUAL or RYW")

    @field_validator("quality")
    @classmethod
    def validate_quality(cls, v):
        allowed = {"fast", "balanced", "high"}
        if v not in allowed:
            raise ValueError(f"Quality must be one of {allowed}")
        return v

    @field_validator("consistency_level")
    @classmethod
    def validate_consistency_level(cls, v):
        if v is not None:
            allowed = {"EVENTUAL", "RYW"}
            if v not in allowed:
                raise ValueError(f"Consistency level must be one of {allowed}")
        return v

    @field_validator("context_refs")
    @classmethod
    def validate_context_refs(cls, v):
        for ref in v:
            if not ref or len(ref) > 200:
                raise ValueError("Context refs must be non-empty strings <= 200 characters")
        return v


class Chunk(BaseModel):
    type: str = "chunk"
    seq: int
    text: str
    model: str


class FinalResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    type: str = "final"
    text: str
    model_used: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    savings_pct: float
    escalation_count: int
    quality_score: float
    cluster_hint: Optional[str] = None
    energy_kwh: Optional[float] = None
    co2e_grams: Optional[float] = None
    tool_success: Optional[bool] = True
    format_ok: Optional[bool] = True
    safety_ok: Optional[bool] = True  # GAP-205: Safety validation result
    phase: Optional[str] = None  # shadow|active


class Evidence(BaseModel):
    kind: str = Field(description="Type of evidence (code, test, doc, etc.)")
    file: Optional[str] = None
    lines: Optional[str] = None  # e.g., "60-72"
    content: Optional[str] = None


class Finding(BaseModel):
    id: str = Field(description="Unique finding identifier (F-...)")
    type: str = Field(description="Taxonomy key (e.g., code.vuln.aud_check_missing)")
    file: Optional[str] = None
    span: Optional[str] = None  # e.g., "45-80"
    claim: str = Field(description="Human-readable description of the finding")
    evidence: list[Evidence] = Field(default_factory=list)
    proposed_fix: Optional[str] = None
    tests: list[str] = Field(default_factory=list)
    severity: str = Field(description="high|medium|low|info")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0.0-1.0")
    provenance: list[str] = Field(default_factory=list, description="List of agent IDs that produced this finding")
