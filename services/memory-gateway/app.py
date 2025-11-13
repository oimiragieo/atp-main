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

"""ATP Memory Gateway Service.

A FastAPI-based memory gateway service that provides key-value storage with
audit logging, PII detection, quota management, and adaptive caching.

This service acts as the central memory fabric for the ATP (Autonomous Task Processor)
system, providing reliable storage with observability and security features.
"""

import json
import logging
import os
import re

# Import metrics from the main project
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from metrics.registry import MEMORY_ACCESS_ANOMALIES_TOTAL

from .audit_log import append_event

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="ATP Memory Gateway", description="Central memory fabric service for ATP system", version="1.0.0")
STORE: dict[str, dict[str, Any]] = {}

# Validation constants
MAX_NAMESPACE_LENGTH = 100
MAX_KEY_LENGTH = 200
MAX_TENANT_ID_LENGTH = 50
MAX_REQUEST_SIZE = 1024 * 1024  # 1MB
ALLOWED_CONSISTENCY_LEVELS = {"EVENTUAL", "STRONG"}

# Validation patterns
NAMESPACE_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")
TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_namespace(namespace: str) -> str:
    """Validate namespace parameter.

    Args:
        namespace: The namespace string to validate

    Returns:
        The validated namespace string

    Raises:
        HTTPException: If namespace is invalid
    """
    if not namespace:
        raise HTTPException(status_code=400, detail="Namespace cannot be empty")
    if len(namespace) > MAX_NAMESPACE_LENGTH:
        raise HTTPException(status_code=400, detail=f"Namespace too long (max {MAX_NAMESPACE_LENGTH} characters)")
    if not NAMESPACE_PATTERN.match(namespace):
        raise HTTPException(status_code=400, detail="Namespace contains invalid characters")
    return namespace


def validate_key(key: str) -> str:
    """Validate key parameter.

    Args:
        key: The key string to validate

    Returns:
        The validated key string

    Raises:
        HTTPException: If key is invalid
    """
    if not key:
        raise HTTPException(status_code=400, detail="Key cannot be empty")
    if len(key) > MAX_KEY_LENGTH:
        raise HTTPException(status_code=400, detail=f"Key too long (max {MAX_KEY_LENGTH} characters)")
    if not KEY_PATTERN.match(key):
        raise HTTPException(status_code=400, detail="Key contains invalid characters")
    return key


def validate_tenant_id(tenant_id: str) -> str:
    """Validate tenant ID header.

    Args:
        tenant_id: The tenant ID string to validate

    Returns:
        The validated tenant ID string

    Raises:
        HTTPException: If tenant ID is invalid
    """
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant ID cannot be empty")
    if len(tenant_id) > MAX_TENANT_ID_LENGTH:
        raise HTTPException(status_code=400, detail=f"Tenant ID too long (max {MAX_TENANT_ID_LENGTH} characters)")
    if not TENANT_ID_PATTERN.match(tenant_id):
        raise HTTPException(status_code=400, detail="Tenant ID contains invalid characters")
    return tenant_id


def validate_consistency_level(level: str) -> str:
    """Validate consistency level header.

    Args:
        level: The consistency level string to validate

    Returns:
        The validated consistency level string

    Raises:
        HTTPException: If consistency level is invalid
    """
    if level not in ALLOWED_CONSISTENCY_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid consistency level. Must be one of: {', '.join(ALLOWED_CONSISTENCY_LEVELS)}",
        )
    return level


def validate_request_size(data: Any) -> None:
    """Validate request data size."""
    data_str = str(data)
    if len(data_str.encode("utf-8")) > MAX_REQUEST_SIZE:
        raise HTTPException(status_code=413, detail=f"Request too large (max {MAX_REQUEST_SIZE} bytes)")


# Audit configuration
AUDIT_SECRET = os.getenv("AUDIT_SECRET")
if not AUDIT_SECRET:
    raise ValueError("AUDIT_SECRET environment variable must be set")
AUDIT_SECRET = AUDIT_SECRET.encode()

