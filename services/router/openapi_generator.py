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
OpenAPI Documentation Generator
This module provides comprehensive OpenAPI specification generation including:
- Dynamic schema generation
- Multi-version API documentation
- Interactive documentation
- Schema validation
- Code generation support
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum
import yaml
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DocumentationFormat(Enum):
    """Documentation output formats."""
    JSON = "json"
    YAML = "yaml"
    HTML = "html"

@dataclass
class APIDocumentationConfig:
    """Configuration for API documentation generation."""
    title: str = "ATP Enterprise API"
    description: str = "Enterprise AI Text Processing Platform API"
    version: str = "1.0.0"
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_url: Optional[str] = None
    license_name: Optional[str] = "Apache 2.0"
    license_url: Optional[str] = "https://www.apache.org/licenses/LICENSE-2.0"
    terms_of_service: Optional[str] = None
    servers: List[Dict[str, str]] = None
    include_examples: bool = True
    include_rate_limits: bool = True
    include_deprecation_info: bool = True

    def __post_init__(self):
        if self.servers is None:
            self.servers = [
                {"url": "https://api.atp.example.com", "description": "Production"},
                {"url": "https://staging-api.atp.example.com", "description": "Staging"},
                {"url": "http://localhost:8000", "description": "Development"}
            ]

