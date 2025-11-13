# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Adapter domain - LLM provider adapter management."""

from .registry import AdapterInfo, AdapterRegistry

__all__ = ["AdapterRegistry", "AdapterInfo"]
