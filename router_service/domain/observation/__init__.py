# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Observation domain - logging and analytics for LLM requests."""

from .models import Observation
from .service import ObservationService

__all__ = ["ObservationService", "Observation"]
