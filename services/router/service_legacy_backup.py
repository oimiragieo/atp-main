"""Legacy backup shim.

We intentionally avoid wildcard export to satisfy F403. This module re-exports
the FastAPI app object for any older import paths that referenced
`router_service.service_legacy_backup`.
"""

from .service import app  # noqa: F401

__all__ = ["app"]