AUDIT_PATH = os.getenv("AUDIT_PATH", "./memory_audit.log")  # Should be configured in production
PREV_HASH = os.getenv("AUDIT_PREV_HASH")

# Anomaly detection state
NAMESPACE_ACCESS_PATTERNS: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
TENANT_ACCESS_HISTORY: dict[str, list[tuple[str, float]]] = defaultdict(list)
ANOMALY_THRESHOLD = int(os.getenv("ANOMALY_THRESHOLD", "10"))  # Accesses per minute threshold


class Obj(BaseModel):
    object: dict[str, Any]


def _record_access(tenant_id: str, namespace: str, operation: str, key: str = None):
    """Record namespace access for anomaly detection."""
    current_time = time.time()

    # Update access patterns
    NAMESPACE_ACCESS_PATTERNS[tenant_id][namespace] += 1

    # Update access history (keep last 100 accesses per tenant)
    history = TENANT_ACCESS_HISTORY[tenant_id]
    history.append((namespace, current_time))
    if len(history) > 100:
        history.pop(0)

    # Check for anomalies
    recent_accesses = [ns for ns, ts in history if current_time - ts < 60]  # Last minute
    if len(recent_accesses) > ANOMALY_THRESHOLD:
        # Check if this tenant is accessing too many different namespaces
        unique_namespaces = len(set(recent_accesses))
        if unique_namespaces > 5:  # Arbitrary threshold for cross-namespace access
            MEMORY_ACCESS_ANOMALIES_TOTAL.inc(1)
            logger.warning(
                f"ANOMALY DETECTED: Tenant {tenant_id} accessing {unique_namespaces} namespaces in last minute"
            )


def _audit_event(event_type: str, tenant_id: str, namespace: str, key: str = None, details: dict = None):
    """Create audit event with namespace lineage."""
    global PREV_HASH

    event = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "tenant_id": tenant_id,
        "namespace": namespace,
        "key": key,
        "details": details or {},
    }

    try:
        PREV_HASH = append_event(AUDIT_PATH, event, AUDIT_SECRET, PREV_HASH)
    except Exception as e:
        logger.error(f"Audit logging failed: {e}")


@app.get("/healthz")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.put("/v1/memory/{ns}/{key}")
def put(
    ns: str, key: str, body: Obj, request: Request, x_tenant_id: str = Header(..., alias="x-tenant-id")
) -> dict[str, bool]:
    # Validate inputs
    ns = validate_namespace(ns)
    key = validate_key(key)
    x_tenant_id = validate_tenant_id(x_tenant_id)
    validate_request_size(body.object)

    STORE.setdefault(ns, {})[key] = body.object

    _record_access(x_tenant_id, ns, "PUT", key)
    _audit_event("memory_put", x_tenant_id, ns, key, {"size": len(str(body.object))})

    return {"ok": True}


@app.get("/v1/memory/{ns}/{key}", response_model=dict[str, Any])
def get(
    ns: str,
    key: str,
    request: Request,
    x_session_id: str | None = Header(None, alias="x-session-id"),
    x_consistency_level: str = Header("EVENTUAL", alias="x-consistency-level"),
    x_tenant_id: str = Header(..., alias="x-tenant-id"),
) -> dict[str, Any]:
    """Get memory object with consistency level support."""
    # Validate inputs
    ns = validate_namespace(ns)
    key = validate_key(key)
    x_tenant_id = validate_tenant_id(x_tenant_id)
    x_consistency_level = validate_consistency_level(x_consistency_level)

    # For now, just return from store (simulating eventual consistency)
    # In a real implementation, this would route to primary vs replica based on consistency level
    obj = STORE.get(ns, {}).get(key)
    if obj is None:
        _record_access(x_tenant_id, ns, "GET_NOT_FOUND", key)
        _audit_event("memory_get_not_found", x_tenant_id, ns, key)
        return {"error": "not_found"}

    _record_access(x_tenant_id, ns, "GET", key)
    _audit_event("memory_get", x_tenant_id, ns, key, {"size": len(str(obj))})

    return {"object": obj}


