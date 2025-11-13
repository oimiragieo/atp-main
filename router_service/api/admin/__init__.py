# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Admin API endpoints."""

from .health import router as health_router

__all__ = ["health_router"]
