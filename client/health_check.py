"""ATP Client Health Check Script.

Simple health check script that verifies the status of ATP services.
Checks both the router service and memory gateway for availability.
"""

import os

import requests

TIMEOUT = float(os.getenv("ATP_CLIENT_TIMEOUT", "3"))  # small adaptive timeout
print("router /healthz =>", requests.get("http://localhost:7443/healthz", timeout=TIMEOUT).text)
print("memory-gateway /healthz =>", requests.get("http://localhost:8080/healthz", timeout=TIMEOUT).json())
