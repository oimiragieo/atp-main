"""Adapter client infrastructure for ATP router.

This module provides gRPC client infrastructure for communicating with
external LLM adapters following the adapter protocol defined in adapter.proto.
"""

from .client import AdapterClient, AdapterClientPool

__all__ = ["AdapterClient", "AdapterClientPool"]
