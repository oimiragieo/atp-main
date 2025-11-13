# Copyright 2025 ATP Project Contributors
# Licensed under the Apache License, Version 2.0

"""Dependency injection container for service management."""

from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar, cast

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Container:
    """
    Dependency injection container.

    Manages service instances and their lifecycles.
    Supports singleton and factory patterns.
    """

    def __init__(self):
        self._services: dict[type, Any] = {}
        self._factories: dict[type, Callable[..., Any]] = {}
        self._singletons: set[type] = set()

    def register(
        self,
        interface: type[T],
        implementation: T | None = None,
        factory: Callable[..., T] | None = None,
        singleton: bool = True
    ) -> None:
        """
        Register a service in the container.

        Args:
            interface: The interface type
            implementation: Concrete implementation instance (for singleton)
            factory: Factory function to create instances (for non-singleton)
            singleton: Whether to use singleton pattern (default: True)
        """
        if implementation is None and factory is None:
            raise ValueError("Must provide either implementation or factory")

        if implementation is not None and factory is not None:
            raise ValueError("Cannot provide both implementation and factory")

        if implementation is not None:
            # Register instance directly
            self._services[interface] = implementation
            if singleton:
                self._singletons.add(interface)
            logger.debug(f"Registered service: {interface.__name__}")

        if factory is not None:
            # Register factory
            self._factories[interface] = factory
            if singleton:
                self._singletons.add(interface)
            logger.debug(f"Registered factory for: {interface.__name__}")

    def get(self, interface: type[T]) -> T:
        """
        Retrieve a service from the container.

        Args:
            interface: The interface type to retrieve

        Returns:
            The service instance

        Raises:
            ValueError: If service is not registered
        """
        # Check if instance already exists
        if interface in self._services:
            return cast(T, self._services[interface])

        # Check if factory exists
        if interface in self._factories:
            factory = self._factories[interface]
            instance = factory(self)  # Pass container for dependency resolution

            # Cache if singleton
            if interface in self._singletons:
                self._services[interface] = instance

            return cast(T, instance)

        raise ValueError(f"Service not registered: {interface.__name__}")

    def has(self, interface: type) -> bool:
        """Check if a service is registered."""
        return interface in self._services or interface in self._factories

    def clear(self) -> None:
        """Clear all registered services (useful for testing)."""
        self._services.clear()
        self._factories.clear()
        self._singletons.clear()
        logger.debug("Container cleared")


# Global container instance
_container: Container | None = None


def get_container() -> Container:
    """Get the global container instance."""
    global _container
    if _container is None:
        _container = Container()
    return _container


def reset_container() -> None:
    """Reset the global container (for testing)."""
    global _container
    _container = None
