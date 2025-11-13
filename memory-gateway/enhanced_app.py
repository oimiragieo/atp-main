"""
Enhanced ATP Memory Gateway Service with Advanced PII Detection

This enhanced version integrates the advanced PII detection and redaction system
into the memory gateway, providing automatic PII protection for stored data.
"""

import logging
import os
import sys
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel

# Import from parent directory
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Import existing memory gateway components
from .app import (
    STORE,
    _audit_event,
    _record_access,
    validate_consistency_level,
    validate_key,
    validate_namespace,
    validate_request_size,
    validate_tenant_id,
)

# Import advanced PII system
try:
    from .advanced_pii import AdvancedPIISystem, DataClassification, PIIMatch

    ADVANCED_PII_AVAILABLE = True
except ImportError:
    ADVANCED_PII_AVAILABLE = False
    logging.warning("Advanced PII system not available. Falling back to basic PII detection.")

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Initialize advanced PII system
if ADVANCED_PII_AVAILABLE:
    pii_system = AdvancedPIISystem()
    logger.info("Advanced PII system initialized")
else:
    pii_system = None

app = FastAPI(
    title="Enhanced ATP Memory Gateway",
    description="Central memory fabric service with advanced PII protection",
    version="2.0.0",
)


class Obj(BaseModel):
    object: Any


class PIIDetectionRequest(BaseModel):
    text: str
    data_classification: str = "confidential"
    return_matches: bool = False


class PIIRedactionRequest(BaseModel):
    text: str
    data_classification: str = "confidential"
    tenant_id: str | None = None
    user_id: str | None = None


class DataSubjectRequest(BaseModel):
    subject_identifier: str
    request_type: str  # "export" or "delete"


def _get_data_classification(x_tenant_id: str, ns: str) -> DataClassification:
    """Determine data classification based on tenant and namespace"""
    # This is a simplified classification logic
    # In production, this would be based on tenant configuration and namespace policies

    if ns.startswith("public_"):
        return DataClassification.PUBLIC
    elif ns.startswith("internal_"):
        return DataClassification.INTERNAL
    elif ns.startswith("restricted_"):
        return DataClassification.RESTRICTED
    elif ns.startswith("secret_"):
        return DataClassification.TOP_SECRET
    else:
        return DataClassification.CONFIDENTIAL


def _process_data_for_storage(
    data: Any, tenant_id: str, namespace: str, key: str, user_id: str | None = None
) -> tuple[Any, list[PIIMatch], str | None]:
    """Process data for storage with PII detection and redaction"""

    if not ADVANCED_PII_AVAILABLE or pii_system is None:
        return data, [], None

    # Convert data to string for PII processing
    if isinstance(data, str):
        text_data = data
    else:
        text_data = str(data)

    # Determine data classification
    classification = _get_data_classification(tenant_id, namespace)

    # Process with PII system
    try:
        redacted_data, pii_matches, audit_entry = pii_system.process_text(
            text_data,
            classification,
            tenant_id=tenant_id,
            user_id=user_id,
            request_id=f"{namespace}:{key}",
            return_matches=True,
        )

        # If original data was not string, try to preserve structure
        if not isinstance(data, str):
            try:
                # For JSON-like objects, use the object redaction
                from .advanced_pii import redact_object

                redacted_data = redact_object(data, classification)
            except:
                # Fallback to string redaction
                pass

        audit_id = audit_entry.id if audit_entry else None
        return redacted_data, pii_matches, audit_id

    except Exception as e:
        logger.error(f"Error processing PII for {namespace}:{key}: {e}")
        return data, [], None


@app.put("/v1/memory/{ns}/{key}")
def put_with_pii_protection(
    ns: str,
    key: str,
    body: Obj,
    request: Request,
    x_tenant_id: str = Header(..., alias="x-tenant-id"),
    x_user_id: str | None = Header(None, alias="x-user-id"),
    x_disable_pii_protection: bool = Header(False, alias="x-disable-pii-protection"),
) -> dict[str, Any]:
    """Store memory object with PII protection"""

    # Validate inputs
    ns = validate_namespace(ns)
    key = validate_key(key)
    x_tenant_id = validate_tenant_id(x_tenant_id)
    validate_request_size(body.object)

    # Process data for PII protection
    if x_disable_pii_protection:
        # Store original data without PII protection
        processed_data = body.object
        pii_matches = []
        audit_id = None
        logger.info(f"PII protection disabled for {ns}:{key}")
    else:
        processed_data, pii_matches, audit_id = _process_data_for_storage(body.object, x_tenant_id, ns, key, x_user_id)

    # Store the processed data
    STORE.setdefault(ns, {})[key] = processed_data

    # Record access and audit
    _record_access(x_tenant_id, ns, "PUT", key)

    audit_data = {
        "size": len(str(processed_data)),
        "pii_matches_found": len(pii_matches),
        "pii_audit_id": audit_id,
        "pii_protection_enabled": not x_disable_pii_protection,
    }

    if pii_matches:
        audit_data["pii_types"] = list({match.pii_type.value for match in pii_matches})

    _audit_event("memory_put_with_pii", x_tenant_id, ns, key, audit_data)

    # Return response with PII information
    response = {"ok": True}

    if pii_matches:
        response["pii_detected"] = True
        response["pii_matches_count"] = len(pii_matches)
        response["pii_types"] = list({match.pii_type.value for match in pii_matches})
        if audit_id:
            response["pii_audit_id"] = audit_id
    else:
        response["pii_detected"] = False

    return response


