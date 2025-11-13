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
Vertex AI Adapter Implementation

This module provides the main adapter interface for Google Cloud Vertex AI,
supporting both pre-trained models and custom model deployments.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from typing import Any

import vertexai
from google.cloud import aiplatform
from google.cloud.aiplatform import gapic
from vertexai.generative_models import GenerativeModel, Part
from vertexai.language_models import ChatModel, TextGenerationModel

from ..base_adapter import AdapterCapability, AdapterError, AdapterResponse, BaseAdapter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class VertexAIConfig:
    """Vertex AI adapter configuration."""

    project_id: str
    location: str = "us-central1"
    credentials_path: str | None = None
    default_model: str = "gemini-pro"
    max_retries: int = 3
    timeout_seconds: int = 300
    enable_streaming: bool = True
    enable_monitoring: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VertexAIModelInfo:
    """Vertex AI model information."""

    model_id: str
    display_name: str
    model_type: str  # "foundation", "custom", "automl"
    endpoint_id: str | None = None
    version_id: str | None = None
    supported_tasks: list[str] = None
    input_token_limit: int = 32768
    output_token_limit: int = 8192
    supports_streaming: bool = True
    supports_function_calling: bool = False
    cost_per_1k_input_tokens: float = 0.0
    cost_per_1k_output_tokens: float = 0.0

    def __post_init__(self):
        if self.supported_tasks is None:
            self.supported_tasks = ["text-generation"]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class VertexAIAdapter(BaseAdapter):
    """Vertex AI adapter for ATP platform."""

    def __init__(self, config: VertexAIConfig):
        super().__init__()
        self.config = config
        self.client = None
        self.prediction_client = None
        self.models: dict[str, VertexAIModelInfo] = {}
        self.endpoints: dict[str, Any] = {}

        # Initialize Vertex AI
        self._initialize_vertex_ai()

        # Load available models
        asyncio.create_task(self._load_models())

    def _initialize_vertex_ai(self):
        """Initialize Vertex AI client and authentication."""
        try:
            # Initialize Vertex AI
            vertexai.init(
                project=self.config.project_id, location=self.config.location, credentials=self.config.credentials_path
            )

            # Initialize AI Platform client
            aiplatform.init(
                project=self.config.project_id, location=self.config.location, credentials=self.config.credentials_path
            )

            # Create prediction client
            client_options = {"api_endpoint": f"{self.config.location}-aiplatform.googleapis.com"}
            self.prediction_client = gapic.PredictionServiceClient(client_options=client_options)

            logger.info(f"Initialized Vertex AI for project {self.config.project_id} in {self.config.location}")

        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI: {e}")
            raise

    async def _load_models(self):
        """Load available models and endpoints."""
        try:
            # Load foundation models
            await self._load_foundation_models()

            # Load custom models and endpoints
            await self._load_custom_models()

            logger.info(f"Loaded {len(self.models)} Vertex AI models")

        except Exception as e:
            logger.error(f"Failed to load models: {e}")

    async def _load_foundation_models(self):
        """Load Vertex AI foundation models."""

        # Gemini models
        gemini_models = [
            VertexAIModelInfo(
                model_id="gemini-pro",
                display_name="Gemini Pro",
                model_type="foundation",
                supported_tasks=["text-generation", "chat", "code-generation"],
                input_token_limit=32768,
                output_token_limit=8192,
                supports_streaming=True,
                supports_function_calling=True,
                cost_per_1k_input_tokens=0.0005,
                cost_per_1k_output_tokens=0.0015,
            ),
            VertexAIModelInfo(
                model_id="gemini-pro-vision",
                display_name="Gemini Pro Vision",
                model_type="foundation",
                supported_tasks=["text-generation", "vision", "multimodal"],
                input_token_limit=16384,
                output_token_limit=8192,
                supports_streaming=True,
                supports_function_calling=False,
                cost_per_1k_input_tokens=0.00025,
                cost_per_1k_output_tokens=0.0005,
            ),
            VertexAIModelInfo(
                model_id="gemini-1.5-pro",
                display_name="Gemini 1.5 Pro",
                model_type="foundation",
                supported_tasks=["text-generation", "chat", "code-generation", "vision"],
                input_token_limit=1048576,  # 1M tokens
                output_token_limit=8192,
                supports_streaming=True,
                supports_function_calling=True,
                cost_per_1k_input_tokens=0.0035,
                cost_per_1k_output_tokens=0.0105,
            ),
        ]

        # PaLM models
        palm_models = [
            VertexAIModelInfo(
                model_id="text-bison",
                display_name="PaLM 2 Text Bison",
                model_type="foundation",
                supported_tasks=["text-generation"],
                input_token_limit=8192,
                output_token_limit=1024,
                supports_streaming=False,
                supports_function_calling=False,
                cost_per_1k_input_tokens=0.0005,
                cost_per_1k_output_tokens=0.0005,
            ),
            VertexAIModelInfo(
                model_id="chat-bison",
                display_name="PaLM 2 Chat Bison",
                model_type="foundation",
                supported_tasks=["chat"],
                input_token_limit=8192,
                output_token_limit=1024,
                supports_streaming=False,
                supports_function_calling=False,
                cost_per_1k_input_tokens=0.0005,
                cost_per_1k_output_tokens=0.0005,
            ),
            VertexAIModelInfo(
                model_id="code-bison",
                display_name="PaLM 2 Code Bison",
                model_type="foundation",
                supported_tasks=["code-generation"],
                input_token_limit=6144,
                output_token_limit=1024,
                supports_streaming=False,
                supports_function_calling=False,
                cost_per_1k_input_tokens=0.0005,
                cost_per_1k_output_tokens=0.0005,
            ),
        ]

        # Add all models to registry
        for model in gemini_models + palm_models:
            self.models[model.model_id] = model

    async def _load_custom_models(self):
        """Load custom models and endpoints."""
        try:
            # List all endpoints in the project

            # This would require async implementation
            # For now, we'll use a placeholder
            # endpoints = await self._list_endpoints(parent)

            # TODO: Implement endpoint listing and model registration
            logger.info("Custom model loading not yet implemented")

        except Exception as e:
            logger.error(f"Failed to load custom models: {e}")

    @property
    def name(self) -> str:
        return "vertex-ai"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def capabilities(self) -> list[AdapterCapability]:
        return [
            AdapterCapability.TEXT_GENERATION,
            AdapterCapability.CHAT,
            AdapterCapability.CODE_GENERATION,
            AdapterCapability.VISION,
            AdapterCapability.MULTIMODAL,
            AdapterCapability.STREAMING,
            AdapterCapability.FUNCTION_CALLING,
            AdapterCapability.BATCH_PROCESSING,
        ]

    async def get_models(self) -> list[dict[str, Any]]:
        """Get list of available models."""
        return [model.to_dict() for model in self.models.values()]

    async def health_check(self) -> dict[str, Any]:
        """Perform health check."""
        try:
            # Test with a simple prediction
            model = GenerativeModel(self.config.default_model)
            response = model.generate_content("Hello")

            return {
                "status": "healthy",
                "timestamp": time.time(),
                "models_available": len(self.models),
                "default_model": self.config.default_model,
                "test_response_length": len(response.text) if response.text else 0,
            }

        except Exception as e:
            return {"status": "unhealthy", "timestamp": time.time(), "error": str(e)}

    async def generate_text(
        self,
        prompt: str,
        model_id: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        stop_sequences: list[str] | None = None,
        stream: bool = False,
        **kwargs,
    ) -> AdapterResponse | AsyncIterator[AdapterResponse]:
        """Generate text using Vertex AI models."""

        model_id = model_id or self.config.default_model

        if model_id not in self.models:
            raise AdapterError(f"Model {model_id} not found")

        model_info = self.models[model_id]

        try:
            if stream and model_info.supports_streaming:
                return self._generate_text_stream(
                    prompt, model_id, max_tokens, temperature, top_p, top_k, stop_sequences, **kwargs
                )
            else:
                return await self._generate_text_sync(
                    prompt, model_id, max_tokens, temperature, top_p, top_k, stop_sequences, **kwargs
                )

        except Exception as e:
            logger.error(f"Text generation failed: {e}")
            raise AdapterError(f"Text generation failed: {str(e)}")

    async def _generate_text_sync(
        self,
        prompt: str,
        model_id: str,
        max_tokens: int | None,
        temperature: float | None,
        top_p: float | None,
        top_k: int | None,
        stop_sequences: list[str] | None,
        **kwargs,
    ) -> AdapterResponse:
        """Generate text synchronously."""

        start_time = time.time()

        try:
            # Prepare generation config
            generation_config = {}
            if max_tokens:
                generation_config["max_output_tokens"] = max_tokens
            if temperature is not None:
                generation_config["temperature"] = temperature
            if top_p is not None:
                generation_config["top_p"] = top_p
            if top_k is not None:
                generation_config["top_k"] = top_k
            if stop_sequences:
                generation_config["stop_sequences"] = stop_sequences

            # Handle different model types
            if model_id.startswith("gemini"):
                model = GenerativeModel(model_id)

                # Handle multimodal input
                if "images" in kwargs:
                    contents = [prompt]
                    for image_data in kwargs["images"]:
                        contents.append(Part.from_data(image_data, mime_type="image/jpeg"))
                    response = model.generate_content(contents, generation_config=generation_config)
                else:
                    response = model.generate_content(prompt, generation_config=generation_config)

                text = response.text

            elif model_id in ["text-bison", "chat-bison", "code-bison"]:
                if model_id == "text-bison":
                    model = TextGenerationModel.from_pretrained(model_id)
                    response = model.predict(prompt, **generation_config)
                    text = response.text
                elif model_id == "chat-bison":
                    model = ChatModel.from_pretrained(model_id)
                    chat = model.start_chat()
                    response = chat.send_message(prompt, **generation_config)
                    text = response.text
                else:  # code-bison
                    model = TextGenerationModel.from_pretrained(model_id)
                    response = model.predict(prompt, **generation_config)
                    text = response.text
            else:
                raise AdapterError(f"Unsupported model: {model_id}")

            # Calculate metrics
            duration = time.time() - start_time
            input_tokens = self._estimate_tokens(prompt)
            output_tokens = self._estimate_tokens(text)

            model_info = self.models[model_id]
            cost = (input_tokens / 1000) * model_info.cost_per_1k_input_tokens + (
                output_tokens / 1000
            ) * model_info.cost_per_1k_output_tokens

            return AdapterResponse(
                text=text,
                model=model_id,
                usage={
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
                cost=cost,
                latency=duration,
                metadata={"model_type": model_info.model_type, "generation_config": generation_config},
            )

        except Exception as e:
            logger.error(f"Sync text generation failed: {e}")
            raise AdapterError(f"Text generation failed: {str(e)}")

    async def _generate_text_stream(
        self,
        prompt: str,
        model_id: str,
        max_tokens: int | None,
        temperature: float | None,
        top_p: float | None,
        top_k: int | None,
        stop_sequences: list[str] | None,
        **kwargs,
    ) -> AsyncIterator[AdapterResponse]:
        """Generate text with streaming."""

        start_time = time.time()

        try:
            # Prepare generation config
            generation_config = {}
            if max_tokens:
                generation_config["max_output_tokens"] = max_tokens
            if temperature is not None:
                generation_config["temperature"] = temperature
            if top_p is not None:
                generation_config["top_p"] = top_p
            if top_k is not None:
                generation_config["top_k"] = top_k
            if stop_sequences:
                generation_config["stop_sequences"] = stop_sequences

            # Only Gemini models support streaming currently
            if not model_id.startswith("gemini"):
                # Fall back to sync generation for non-streaming models
                response = await self._generate_text_sync(
                    prompt, model_id, max_tokens, temperature, top_p, top_k, stop_sequences, **kwargs
                )
                yield response
                return

            model = GenerativeModel(model_id)

            # Handle multimodal input
            if "images" in kwargs:
                contents = [prompt]
                for image_data in kwargs["images"]:
                    contents.append(Part.from_data(image_data, mime_type="image/jpeg"))
                response_stream = model.generate_content(contents, generation_config=generation_config, stream=True)
            else:
                response_stream = model.generate_content(prompt, generation_config=generation_config, stream=True)

            accumulated_text = ""
            input_tokens = self._estimate_tokens(prompt)
            model_info = self.models[model_id]

            for chunk in response_stream:
                if chunk.text:
                    accumulated_text += chunk.text
                    output_tokens = self._estimate_tokens(accumulated_text)

                    cost = (input_tokens / 1000) * model_info.cost_per_1k_input_tokens + (
                        output_tokens / 1000
                    ) * model_info.cost_per_1k_output_tokens

                    yield AdapterResponse(
                        text=chunk.text,
                        model=model_id,
                        usage={
                            "prompt_tokens": input_tokens,
                            "completion_tokens": output_tokens,
                            "total_tokens": input_tokens + output_tokens,
                        },
                        cost=cost,
                        latency=time.time() - start_time,
                        metadata={
                            "model_type": model_info.model_type,
                            "generation_config": generation_config,
                            "is_streaming": True,
                            "accumulated_text": accumulated_text,
                        },
                    )

        except Exception as e:
            logger.error(f"Streaming text generation failed: {e}")
            raise AdapterError(f"Streaming text generation failed: {str(e)}")

    async def chat(
        self,
        messages: list[dict[str, str]],
        model_id: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        stream: bool = False,
        **kwargs,
    ) -> AdapterResponse | AsyncIterator[AdapterResponse]:
        """Chat with Vertex AI models."""

        model_id = model_id or self.config.default_model

        if model_id not in self.models:
            raise AdapterError(f"Model {model_id} not found")

        # Convert messages to prompt format
        prompt = self._messages_to_prompt(messages)

        return await self.generate_text(
            prompt=prompt, model_id=model_id, max_tokens=max_tokens, temperature=temperature, stream=stream, **kwargs
        )

    def _messages_to_prompt(self, messages: list[dict[str, str]]) -> str:
        """Convert chat messages to prompt format."""
        prompt_parts = []

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")

            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"Human: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")

        prompt_parts.append("Assistant:")
        return "\n\n".join(prompt_parts)

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        # Simple estimation: ~4 characters per token
        return max(1, len(text) // 4)

    async def get_embeddings(self, texts: list[str], model_id: str | None = None, **kwargs) -> list[list[float]]:
        """Get embeddings for texts."""
        # Vertex AI embeddings would be implemented here
        # For now, return placeholder
        raise NotImplementedError("Embeddings not yet implemented for Vertex AI")

    async def batch_predict(
        self, inputs: list[dict[str, Any]], model_id: str | None = None, **kwargs
    ) -> list[AdapterResponse]:
        """Perform batch prediction."""

        model_id = model_id or self.config.default_model

        if model_id not in self.models:
            raise AdapterError(f"Model {model_id} not found")

        results = []

        # Process inputs in batches
        for input_data in inputs:
            if "prompt" in input_data:
                response = await self.generate_text(
                    prompt=input_data["prompt"], model_id=model_id, **input_data.get("parameters", {})
                )
                results.append(response)
            else:
                raise AdapterError("Invalid input format for batch prediction")

        return results

    async def deploy_model(
        self,
        model_name: str,
        model_artifact_uri: str,
        machine_type: str = "n1-standard-4",
        min_replica_count: int = 1,
        max_replica_count: int = 10,
        **kwargs,
    ) -> str:
        """Deploy a custom model to Vertex AI."""

        try:
            # Create model
            model = aiplatform.Model.upload(
                display_name=model_name,
                artifact_uri=model_artifact_uri,
                serving_container_image_uri="gcr.io/cloud-aiplatform/prediction/tf2-cpu.2-8:latest",
                **kwargs,
            )

            # Deploy model to endpoint
            endpoint = model.deploy(
                machine_type=machine_type,
                min_replica_count=min_replica_count,
                max_replica_count=max_replica_count,
                traffic_percentage=100,
            )

            # Register the deployed model
            model_info = VertexAIModelInfo(
                model_id=model_name,
                display_name=model_name,
                model_type="custom",
                endpoint_id=endpoint.name,
                supported_tasks=["text-generation"],
                supports_streaming=False,
                supports_function_calling=False,
            )

            self.models[model_name] = model_info
            self.endpoints[endpoint.name] = endpoint

            logger.info(f"Deployed model {model_name} to endpoint {endpoint.name}")

            return endpoint.name

        except Exception as e:
            logger.error(f"Model deployment failed: {e}")
            raise AdapterError(f"Model deployment failed: {str(e)}")

    async def undeploy_model(self, endpoint_id: str) -> bool:
        """Undeploy a model from Vertex AI."""

        try:
            if endpoint_id in self.endpoints:
                endpoint = self.endpoints[endpoint_id]
                endpoint.undeploy_all()
                endpoint.delete()

                # Remove from registry
                del self.endpoints[endpoint_id]

                # Remove model info
                for model_id, model_info in list(self.models.items()):
                    if model_info.endpoint_id == endpoint_id:
                        del self.models[model_id]
                        break

                logger.info(f"Undeployed model from endpoint {endpoint_id}")
                return True
            else:
                logger.warning(f"Endpoint {endpoint_id} not found")
                return False

        except Exception as e:
            logger.error(f"Model undeployment failed: {e}")
            return False

    async def get_model_metrics(self, model_id: str) -> dict[str, Any]:
        """Get model performance metrics."""

        if model_id not in self.models:
            raise AdapterError(f"Model {model_id} not found")

        model_info = self.models[model_id]

        # For custom models with endpoints, get actual metrics
        if model_info.endpoint_id:
            try:
                # This would integrate with Cloud Monitoring
                # For now, return placeholder metrics
                return {
                    "model_id": model_id,
                    "endpoint_id": model_info.endpoint_id,
                    "requests_per_minute": 0,
                    "average_latency_ms": 0,
                    "error_rate": 0.0,
                    "cpu_utilization": 0.0,
                    "memory_utilization": 0.0,
                }
            except Exception as e:
                logger.error(f"Failed to get metrics for {model_id}: {e}")

        # For foundation models, return basic info
        return {
            "model_id": model_id,
            "model_type": model_info.model_type,
            "supported_tasks": model_info.supported_tasks,
            "input_token_limit": model_info.input_token_limit,
            "output_token_limit": model_info.output_token_limit,
        }

    async def close(self):
        """Clean up resources."""
        try:
            # Close any open connections
            if self.prediction_client:
                # Prediction client doesn't have explicit close method
                pass

            logger.info("Vertex AI adapter closed")

        except Exception as e:
            logger.error(f"Error closing Vertex AI adapter: {e}")


# Factory function for creating Vertex AI adapter
def create_vertex_ai_adapter(
    project_id: str, location: str = "us-central1", credentials_path: str | None = None, **kwargs
) -> VertexAIAdapter:
    """Create a Vertex AI adapter instance."""

    config = VertexAIConfig(project_id=project_id, location=location, credentials_path=credentials_path, **kwargs)

    return VertexAIAdapter(config)
