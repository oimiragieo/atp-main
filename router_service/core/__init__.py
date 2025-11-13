# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Core application infrastructure."""

from .container import Container, get_container
from .app import create_app
from .lifecycle import LifecycleManager

__all__ = ["Container", "get_container", "create_app", "LifecycleManager"]