@app.get("/v1/memory/{ns}/{key}", response_model=dict[str, Any])
def get_with_metadata(
    ns: str,
    key: str,
    request: Request,
    x_session_id: str | None = Header(None, alias="x-session-id"),
    x_consistency_level: str = Header("EVENTUAL", alias="x-consistency-level"),
    x_tenant_id: str = Header(..., alias="x-tenant-id"),
    include_pii_metadata: bool = Query(False, description="Include PII detection metadata"),
) -> dict[str, Any]:
    """Get memory object with optional PII metadata"""

    # Validate inputs
    ns = validate_namespace(ns)
    key = validate_key(key)
    x_tenant_id = validate_tenant_id(x_tenant_id)
    x_consistency_level = validate_consistency_level(x_consistency_level)

    # Get object from store
    obj = STORE.get(ns, {}).get(key)
    if obj is None:
        _record_access(x_tenant_id, ns, "GET_NOT_FOUND", key)
        _audit_event("memory_get_not_found", x_tenant_id, ns, key)
        return {"error": "not_found"}

    _record_access(x_tenant_id, ns, "GET", key)
    _audit_event("memory_get", x_tenant_id, ns, key, {"size": len(str(obj))})

    response = {"object": obj}

    # Add PII metadata if requested
    if include_pii_metadata and ADVANCED_PII_AVAILABLE and pii_system:
        try:
            # Analyze current object for PII (without redaction)
            text_data = str(obj) if not isinstance(obj, str) else obj
            matches = pii_system.detector.detect_pii(text_data)

            if matches:
                response["pii_metadata"] = {
                    "pii_detected": True,
                    "pii_matches_count": len(matches),
                    "pii_types": list({match.pii_type.value for match in matches}),
                    "matches": [
                        {
                            "type": match.pii_type.value,
                            "start": match.start,
                            "end": match.end,
                            "confidence": match.confidence,
                            "method": match.detection_method,
                        }
                        for match in matches
                    ],
                }
            else:
                response["pii_metadata"] = {"pii_detected": False}

        except Exception as e:
            logger.error(f"Error analyzing PII metadata for {ns}:{key}: {e}")
            response["pii_metadata"] = {"error": "pii_analysis_failed"}

    return response


# PII Management Endpoints


@app.post("/v1/pii/detect")
def detect_pii_endpoint(
    request: PIIDetectionRequest, x_tenant_id: str = Header(..., alias="x-tenant-id")
) -> dict[str, Any]:
    """Detect PII in provided text"""

    if not ADVANCED_PII_AVAILABLE or pii_system is None:
        raise HTTPException(status_code=503, detail="Advanced PII system not available")

    try:
        classification = DataClassification(request.data_classification)

        if request.return_matches:
            redacted_text, matches, audit_entry = pii_system.process_text(
                request.text, classification, tenant_id=x_tenant_id, return_matches=True
            )

            return {
                "pii_detected": len(matches) > 0,
                "matches_count": len(matches),
                "matches": [
                    {
                        "type": match.pii_type.value,
                        "text": match.text,
                        "start": match.start,
                        "end": match.end,
                        "confidence": match.confidence,
                        "method": match.detection_method,
                        "context": match.context,
                    }
                    for match in matches
                ],
                "redacted_text": redacted_text,
                "audit_id": audit_entry.id if audit_entry else None,
            }
        else:
            matches = pii_system.detector.detect_pii(request.text)
            return {
                "pii_detected": len(matches) > 0,
                "matches_count": len(matches),
                "pii_types": list({match.pii_type.value for match in matches}),
            }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid data classification: {e}")
    except Exception as e:
        logger.error(f"Error in PII detection: {e}")
        raise HTTPException(status_code=500, detail="PII detection failed")