# Compliance and audit endpoints
@app.get("/v1/compliance/audit-log")
def get_audit_log(
    start_time: str = Query(None, description="Start time (ISO format)"),
    end_time: str = Query(None, description="End time (ISO format)"),
    tenant_id: str = Query(None, description="Filter by tenant ID"),
    event_type: str = Query(None, description="Filter by event type"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events"),
    x_tenant_id: str = Header(..., alias="x-tenant-id"),
) -> dict[str, Any]:
    """Get audit log entries for compliance reporting."""
    x_tenant_id = validate_tenant_id(x_tenant_id)

    try:
        events = []
        with open(AUDIT_PATH, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if len(events) >= limit:
                    break

                try:
                    record = json.loads(line.strip())
                    event = record.get("event", {})

                    # Apply filters
                    if tenant_id and event.get("tenant_id") != tenant_id:
                        continue
                    if event_type and event.get("event_type") != event_type:
                        continue

                    # Time filtering (basic implementation)
                    if start_time or end_time:
                        event_time = event.get("timestamp")
                        if event_time:
                            if start_time and event_time < start_time:
                                continue
                            if end_time and event_time > end_time:
                                continue

                    # Add line number for reference
                    event["_line_number"] = line_num
                    events.append(event)

                except json.JSONDecodeError:
                    continue

        return {
            "events": events,
            "total_returned": len(events),
            "filters_applied": {
                "start_time": start_time,
                "end_time": end_time,
                "tenant_id": tenant_id,
                "event_type": event_type,
            },
        }

    except FileNotFoundError:
        return {"events": [], "total_returned": 0, "error": "Audit log file not found"}
    except Exception as e:
        logger.error(f"Failed to read audit log: {e}")
        raise HTTPException(status_code=500, detail="Failed to read audit log") from e


@app.get("/v1/compliance/audit-integrity")
def verify_audit_integrity(x_tenant_id: str = Header(..., alias="x-tenant-id")) -> dict[str, Any]:
    """Verify audit log integrity using hash chain validation."""
    x_tenant_id = validate_tenant_id(x_tenant_id)

    try:
        from .audit_log import verify_log

        is_valid = verify_log(AUDIT_PATH, AUDIT_SECRET)

        return {
            "integrity_valid": is_valid,
            "audit_path": AUDIT_PATH,
            "verification_timestamp": datetime.now().isoformat(),
        }

    except FileNotFoundError:
        return {"integrity_valid": False, "error": "Audit log file not found", "audit_path": AUDIT_PATH}
    except Exception as e:
        logger.error(f"Failed to verify audit integrity: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify audit integrity") from e


@app.get("/v1/compliance/gdpr/data-subject/{subject_id}")
def get_data_subject_info(subject_id: str, x_tenant_id: str = Header(..., alias="x-tenant-id")) -> dict[str, Any]:
    """Get all data for a specific data subject (GDPR Article 15 - Right of Access)."""
    x_tenant_id = validate_tenant_id(x_tenant_id)

    try:
        subject_data = {
            "subject_id": subject_id,
            "tenant_id": x_tenant_id,
            "data_collected": [],
            "audit_events": [],
            "collection_timestamp": datetime.now().isoformat(),
        }

        # Search memory store for subject data
        for namespace, keys in STORE.items():
            for key, value in keys.items():
                # Simple search for subject ID in stored data
                if _contains_subject_data(value, subject_id):
                    subject_data["data_collected"].append(
                        {"namespace": namespace, "key": key, "data": value, "storage_location": "memory_store"}
                    )

        # Search audit log for subject-related events
        try:
            with open(AUDIT_PATH, encoding="utf-8") as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        event = record.get("event", {})

                        # Check if event relates to this subject
                        if _event_relates_to_subject(event, subject_id, x_tenant_id):
                            subject_data["audit_events"].append(event)

                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            pass

        return subject_data

    except Exception as e:
        logger.error(f"Failed to retrieve data subject info: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve data subject information") from e


@app.delete("/v1/compliance/gdpr/data-subject/{subject_id}")
def delete_data_subject_data(subject_id: str, x_tenant_id: str = Header(..., alias="x-tenant-id")) -> dict[str, Any]:
    """Delete all data for a specific data subject (GDPR Article 17 - Right to Erasure)."""
    x_tenant_id = validate_tenant_id(x_tenant_id)

    try:
        deleted_items = []

        # Remove from memory store
        for namespace in list(STORE.keys()):
            for key in list(STORE[namespace].keys()):
                value = STORE[namespace][key]
                if _contains_subject_data(value, subject_id):
                    del STORE[namespace][key]
                    deleted_items.append({"namespace": namespace, "key": key, "storage_location": "memory_store"})

                    # Audit the deletion
                    _audit_event(
                        "gdpr_data_deletion",
                        x_tenant_id,
                        namespace,
                        key,
                        {"subject_id": subject_id, "reason": "gdpr_right_to_erasure"},
                    )

        return {
            "subject_id": subject_id,
            "tenant_id": x_tenant_id,
            "deleted_items": deleted_items,
            "deletion_timestamp": datetime.now().isoformat(),
            "total_deleted": len(deleted_items),
        }

    except Exception as e:
        logger.error(f"Failed to delete data subject data: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete data subject data") from e


@app.get("/v1/compliance/soc2/access-report")
def get_soc2_access_report(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    x_tenant_id: str = Header(..., alias="x-tenant-id"),
) -> dict[str, Any]:
    """Generate SOC 2 access control report."""
    x_tenant_id = validate_tenant_id(x_tenant_id)

    try:
        report = {
            "report_type": "SOC2_ACCESS_CONTROL",
            "tenant_id": x_tenant_id,
            "period": {"start_date": start_date, "end_date": end_date},
            "generated_at": datetime.now().isoformat(),
            "access_events": [],
            "anomalies": [],
            "summary": {
                "total_access_events": 0,
                "unique_users": set(),
                "unique_namespaces": set(),
                "anomaly_count": 0,
            },
        }

        # Analyze audit log for the specified period
        try:
            with open(AUDIT_PATH, encoding="utf-8") as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        event = record.get("event", {})

                        # Filter by tenant and date range
                        if event.get("tenant_id") != x_tenant_id:
                            continue

                        event_date = event.get("timestamp", "")[:10]  # Extract date part
                        if event_date < start_date or event_date > end_date:
                            continue

                        # Include access events
                        if event.get("event_type") in ["memory_get", "memory_put"]:
                            report["access_events"].append(event)
                            report["summary"]["total_access_events"] += 1

                            # Track unique users and namespaces
                            if "user_id" in event:
                                report["summary"]["unique_users"].add(event["user_id"])
                            if "namespace" in event:
                                report["summary"]["unique_namespaces"].add(event["namespace"])

                        # Include anomaly events
                        if "anomaly" in event.get("event_type", "").lower():
                            report["anomalies"].append(event)
                            report["summary"]["anomaly_count"] += 1

                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            pass

        # Convert sets to lists for JSON serialization
        report["summary"]["unique_users"] = list(report["summary"]["unique_users"])
        report["summary"]["unique_namespaces"] = list(report["summary"]["unique_namespaces"])

        return report

    except Exception as e:
        logger.error(f"Failed to generate SOC2 access report: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate SOC2 access report") from e


def _contains_subject_data(data: Any, subject_id: str) -> bool:
    """Check if data contains information about a specific data subject."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key.lower() in ["user_id", "subject_id", "email", "username"] and str(value) == subject_id:
                return True
            if _contains_subject_data(value, subject_id):
                return True
    elif isinstance(data, list):
        for item in data:
            if _contains_subject_data(item, subject_id):
                return True
    elif isinstance(data, str):
        return subject_id in data

    return False


def _event_relates_to_subject(event: dict, subject_id: str, tenant_id: str) -> bool:
    """Check if an audit event relates to a specific data subject."""
    # Must be same tenant
    if event.get("tenant_id") != tenant_id:
        return False

    # Check if subject ID appears in event details
    event_str = json.dumps(event)
    return subject_id in event_str
