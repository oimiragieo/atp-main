"""Structured JSON logging utilities."""

import json
import logging
import sys
import time
from typing import Any


class StructuredLogger:
    """Structured JSON logger with consistent formatting."""

    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(message)s"))  # JSON output
            self.logger.addHandler(handler)
        self.logger.setLevel(level)

    def _log(self, level: int, event: str, **fields: Any) -> None:
        """Internal logging method."""
        record = {
            "ts": round(time.time(), 3),
            "level": logging.getLevelName(level),
            "event": event,
            **fields
        }
        try:
            self.logger.log(level, json.dumps(record, separators=(",", ":")))
        except Exception as err:  # noqa: S110
            # Fallback to basic logging if JSON serialization fails
            self.logger.log(level, f"LOG_SERIALIZE_ERROR event={event} error={err}")

    def debug(self, event: str, **fields: Any) -> None:
        """Log debug event."""
        self._log(logging.DEBUG, event, **fields)

    def info(self, event: str, **fields: Any) -> None:
        """Log info event."""
        self._log(logging.INFO, event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        """Log warning event."""
        self._log(logging.WARNING, event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        """Log error event."""
        self._log(logging.ERROR, event, **fields)

    def critical(self, event: str, **fields: Any) -> None:
        """Log critical event."""
        self._log(logging.CRITICAL, event, **fields)


# Global logger instance
_logger = StructuredLogger("atp_router")


def log_event(event: str, **fields: Any) -> None:
    """Legacy function for backward compatibility."""
    _logger.info(event, **fields)


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance for a specific module."""
    return StructuredLogger(name)
