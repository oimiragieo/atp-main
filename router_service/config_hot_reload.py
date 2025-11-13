"""
Configuration Hot-Reloading System

GAP-4: Implement configuration hot-reloading
Provides file watching and automatic configuration reloading for production services.
"""

import asyncio
import hashlib
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ConfigHotReloader:
    """Hot-reloading configuration manager with file watching."""

    def __init__(
        self, config_file: str, reload_callback: Callable[[dict[str, Any]], None], check_interval: float = 5.0
    ):
        """
        Initialize hot-reloader.

        Args:
            config_file: Path to configuration file to watch
            reload_callback: Function to call when config changes
            check_interval: How often to check for file changes (seconds)
        """
        self.config_file = Path(config_file)
        self.reload_callback = reload_callback
        self.check_interval = check_interval
        self._last_hash: str | None = None
        self._last_mtime: float | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    def _get_file_hash(self) -> str | None:
        """Get SHA256 hash of config file."""
        try:
            if not self.config_file.exists():
                return None
            content = self.config_file.read_text(encoding="utf-8")
            return hashlib.sha256(content.encode()).hexdigest()
        except Exception as e:
            logger.error(f"Failed to read config file {self.config_file}: {e}")
            return None

    def _get_file_mtime(self) -> float | None:
        """Get modification time of config file."""
        try:
            if not self.config_file.exists():
                return None
            return self.config_file.stat().st_mtime
        except Exception as e:
            logger.error(f"Failed to get mtime for {self.config_file}: {e}")
            return None

    def _load_config(self) -> dict[str, Any] | None:
        """Load configuration from file."""
        try:
            if not self.config_file.exists():
                return None
            with open(self.config_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {self.config_file}: {e}")
            return None

    async def _watch_loop(self) -> None:
        """Main file watching loop."""
        logger.info(f"Starting config hot-reload watcher for {self.config_file}")

        while self._running:
            try:
                # Check if file has changed
                current_mtime = self._get_file_mtime()
                current_hash = self._get_file_hash()

                if current_mtime != self._last_mtime or current_hash != self._last_hash:
                    if current_hash is not None:
                        logger.info(f"Config file {self.config_file} changed, reloading...")

                        config = self._load_config()
                        if config is not None:
                            try:
                                self.reload_callback(config)
                                self._last_hash = current_hash
                                self._last_mtime = current_mtime
                                logger.info("Config reloaded successfully")
                            except Exception as e:
                                logger.error(f"Config reload callback failed: {e}")
                        else:
                            logger.warning("Failed to load new config, keeping old config")
                    else:
                        logger.warning(f"Config file {self.config_file} not found or unreadable")

                await asyncio.sleep(self.check_interval)

            except Exception as e:
                logger.error(f"Error in config watch loop: {e}")
                await asyncio.sleep(self.check_interval)

    def start(self) -> None:
        """Start the hot-reloading watcher."""
        if self._running:
            logger.warning("Config hot-reloader already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        """Stop the hot-reloading watcher."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Config hot-reloader stopped")

    def force_reload(self) -> bool:
        """Force a reload of the configuration."""
        config = self._load_config()
        if config is not None:
            try:
                self.reload_callback(config)
                self._last_hash = self._get_file_hash()
                self._last_mtime = self._get_file_mtime()
                logger.info("Config force-reloaded successfully")
                return True
            except Exception as e:
                logger.error(f"Config force-reload callback failed: {e}")
                return False
        else:
            logger.error("Failed to load config for force reload")
            return False


# Global instance for easy access
_hot_reloader: ConfigHotReloader | None = None


def init_config_hot_reload(
    config_file: str, reload_callback: Callable[[dict[str, Any]], None], check_interval: float = 5.0
) -> ConfigHotReloader:
    """
    Initialize global config hot-reloader.

    Args:
        config_file: Path to config file to watch
        reload_callback: Function to call on config changes
        check_interval: Check interval in seconds

    Returns:
        ConfigHotReloader instance
    """
    global _hot_reloader
    _hot_reloader = ConfigHotReloader(config_file, reload_callback, check_interval)
    return _hot_reloader


def get_config_hot_reloader() -> ConfigHotReloader | None:
    """Get the global config hot-reloader instance."""
    return _hot_reloader


async def shutdown_config_hot_reload() -> None:
    """Shutdown the global config hot-reloader."""
    global _hot_reloader
    if _hot_reloader:
        await _hot_reloader.stop()
        _hot_reloader = None