@app.post("/v1/pii/redact")
def redact_pii_endpoint(
    request: PIIRedactionRequest, x_tenant_id: str = Header(..., alias="x-tenant-id")
) -> dict[str, Any]:
    """Redact PII from provided text"""

    if not ADVANCED_PII_AVAILABLE or pii_system is None:
        raise HTTPException(status_code=503, detail="Advanced PII system not available")

    try:
        classification = DataClassification(request.data_classification)

        redacted_text, matches, audit_entry = pii_system.process_text(
            request.text,
            classification,
            tenant_id=request.tenant_id or x_tenant_id,
            user_id=request.user_id,
            return_matches=True,
        )

        return {
            "redacted_text": redacted_text,
            "pii_detected": len(matches) > 0,
            "matches_count": len(matches),
            "pii_types": list({match.pii_type.value for match in matches}),
            "audit_id": audit_entry.id if audit_entry else None,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid data classification: {e}")
    except Exception as e:
        logger.error(f"Error in PII redaction: {e}")
        raise HTTPException(status_code=500, detail="PII redaction failed")


@app.get("/v1/pii/audit")
def get_pii_audit_trail(
    x_tenant_id: str = Header(..., alias="x-tenant-id"),
    days: int = Query(7, description="Number of days to look back"),
    limit: int = Query(100, description="Maximum number of entries to return"),
) -> dict[str, Any]:
    """Get PII audit trail for tenant"""

    if not ADVANCED_PII_AVAILABLE or pii_system is None:
        raise HTTPException(status_code=503, detail="Advanced PII system not available")

    try:
        from datetime import timedelta

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        entries = pii_system.get_audit_trail(tenant_id=x_tenant_id, start_date=start_date, end_date=end_date)

        # Limit results
        if len(entries) > limit:
            entries = entries[:limit]

        return {
            "query": {
                "tenant_id": x_tenant_id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days,
                "limit": limit,
            },
            "entries_found": len(entries),
            "entries": entries,
        }

    except Exception as e:
        logger.error(f"Error retrieving PII audit trail: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve audit trail")


@app.post("/v1/pii/data-subject-request")
def handle_data_subject_request(
    request: DataSubjectRequest, x_tenant_id: str = Header(..., alias="x-tenant-id")
) -> dict[str, Any]:
    """Handle GDPR/CCPA data subject requests"""

    if not ADVANCED_PII_AVAILABLE or pii_system is None:
        raise HTTPException(status_code=503, detail="Advanced PII system not available")

    if request.request_type not in ["export", "delete"]:
        raise HTTPException(status_code=400, detail="Invalid request type. Must be 'export' or 'delete'")

    try:
        result = pii_system.handle_data_subject_request(request.subject_identifier, request.request_type)

        # Add tenant context
        result["tenant_id"] = x_tenant_id
        result["processed_at"] = datetime.now().isoformat()

        return result

    except Exception as e:
        logger.error(f"Error handling data subject request: {e}")
        raise HTTPException(status_code=500, detail="Failed to process data subject request")


# Health and Status Endpoints


@app.get("/v1/pii/health")
def pii_system_health() -> dict[str, Any]:
    """Get PII system health status"""

    if not ADVANCED_PII_AVAILABLE:
        return {
            "status": "unavailable",
            "message": "Advanced PII system not installed",
            "features": {
                "rule_based_detection": False,
                "ml_based_detection": False,
                "audit_trail": False,
                "data_subject_requests": False,
            },
        }

    if pii_system is None:
        return {
            "status": "error",
            "message": "PII system failed to initialize",
            "features": {
                "rule_based_detection": False,
                "ml_based_detection": False,
                "audit_trail": False,
                "data_subject_requests": False,
            },
        }

    # Check system capabilities
    features = {
        "rule_based_detection": pii_system.detector.config.get("enable_rule_detection", True),
        "ml_based_detection": pii_system.detector.config.get("enable_ml_detection", True)
        and bool(pii_system.detector.ml_models),
        "audit_trail": True,
        "data_subject_requests": True,
    }

    return {
        "status": "healthy",
        "message": "PII system operational",
        "features": features,
        "ml_models_loaded": len(pii_system.detector.ml_models),
        "custom_patterns": sum(len(patterns) for patterns in pii_system.detector.custom_patterns.values()),
        "audit_entries": len(pii_system.redactor.audit_trail),
    }


@app.get("/v1/pii/config")
def get_pii_config(x_tenant_id: str = Header(..., alias="x-tenant-id")) -> dict[str, Any]:
    """Get PII system configuration (sanitized)"""

    if not ADVANCED_PII_AVAILABLE or pii_system is None:
        raise HTTPException(status_code=503, detail="Advanced PII system not available")

    # Return sanitized configuration (no sensitive data)
    config = pii_system.detector.config.copy()

    # Remove sensitive configuration
    sensitive_keys = ["api_keys", "secrets", "credentials"]
    for key in sensitive_keys:
        config.pop(key, None)

    return {
        "tenant_id": x_tenant_id,
        "config": config,
        "policies_count": len(pii_system.redactor.policies),
        "custom_patterns_count": sum(len(patterns) for patterns in pii_system.detector.custom_patterns.values()),
    }


# Include all original endpoints from the base app
# This ensures backward compatibility

from .app import app as base_app

# Copy routes from base app (excluding the ones we've overridden)
for route in base_app.routes:
    if hasattr(route, "path"):
        # Skip routes we've already defined
        if route.path in ["/v1/memory/{ns}/{key}"]:
            continue
        app.routes.append(route)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