class OpenAPIGenerator:
    """OpenAPI specification generator."""

    def __init__(self, config: APIDocumentationConfig = None):
        self.config = config or APIDocumentationConfig()
        self.custom_schemas: Dict[str, Dict[str, Any]] = {}
        self.custom_examples: Dict[str, Dict[str, Any]] = {}
        self.rate_limit_info: Dict[str, Dict[str, Any]] = {}
        
        # Initialize default schemas and examples
        self._initialize_default_schemas()
        self._initialize_default_examples()

    def _initialize_default_schemas(self):
        """Initialize default API schemas."""
        # Chat completion request schema
        self.custom_schemas["ChatCompletionRequest"] = {
            "type": "object",
            "required": ["messages"],
            "properties": {
                "messages": {
                    "type": "array",
                    "items": {
                        "$ref": "#/components/schemas/ChatMessage"
                    },
                    "description": "List of messages in the conversation"
                },
                "model": {
                    "type": "string",
                    "description": "Model to use for completion",
                    "example": "gpt-4"
                },
                "temperature": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 2,
                    "default": 1,
                    "description": "Sampling temperature"
                },
                "max_tokens": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Maximum tokens to generate"
                },
                "stream": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to stream responses"
                },
                "top_p": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 1,
                    "description": "Nucleus sampling parameter"
                }
            }
        }

        # Chat message schema
        self.custom_schemas["ChatMessage"] = {
            "type": "object",
            "required": ["role", "content"],
            "properties": {
                "role": {
                    "type": "string",
                    "enum": ["system", "user", "assistant"],
                    "description": "Role of the message sender"
                },
                "content": {
                    "type": "string",
                    "description": "Content of the message"
                },
                "name": {
                    "type": "string",
                    "description": "Optional name of the sender"
                }
            }
        }

        # Chat completion response schema
        self.custom_schemas["ChatCompletionResponse"] = {
            "type": "object",
            "required": ["id", "object", "created", "model", "choices"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Unique identifier for the completion"
                },
                "object": {
                    "type": "string",
                    "enum": ["chat.completion"],
                    "description": "Object type"
                },
                "created": {
                    "type": "integer",
                    "description": "Unix timestamp of creation"
                },
                "model": {
                    "type": "string",
                    "description": "Model used for completion"
                },
                "choices": {
                    "type": "array",
                    "items": {
                        "$ref": "#/components/schemas/ChatChoice"
                    },
                    "description": "List of completion choices"
                },
                "usage": {
                    "$ref": "#/components/schemas/Usage",
                    "description": "Token usage information"
                }
            }
        }

        # Chat choice schema
        self.custom_schemas["ChatChoice"] = {
            "type": "object",
            "required": ["index", "message", "finish_reason"],
            "properties": {
                "index": {
                    "type": "integer",
                    "description": "Choice index"
                },
                "message": {
                    "$ref": "#/components/schemas/ChatMessage",
                    "description": "Generated message"
                },
                "finish_reason": {
                    "type": "string",
                    "enum": ["stop", "length", "content_filter"],
                    "description": "Reason for completion finish"
                }
            }
        }

        # Usage schema
        self.custom_schemas["Usage"] = {
            "type": "object",
            "required": ["prompt_tokens", "completion_tokens", "total_tokens"],
            "properties": {
                "prompt_tokens": {
                    "type": "integer",
                    "description": "Tokens in the prompt"
                },
                "completion_tokens": {
                    "type": "integer",
                    "description": "Tokens in the completion"
                },
                "total_tokens": {
                    "type": "integer",
                    "description": "Total tokens used"
                }
            }
        }

        # Error response schema
        self.custom_schemas["ErrorResponse"] = {
            "type": "object",
            "required": ["error"],
            "properties": {
                "error": {
                    "type": "object",
                    "required": ["message", "type"],
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Error message"
                        },
                        "type": {
                            "type": "string",
                            "description": "Error type"
                        },
                        "code": {
                            "type": "string",
                            "description": "Error code"
                        }
                    }
                }
            }
        }

        # Model information schema
        self.custom_schemas["Model"] = {
            "type": "object",
            "required": ["id", "object", "created", "owned_by"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Model identifier"
                },
                "object": {
                    "type": "string",
                    "enum": ["model"],
                    "description": "Object type"
                },
                "created": {
                    "type": "integer",
                    "description": "Unix timestamp of creation"
                },
                "owned_by": {
                    "type": "string",
                    "description": "Organization that owns the model"
                },
                "permission": {
                    "type": "array",
                    "items": {
                        "type": "object"
                    },
                    "description": "Model permissions"
                }
            }
        }

    def _initialize_default_examples(self):
        """Initialize default API examples."""
        # Chat completion examples
        self.custom_examples["ChatCompletionRequest"] = {
            "simple_chat": {
                "summary": "Simple chat completion",
                "value": {
                    "model": "gpt-4",
                    "messages": [
                        {"role": "user", "content": "Hello, how are you?"}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 150
                }
            },
            "conversation": {
                "summary": "Multi-turn conversation",
                "value": {
                    "model": "gpt-4",
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": "What's the weather like?"},
                        {"role": "assistant", "content": "I don't have access to current weather data."},
                        {"role": "user", "content": "Can you help me with coding?"}
                    ],
                    "temperature": 0.5,
                    "max_tokens": 200
                }
            },
            "streaming": {
                "summary": "Streaming completion",
                "value": {
                    "model": "gpt-4",
                    "messages": [
                        {"role": "user", "content": "Write a short story"}
                    ],
                    "stream": True,
                    "temperature": 0.8,
                    "max_tokens": 500
                }
            }
        }

        self.custom_examples["ChatCompletionResponse"] = {
            "successful_completion": {
                "summary": "Successful completion",
                "value": {
                    "id": "chatcmpl-123",
                    "object": "chat.completion",
                    "created": 1677652288,
                    "model": "gpt-4",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "Hello! I'm doing well, thank you for asking. How can I help you today?"
                            },
                            "finish_reason": "stop"
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 9,
                        "completion_tokens": 18,
                        "total_tokens": 27
                    }
                }
            }
        }

    def generate_openapi_spec(
        self, 
        app: FastAPI = None,
        version: str = None,
        include_internal: bool = False
    ) -> Dict[str, Any]:
        """Generate OpenAPI specification."""
        # Use provided version or config version
        api_version = version or self.config.version
        
        # Base OpenAPI specification
        openapi_spec = {
            "openapi": "3.0.0",
            "info": {
                "title": self.config.title,
                "description": self.config.description,
                "version": api_version,
                "termsOfService": self.config.terms_of_service,
                "contact": {},
                "license": {}
            },
            "servers": self.config.servers,
            "paths": {},
            "components": {
                "schemas": self.custom_schemas.copy(),
                "securitySchemes": {
                    "BearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "bearerFormat": "JWT",
                        "description": "JWT token authentication"
                    },
                    "ApiKeyAuth": {
                        "type": "apiKey",
                        "in": "header",
                        "name": "X-API-Key",
                        "description": "API key authentication"
                    }
                },
                "responses": {
                    "RateLimitExceeded": {
                        "description": "Rate limit exceeded",
                        "headers": {
                            "X-RateLimit-Remaining": {
                                "schema": {"type": "integer"},
                                "description": "Requests remaining in current window"
                            },
                            "X-RateLimit-Reset": {
                                "schema": {"type": "integer"},
                                "description": "Unix timestamp when rate limit resets"
                            },
                            "Retry-After": {
                                "schema": {"type": "integer"},
                                "description": "Seconds to wait before retrying"
                            }
                        },
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        }
                    },
                    "Unauthorized": {
                        "description": "Authentication required",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        }
                    },
                    "Forbidden": {
                        "description": "Insufficient permissions",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        }
                    }
                }
            },
            "security": [
                {"BearerAuth": []},
                {"ApiKeyAuth": []}
            ]
        }

        # Add contact information if provided
        if self.config.contact_name or self.config.contact_email or self.config.contact_url:
            contact = {}
            if self.config.contact_name:
                contact["name"] = self.config.contact_name
            if self.config.contact_email:
                contact["email"] = self.config.contact_email
            if self.config.contact_url:
                contact["url"] = self.config.contact_url
            openapi_spec["info"]["contact"] = contact

        # Add license information if provided
        if self.config.license_name or self.config.license_url:
            license_info = {}
            if self.config.license_name:
                license_info["name"] = self.config.license_name
            if self.config.license_url:
                license_info["url"] = self.config.license_url
            openapi_spec["info"]["license"] = license_info

        # Generate paths from FastAPI app if provided
        if app:
            fastapi_openapi = get_openapi(
                title=self.config.title,
                version=api_version,
                description=self.config.description,
                routes=app.routes
            )
            
            # Merge paths
            if "paths" in fastapi_openapi:
                openapi_spec["paths"].update(fastapi_openapi["paths"])
            
            # Merge components
            if "components" in fastapi_openapi:
                if "schemas" in fastapi_openapi["components"]:
                    openapi_spec["components"]["schemas"].update(
                        fastapi_openapi["components"]["schemas"]
                    )
        else:
            # Add default paths manually
            openapi_spec["paths"] = self._generate_default_paths()

        # Add examples if enabled
        if self.config.include_examples:
            self._add_examples_to_spec(openapi_spec)

        # Add rate limiting information if enabled
        if self.config.include_rate_limits:
            self._add_rate_limit_info(openapi_spec)

        return openapi_spec

    def _generate_default_paths(self) -> Dict[str, Any]:
        """Generate default API paths."""
        paths = {
            "/api/v1/chat/completions": {
                "post": {
                    "summary": "Create chat completion",
                    "description": "Generate a chat completion response",
                    "operationId": "createChatCompletion",
                    "tags": ["Chat"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ChatCompletionRequest"}
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Successful completion",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ChatCompletionResponse"}
                                }
                            }
                        },
                        "400": {"$ref": "#/components/responses/BadRequest"},
                        "401": {"$ref": "#/components/responses/Unauthorized"},
                        "429": {"$ref": "#/components/responses/RateLimitExceeded"},
                        "500": {"$ref": "#/components/responses/InternalServerError"}
                    },
                    "security": [{"BearerAuth": []}, {"ApiKeyAuth": []}]
                }
            },
            "/api/v1/models": {
                "get": {
                    "summary": "List available models",
                    "description": "Get a list of available models",
                    "operationId": "listModels",
                    "tags": ["Models"],
                    "responses": {
                        "200": {
                            "description": "List of models",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "object": {"type": "string", "enum": ["list"]},
                                            "data": {
                                                "type": "array",
                                                "items": {"$ref": "#/components/schemas/Model"}
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "401": {"$ref": "#/components/responses/Unauthorized"},
                        "429": {"$ref": "#/components/responses/RateLimitExceeded"}
                    },
                    "security": [{"BearerAuth": []}, {"ApiKeyAuth": []}]
                }
            },
            "/health": {
                "get": {
                    "summary": "Health check",
                    "description": "Check API health status",
                    "operationId": "healthCheck",
                    "tags": ["System"],
                    "responses": {
                        "200": {
                            "description": "API is healthy",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {"type": "string", "enum": ["healthy"]},
                                            "timestamp": {"type": "string", "format": "date-time"}
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "security": []
                }
            }
        }

        return paths

    def _add_examples_to_spec(self, spec: Dict[str, Any]):
        """Add examples to OpenAPI specification."""
        # Add examples to request bodies and responses
        for path_info in spec.get("paths", {}).values():
            for method_info in path_info.values():
                if isinstance(method_info, dict):
                    # Add request body examples
                    if "requestBody" in method_info:
                        content = method_info["requestBody"].get("content", {})
                        for media_type, media_info in content.items():
                            schema_ref = media_info.get("schema", {}).get("$ref", "")
                            schema_name = schema_ref.split("/")[-1] if schema_ref else ""
                            if schema_name in self.custom_examples:
                                media_info["examples"] = self.custom_examples[schema_name]

                    # Add response examples
                    for response_info in method_info.get("responses", {}).values():
                        if isinstance(response_info, dict):
                            content = response_info.get("content", {})
                            for media_type, media_info in content.items():
                                schema_ref = media_info.get("schema", {}).get("$ref", "")
                                schema_name = schema_ref.split("/")[-1] if schema_ref else ""
                                if schema_name in self.custom_examples:
                                    media_info["examples"] = self.custom_examples[schema_name]

    def _add_rate_limit_info(self, spec: Dict[str, Any]):
        """Add rate limiting information to specification."""
        # Add rate limit headers to all responses
        for path_info in spec.get("paths", {}).values():
            for method_info in path_info.values():
                if isinstance(method_info, dict):
                    for status_code, response_info in method_info.get("responses", {}).items():
                        if isinstance(response_info, dict) and status_code == "200":
                            if "headers" not in response_info:
                                response_info["headers"] = {}
                            
                            response_info["headers"].update({
                                "X-RateLimit-Remaining": {
                                    "schema": {"type": "integer"},
                                    "description": "Requests remaining in current window"
                                },
                                "X-RateLimit-Reset": {
                                    "schema": {"type": "integer"},
                                    "description": "Unix timestamp when rate limit resets"
                                }
                            })

    def add_custom_schema(self, name: str, schema: Dict[str, Any]):
        """Add custom schema to the specification."""
        self.custom_schemas[name] = schema
        logger.info(f"Added custom schema: {name}")

    def add_custom_example(self, schema_name: str, example_name: str, example: Dict[str, Any]):
        """Add custom example for a schema."""
        if schema_name not in self.custom_examples:
            self.custom_examples[schema_name] = {}
        
        self.custom_examples[schema_name][example_name] = {
            "summary": example_name.replace("_", " ").title(),
            "value": example
        }
        logger.info(f"Added custom example {example_name} for schema {schema_name}")

    def export_specification(
        self, 
        spec: Dict[str, Any], 
        format_type: DocumentationFormat = DocumentationFormat.JSON,
        output_file: Optional[str] = None
    ) -> str:
        """Export OpenAPI specification to different formats."""
        if format_type == DocumentationFormat.JSON:
            content = json.dumps(spec, indent=2, ensure_ascii=False)
        elif format_type == DocumentationFormat.YAML:
            content = yaml.dump(spec, default_flow_style=False, allow_unicode=True)
        elif format_type == DocumentationFormat.HTML:
            content = self._generate_html_documentation(spec)
        else:
            raise ValueError(f"Unsupported format: {format_type}")

        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Exported specification to {output_file}")

        return content

    def _generate_html_documentation(self, spec: Dict[str, Any]) -> str:
        """Generate HTML documentation from OpenAPI spec."""
        # Simple HTML template with embedded Swagger UI
        html_template = f"""
<!DOCTYPE html>
<html>
<head>
    <title>{spec['info']['title']} - API Documentation</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@3.52.5/swagger-ui.css" />
    <style>
        html {{
            box-sizing: border-box;
            overflow: -moz-scrollbars-vertical;
            overflow-y: scroll;
        }}
        *, *:before, *:after {{
            box-sizing: inherit;
        }}
        body {{
            margin:0;
            background: #fafafa;
        }}
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@3.52.5/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@3.52.5/swagger-ui-standalone-preset.js"></script>
    <script>
        window.onload = function() {{
            const ui = SwaggerUIBundle({{
                url: 'data:application/json;base64,' + btoa(JSON.stringify({json.dumps(spec)})),
                dom_id: '#swagger-ui',
                deepLinking: true,
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIStandalonePreset
                ],
                plugins: [
                    SwaggerUIBundle.plugins.DownloadUrl
                ],
                layout: "StandaloneLayout"
            }});
        }};
    </script>
</body>
</html>
        """
        return html_template

    def generate_client_code(
        self, 
        spec: Dict[str, Any], 
        language: str = "python",
        output_dir: Optional[str] = None
    ) -> Dict[str, str]:
        """Generate client code from OpenAPI specification."""
        # This is a simplified example - in practice you'd use tools like
        # openapi-generator or swagger-codegen
        
        if language.lower() == "python":
            return self._generate_python_client(spec)
        elif language.lower() == "javascript":
            return self._generate_javascript_client(spec)
        else:
            raise ValueError(f"Unsupported language: {language}")

    def _generate_python_client(self, spec: Dict[str, Any]) -> Dict[str, str]:
        """Generate Python client code."""
        client_code = f'''
"""
{spec['info']['title']} Python Client
Generated from OpenAPI specification
"""
import requests
from typing import Dict, List, Optional, Any
import json

class {spec['info']['title'].replace(' ', '')}Client:
    """Python client for {spec['info']['title']}."""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None, jwt_token: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        
        if jwt_token:
            self.session.headers.update({{"Authorization": f"Bearer {{jwt_token}}"}})
        elif api_key:
            self.session.headers.update({{"X-API-Key": api_key}})
    
    def create_chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """Create a chat completion."""
        data = {{"messages": messages, **kwargs}}
        response = self.session.post(f"{{self.base_url}}/api/v1/chat/completions", json=data)
        response.raise_for_status()
        return response.json()
    
    def list_models(self) -> Dict[str, Any]:
        """List available models."""
        response = self.session.get(f"{{self.base_url}}/api/v1/models")
        response.raise_for_status()
        return response.json()
    
    def health_check(self) -> Dict[str, Any]:
        """Check API health."""
        response = self.session.get(f"{{self.base_url}}/health")
        response.raise_for_status()
        return response.json()
'''
        
        return {"client.py": client_code}

    def _generate_javascript_client(self, spec: Dict[str, Any]) -> Dict[str, str]:
        """Generate JavaScript client code."""
        client_code = f'''
/**
 * {spec['info']['title']} JavaScript Client
 * Generated from OpenAPI specification
 */

class {spec['info']['title'].replace(' ', '')}Client {{
    constructor(baseUrl, options = {{}}) {{
        this.baseUrl = baseUrl.replace(/\/$/, '');
        this.apiKey = options.apiKey;
        this.jwtToken = options.jwtToken;
    }}

    async _request(method, path, data = null) {{
        const headers = {{
            'Content-Type': 'application/json'
        }};

        if (this.jwtToken) {{
            headers['Authorization'] = `Bearer ${{this.jwtToken}}`;
        }} else if (this.apiKey) {{
            headers['X-API-Key'] = this.apiKey;
        }}

        const config = {{
            method,
            headers,
            body: data ? JSON.stringify(data) : null
        }};

        const response = await fetch(`${{this.baseUrl}}${{path}}`, config);
        
        if (!response.ok) {{
            throw new Error(`HTTP error! status: ${{response.status}}`);
        }}

        return response.json();
    }}

    async createChatCompletion(messages, options = {{}}) {{
        const data = {{ messages, ...options }};
        return this._request('POST', '/api/v1/chat/completions', data);
    }}

    async listModels() {{
        return this._request('GET', '/api/v1/models');
    }}

    async healthCheck() {{
        return this._request('GET', '/health');
    }}
}}

module.exports = {spec['info']['title'].replace(' ', '')}Client;
'''
        
        return {"client.js": client_code}

# Factory function
def create_openapi_generator(config: APIDocumentationConfig = None) -> OpenAPIGenerator:
    """Create OpenAPI documentation generator."""
    return OpenAPIGenerator(config)