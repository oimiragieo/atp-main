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
API Versioning and Backward Compatibility Management
This module provides comprehensive API versioning capabilities including:
- Semantic versioning support
- Backward compatibility management
- Request/response transformation
- Deprecation management
- Migration assistance
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, asdict
from enum import Enum
import re
from packaging import version
from fastapi import Request, Response
from fastapi.responses import JSONResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VersioningStrategy(Enum):
    """API versioning strategies."""
    URL_PATH = "url_path"  # /api/v1/endpoint
    HEADER = "header"      # Accept: application/vnd.api+json;version=1
    QUERY_PARAM = "query_param"  # ?version=1
    CONTENT_TYPE = "content_type"  # Content-Type: application/vnd.api.v1+json

class CompatibilityLevel(Enum):
    """Backward compatibility levels."""
    BREAKING = "breaking"      # Breaking changes
    COMPATIBLE = "compatible"  # Backward compatible
    DEPRECATED = "deprecated"  # Deprecated but compatible

@dataclass
class APIVersion:
    """API version information."""
    version: str
    release_date: datetime
    status: str  # "stable", "beta", "alpha", "deprecated", "sunset"
    compatibility_level: CompatibilityLevel
    breaking_changes: List[str] = None
    deprecations: List[str] = None
    sunset_date: Optional[datetime] = None
    migration_guide_url: Optional[str] = None

    def __post_init__(self):
        if self.breaking_changes is None:
            self.breaking_changes = []
        if self.deprecations is None:
            self.deprecations = []

    @property
    def is_supported(self) -> bool:
        """Check if version is still supported."""
        if self.status == "sunset":
            return False
        if self.sunset_date and datetime.now(timezone.utc) > self.sunset_date:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["compatibility_level"] = self.compatibility_level.value
        result["release_date"] = self.release_date.isoformat()
        if self.sunset_date:
            result["sunset_date"] = self.sunset_date.isoformat()
        return result

@dataclass
class TransformationRule:
    """Request/response transformation rule."""
    rule_id: str
    name: str
    source_version: str
    target_version: str
    transformation_type: str  # "request", "response", "both"
    field_mappings: Dict[str, str] = None
    custom_transformer: Optional[str] = None
    enabled: bool = True

    def __post_init__(self):
        if self.field_mappings is None:
            self.field_mappings = {}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class DeprecationNotice:
    """Deprecation notice for API features."""
    feature_id: str
    feature_name: str
    deprecated_in_version: str
    removal_version: str
    deprecation_date: datetime
    removal_date: datetime
    reason: str
    replacement: Optional[str] = None
    migration_guide: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["deprecation_date"] = self.deprecation_date.isoformat()
        result["removal_date"] = self.removal_date.isoformat()
        return result

