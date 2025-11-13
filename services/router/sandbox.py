import abc
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SandboxState(Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"

class SandboxError(Exception):
    pass

@dataclass
class SandboxConfig:
    memory_mb: int = 512
    cpu_count: int = 1
    disk_mb: int = 1024
    timeout_seconds: int = 300
    network_enabled: bool = False
    allowlist_domains: Optional[list[str]] = None
    read_only_paths: Optional[list[str]] = None
    temp_paths: Optional[list[str]] = None
    tool_id: Optional[str] = None  # Tool identifier for cost cap enforcement

    def __post_init__(self):
        if self.allowlist_domains is None:
            self.allowlist_domains = []
        if self.read_only_paths is None:
            self.read_only_paths = ["/usr", "/bin", "/lib"]
        if self.temp_paths is None:
            self.temp_paths = ["/tmp", "/var/tmp"]  # noqa: S108

@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    resource_usage: dict

class SandboxDriver(abc.ABC):
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._sandboxes = {}

    @abc.abstractmethod
    def _record_start(self):
        """Record sandbox start event for metrics."""
        pass

    @abc.abstractmethod
    async def create_sandbox(self, config):
        pass

    @abc.abstractmethod
    async def start_sandbox(self, sandbox_id):
        pass

    @abc.abstractmethod
    async def execute_in_sandbox(self, sandbox_id, command, env=None, cwd=None):
        pass

    @abc.abstractmethod
    async def stop_sandbox(self, sandbox_id):
        pass

    @abc.abstractmethod
    async def destroy_sandbox(self, sandbox_id):
        pass

    @abc.abstractmethod
    async def get_sandbox_status(self, sandbox_id):
        pass

class SandboxManager:
    def __init__(self):
        self.drivers = {}
        self.logger = logging.getLogger(__name__)

    def register_driver(self, name, driver):
        self.drivers[name] = driver
        self.logger.info(f"Registered sandbox driver: {name}")

    def get_driver(self, name):
        if name not in self.drivers:
            raise ValueError(f"Sandbox driver '{name}' not found")
        return self.drivers[name]

    def list_drivers(self):
        return list(self.drivers.keys())

_sandbox_manager = SandboxManager()

def get_sandbox_manager():
    return _sandbox_manager

def register_sandbox_driver(name, driver):
    _sandbox_manager.register_driver(name, driver)

def get_sandbox_driver(name):
    return _sandbox_manager.get_driver(name)