class APIVersionManager:
    """API version management system."""

    def __init__(self, default_version: str = "1.0.0"):
        self.default_version = default_version
        self.versions: Dict[str, APIVersion] = {}
        self.transformation_rules: Dict[str, TransformationRule] = {}
        self.deprecation_notices: Dict[str, DeprecationNotice] = {}
        self.custom_transformers: Dict[str, Callable] = {}
        
        # Initialize default versions
        self._initialize_default_versions()

    def _initialize_default_versions(self):
        """Initialize default API versions."""
        # Version 1.0.0 - Initial stable release
        v1 = APIVersion(
            version="1.0.0",
            release_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            status="stable",
            compatibility_level=CompatibilityLevel.COMPATIBLE
        )
        self.versions["1.0.0"] = v1

        # Version 1.1.0 - Minor update with new features
        v1_1 = APIVersion(
            version="1.1.0",
            release_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            status="stable",
            compatibility_level=CompatibilityLevel.COMPATIBLE,
            deprecations=["legacy_auth_method"]
        )
        self.versions["1.1.0"] = v1_1

        # Version 2.0.0 - Major update with breaking changes
        v2 = APIVersion(
            version="2.0.0",
            release_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            status="stable",
            compatibility_level=CompatibilityLevel.BREAKING,
            breaking_changes=[
                "Changed authentication from API key to JWT",
                "Renamed 'completions' endpoint to 'generate'",
                "Modified response format for streaming endpoints"
            ]
        )
        self.versions["2.0.0"] = v2

        # Version 2.1.0 - Current beta
        v2_1 = APIVersion(
            version="2.1.0",
            release_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
            status="beta",
            compatibility_level=CompatibilityLevel.COMPATIBLE
        )
        self.versions["2.1.0"] = v2_1

        # Add transformation rules
        self._initialize_transformation_rules()

    def _initialize_transformation_rules(self):
        """Initialize default transformation rules."""
        # Transform v1 completions to v2 generate
        completions_rule = TransformationRule(
            rule_id="v1_to_v2_completions",
            name="Transform completions endpoint",
            source_version="1.0.0",
            target_version="2.0.0",
            transformation_type="both",
            field_mappings={
                "prompt": "input",
                "max_tokens": "max_length",
                "temperature": "temperature",
                "top_p": "top_p"
            }
        )
        self.transformation_rules[completions_rule.rule_id] = completions_rule

        # Transform v1 auth to v2 auth
        auth_rule = TransformationRule(
            rule_id="v1_to_v2_auth",
            name="Transform authentication",
            source_version="1.0.0",
            target_version="2.0.0",
            transformation_type="request",
            custom_transformer="transform_auth_v1_to_v2"
        )
        self.transformation_rules[auth_rule.rule_id] = auth_rule

        # Register custom transformers
        self.custom_transformers["transform_auth_v1_to_v2"] = self._transform_auth_v1_to_v2

    def add_version(self, api_version: APIVersion):
        """Add a new API version."""
        self.versions[api_version.version] = api_version
        logger.info(f"Added API version {api_version.version}")

    def deprecate_version(
        self, 
        version_str: str, 
        sunset_date: datetime,
        migration_guide_url: Optional[str] = None
    ):
        """Deprecate an API version."""
        if version_str in self.versions:
            api_version = self.versions[version_str]
            api_version.status = "deprecated"
            api_version.sunset_date = sunset_date
            api_version.migration_guide_url = migration_guide_url
            logger.info(f"Deprecated API version {version_str}, sunset date: {sunset_date}")

    def sunset_version(self, version_str: str):
        """Sunset an API version (no longer supported)."""
        if version_str in self.versions:
            api_version = self.versions[version_str]
            api_version.status = "sunset"
            logger.info(f"Sunset API version {version_str}")

    def get_version_info(self, version_str: str) -> Optional[APIVersion]:
        """Get information about a specific version."""
        return self.versions.get(version_str)

    def list_versions(self, include_sunset: bool = False) -> List[APIVersion]:
        """List all API versions."""
        versions = []
        for api_version in self.versions.values():
            if include_sunset or api_version.is_supported:
                versions.append(api_version)
        
        # Sort by version number
        versions.sort(key=lambda v: version.parse(v.version), reverse=True)
        return versions

    def get_latest_version(self, status: Optional[str] = None) -> Optional[APIVersion]:
        """Get the latest API version."""
        versions = self.list_versions()
        if status:
            versions = [v for v in versions if v.status == status]
        return versions[0] if versions else None

    def extract_version_from_request(
        self, 
        request: Request, 
        strategy: VersioningStrategy = VersioningStrategy.URL_PATH
    ) -> str:
        """Extract API version from request."""
        if strategy == VersioningStrategy.URL_PATH:
            # Extract from URL path like /api/v1/endpoint or /api/v2.1/endpoint
            path = request.url.path
            match = re.search(r'/api/v?(\d+(?:\.\d+)*)', path)
            if match:
                version_str = match.group(1)
                # Convert short version to full version
                if version_str == "1":
                    return "1.0.0"
                elif version_str == "2":
                    return "2.0.0"
                else:
                    return version_str
        elif strategy == VersioningStrategy.HEADER:
            # Extract from Accept header
            accept_header = request.headers.get("Accept", "")
            match = re.search(r'version=(\d+(?:\.\d+)*)', accept_header)
            if match:
                return match.group(1)
        elif strategy == VersioningStrategy.QUERY_PARAM:
            # Extract from query parameter
            version_param = request.query_params.get("version")
            if version_param:
                return version_param
        elif strategy == VersioningStrategy.CONTENT_TYPE:
            # Extract from Content-Type header
            content_type = request.headers.get("Content-Type", "")
            match = re.search(r'\.v(\d+(?:\.\d+)*)\+', content_type)
            if match:
                return match.group(1)

        # Return default version if not found
        return self.default_version

    def is_version_supported(self, version_str: str) -> bool:
        """Check if a version is supported."""
        api_version = self.versions.get(version_str)
        return api_version.is_supported if api_version else False

    def get_compatibility_info(
        self, 
        source_version: str, 
        target_version: str
    ) -> Dict[str, Any]:
        """Get compatibility information between versions."""
        source_ver = self.versions.get(source_version)
        target_ver = self.versions.get(target_version)
        
        if not source_ver or not target_ver:
            return {"error": "Version not found"}

        # Compare versions
        source_parsed = version.parse(source_version)
        target_parsed = version.parse(target_version)

        compatibility_info = {
            "source_version": source_version,
            "target_version": target_version,
            "is_compatible": True,
            "compatibility_level": "compatible",
            "breaking_changes": [],
            "deprecations": [],
            "transformation_required": False,
            "available_transformations": []
        }

        if source_parsed.major != target_parsed.major:
            compatibility_info["is_compatible"] = False
            compatibility_info["compatibility_level"] = "breaking"
            compatibility_info["breaking_changes"] = target_ver.breaking_changes
            compatibility_info["transformation_required"] = True

        # Find available transformation rules
        for rule in self.transformation_rules.values():
            if rule.source_version == source_version and rule.target_version == target_version:
                compatibility_info["available_transformations"].append(rule.rule_id)

        return compatibility_info

    async def transform_request(
        self, 
        request_data: Dict[str, Any],
        source_version: str,
        target_version: str,
        endpoint: str
    ) -> Dict[str, Any]:
        """Transform request data between versions."""
        # Find applicable transformation rules
        applicable_rules = [
            rule for rule in self.transformation_rules.values()
            if (rule.source_version == source_version and 
                rule.target_version == target_version and
                rule.transformation_type in ["request", "both"])
        ]

        transformed_data = request_data.copy()

        for rule in applicable_rules:
            if rule.custom_transformer and rule.custom_transformer in self.custom_transformers:
                # Apply custom transformer
                transformer = self.custom_transformers[rule.custom_transformer]
                transformed_data = await transformer(transformed_data, "request", endpoint)
            else:
                # Apply field mappings
                transformed_data = self._apply_field_mappings(
                    transformed_data, rule.field_mappings
                )

        return transformed_data

    async def transform_response(
        self, 
        response_data: Dict[str, Any],
        source_version: str,
        target_version: str,
        endpoint: str
    ) -> Dict[str, Any]:
        """Transform response data between versions."""
        # Find applicable transformation rules
        applicable_rules = [
            rule for rule in self.transformation_rules.values()
            if (rule.source_version == target_version and  # Note: reversed for response
                rule.target_version == source_version and
                rule.transformation_type in ["response", "both"])
        ]

        transformed_data = response_data.copy()

        for rule in applicable_rules:
            if rule.custom_transformer and rule.custom_transformer in self.custom_transformers:
                # Apply custom transformer
                transformer = self.custom_transformers[rule.custom_transformer]
                transformed_data = await transformer(transformed_data, "response", endpoint)
            else:
                # Apply reverse field mappings for response
                reverse_mappings = {v: k for k, v in rule.field_mappings.items()}
                transformed_data = self._apply_field_mappings(
                    transformed_data, reverse_mappings
                )

        return transformed_data

    def _apply_field_mappings(
        self, 
        data: Dict[str, Any], 
        mappings: Dict[str, str]
    ) -> Dict[str, Any]:
        """Apply field mappings to data."""
        transformed = {}
        for key, value in data.items():
            # Check if field should be mapped
            if key in mappings:
                new_key = mappings[key]
                transformed[new_key] = value
            else:
                transformed[key] = value
        return transformed

    async def _transform_auth_v1_to_v2(
        self, 
        data: Dict[str, Any], 
        transform_type: str,
        endpoint: str
    ) -> Dict[str, Any]:
        """Custom transformer for authentication v1 to v2."""
        if transform_type == "request":
            # Transform API key to JWT format expectation
            if "api_key" in data:
                # In practice, you'd convert API key to JWT or handle differently
                data["authorization"] = f"Bearer {data.pop('api_key')}"
        return data

    def add_transformation_rule(self, rule: TransformationRule):
        """Add a transformation rule."""
        self.transformation_rules[rule.rule_id] = rule
        logger.info(f"Added transformation rule: {rule.name}")

    def add_custom_transformer(self, name: str, transformer: Callable):
        """Add a custom transformer function."""
        self.custom_transformers[name] = transformer
        logger.info(f"Added custom transformer: {name}")

    def add_deprecation_notice(self, notice: DeprecationNotice):
        """Add a deprecation notice."""
        self.deprecation_notices[notice.feature_id] = notice
        logger.info(f"Added deprecation notice for: {notice.feature_name}")

    def get_deprecation_notices(
        self, 
        version_str: Optional[str] = None
    ) -> List[DeprecationNotice]:
        """Get deprecation notices."""
        notices = list(self.deprecation_notices.values())
        if version_str:
            notices = [
                notice for notice in notices
                if notice.deprecated_in_version == version_str
            ]
        return notices

    def generate_migration_guide(
        self, 
        source_version: str, 
        target_version: str
    ) -> Dict[str, Any]:
        """Generate migration guide between versions."""
        compatibility_info = self.get_compatibility_info(source_version, target_version)
        
        migration_guide = {
            "source_version": source_version,
            "target_version": target_version,
            "migration_complexity": "low",
            "estimated_effort": "1-2 hours",
            "breaking_changes": compatibility_info.get("breaking_changes", []),
            "deprecations": compatibility_info.get("deprecations", []),
            "steps": [],
            "code_examples": {},
            "testing_recommendations": []
        }

        # Determine migration complexity
        if compatibility_info["compatibility_level"] == "breaking":
            migration_guide["migration_complexity"] = "high"
            migration_guide["estimated_effort"] = "1-2 weeks"
        elif len(compatibility_info.get("deprecations", [])) > 0:
            migration_guide["migration_complexity"] = "medium"
            migration_guide["estimated_effort"] = "2-5 days"

        # Add migration steps
        if compatibility_info["transformation_required"]:
            migration_guide["steps"].extend([
                "1. Review breaking changes and deprecations",
                "2. Update authentication method if required",
                "3. Update endpoint URLs and request formats",
                "4. Test with new API version",
                "5. Update error handling for new response formats",
                "6. Deploy and monitor"
            ])
        else:
            migration_guide["steps"].extend([
                "1. Update API version in requests",
                "2. Test existing functionality",
                "3. Deploy and monitor"
            ])

        # Add code examples
        if source_version == "1.0.0" and target_version == "2.0.0":
            migration_guide["code_examples"] = {
                "authentication": {
                    "v1": "headers = {'X-API-Key': 'your-api-key'}",
                    "v2": "headers = {'Authorization': 'Bearer your-jwt-token'}"
                },
                "completions": {
                    "v1": "POST /api/v1/completions {'prompt': 'Hello', 'max_tokens': 100}",
                    "v2": "POST /api/v2/generate {'input': 'Hello', 'max_length': 100}"
                }
            }

        # Add testing recommendations
        migration_guide["testing_recommendations"] = [
            "Test all critical API endpoints with new version",
            "Verify authentication works correctly",
            "Check error handling and response formats",
            "Performance test with expected load",
            "Test backward compatibility if supporting multiple versions"
        ]

        return migration_guide

    def get_version_headers(self, version_str: str) -> Dict[str, str]:
        """Get appropriate headers for API version."""
        headers = {}
        
        api_version = self.versions.get(version_str)
        if not api_version:
            return headers

        # Add version information
        headers["X-API-Version"] = version_str
        
        # Add deprecation warnings
        if api_version.status == "deprecated":
            headers["X-API-Deprecated"] = "true"
            if api_version.sunset_date:
                headers["X-API-Sunset-Date"] = api_version.sunset_date.isoformat()
            if api_version.migration_guide_url:
                headers["X-API-Migration-Guide"] = api_version.migration_guide_url

        # Add compatibility information
        headers["X-API-Compatibility-Level"] = api_version.compatibility_level.value

        return headers

    def validate_version_request(self, version_str: str) -> Dict[str, Any]:
        """Validate if a version request is valid."""
        result = {
            "valid": False,
            "version": version_str,
            "message": "",
            "supported": False,
            "deprecated": False,
            "sunset": False
        }

        api_version = self.versions.get(version_str)
        if not api_version:
            result["message"] = f"Version {version_str} not found"
            return result

        result["valid"] = True
        result["supported"] = api_version.is_supported
        result["deprecated"] = api_version.status == "deprecated"
        result["sunset"] = api_version.status == "sunset"

        if not api_version.is_supported:
            if api_version.status == "sunset":
                result["message"] = f"Version {version_str} is no longer supported"
            elif api_version.sunset_date and datetime.now(timezone.utc) > api_version.sunset_date:
                result["message"] = f"Version {version_str} has been sunset"
            else:
                result["message"] = f"Version {version_str} is not supported"
        elif api_version.status == "deprecated":
            result["message"] = f"Version {version_str} is deprecated"
            if api_version.sunset_date:
                result["message"] += f" and will be sunset on {api_version.sunset_date.date()}"
        else:
            result["message"] = f"Version {version_str} is supported"

        return result

# Middleware for FastAPI integration
class APIVersioningMiddleware:
    """FastAPI middleware for API versioning."""
    
    def __init__(
        self, 
        version_manager: APIVersionManager,
        strategy: VersioningStrategy = VersioningStrategy.URL_PATH,
        auto_transform: bool = True
    ):
        self.version_manager = version_manager
        self.strategy = strategy
        self.auto_transform = auto_transform

    async def __call__(self, request: Request, call_next):
        """Process request with versioning support."""
        # Extract version from request
        requested_version = self.version_manager.extract_version_from_request(
            request, self.strategy
        )

        # Validate version
        validation_result = self.version_manager.validate_version_request(requested_version)
        
        if not validation_result["valid"]:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid API version",
                    "message": validation_result["message"],
                    "supported_versions": [v.version for v in self.version_manager.list_versions()]
                }
            )

        if not validation_result["supported"]:
            return JSONResponse(
                status_code=410,  # Gone
                content={
                    "error": "API version not supported",
                    "message": validation_result["message"],
                    "supported_versions": [v.version for v in self.version_manager.list_versions()]
                }
            )

        # Add version information to request state
        request.state.api_version = requested_version
        request.state.version_info = self.version_manager.get_version_info(requested_version)

        # Process request
        response = await call_next(request)

        # Add version headers
        version_headers = self.version_manager.get_version_headers(requested_version)
        for key, value in version_headers.items():
            response.headers[key] = value

        return response

# Factory function
def create_version_manager(default_version: str = "1.0.0") -> APIVersionManager:
    """Create API version manager."""
    return APIVersionManager(default_version)