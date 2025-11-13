"""
Firecracker-based sandbox driver implementation.

This module provides a sandbox driver that uses Firecracker microVMs for
isolated tool execution.
"""

import asyncio
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from .cost_caps import check_tool_cost_cap, get_cost_cap_registry
from .sandbox import SandboxConfig, SandboxDriver, SandboxError, SandboxResult, SandboxState


class FirecrackerSandboxDriver(SandboxDriver):
    """Firecracker-based sandbox driver for isolated tool execution."""

    def __init__(self, firecracker_path: str = "/usr/local/bin/firecracker",
                 jailer_path: str = "/usr/local/bin/jailer",
                 kernel_path: str = "/var/lib/firecracker/kernel/vmlinux",
                 rootfs_path: str = "/var/lib/firecracker/rootfs/rootfs.ext4"):
        super().__init__()
        self.firecracker_path = firecracker_path
        self.jailer_path = jailer_path
        self.kernel_path = kernel_path
        self.rootfs_path = rootfs_path
        self.vm_dir = Path("/tmp/firecracker-vms")  # noqa: S108 POC temporary directory
        self.socket_dir = Path("/tmp/firecracker-sockets")  # noqa: S108 POC temporary directory
        self.audit_log_path = os.getenv("AUDIT_LOG_PATH", "/var/log/atp/audit.log")
        self.audit_secret = os.getenv("AUDIT_SECRET", "default-secret").encode("utf-8")
        self._ensure_audit_log_directory()

    def _ensure_audit_log_directory(self) -> None:
        """Ensure the audit log directory exists."""
        audit_dir = Path(self.audit_log_path).parent
        audit_dir.mkdir(parents=True, exist_ok=True)

    def _log_tool_invocation(self, tool_id: str, command: list[str], cost_usd_micros: int, cost_tokens: int, success: bool) -> None:
        """Log tool invocation with cost cap information to audit log."""
        try:
            # Import audit_log here to avoid circular imports
            import sys
            sys.path.append(str(Path(__file__).parent.parent / "memory-gateway"))
            import audit_log

            # Get remaining budget information
            registry = get_cost_cap_registry()
            remaining_budget = registry.get_remaining_budget(tool_id)

            event = {
                "event_type": "tool_invocation",
                "tool_id": tool_id,
                "command": command,
                "cost_usd_micros": cost_usd_micros,
                "cost_tokens": cost_tokens,
                "success": success,
                "timestamp": time.time(),
                "remaining_budget": remaining_budget or {}
            }

            # Get the last hash from the audit log if it exists
            last_hash = None
            if Path(self.audit_log_path).exists():
                try:
                    with open(self.audit_log_path, encoding="utf-8") as f:
                        lines = f.readlines()
                        if lines:
                            last_entry = json.loads(lines[-1])
                            last_hash = last_entry.get("hash")
                except (json.JSONDecodeError, FileNotFoundError):
                    pass  # Start new chain if log is corrupted

            audit_log.append_event(self.audit_log_path, event, self.audit_secret, last_hash)

            # Record metrics for tool invocation cost
            # In a real implementation, this would update Prometheus metrics
            # metrics.tool_invocation_cost_sum.labels(tool_id=tool_id, success=str(success)).inc(cost_usd_micros / 1000000.0)

        except Exception as e:
            # Log audit failure but don't fail the operation
            self.logger.warning(f"Failed to write audit log entry: {e}")

        # Create temp directory for socket files
        self.socket_dir = Path(tempfile.mkdtemp(prefix="firecracker_sockets_"))
        self.vm_dir = Path(tempfile.mkdtemp(prefix="firecracker_vms_"))

        self.logger.info(f"Firecracker driver initialized with socket_dir: {self.socket_dir}")

    def _record_start(self) -> None:
        """Record sandbox start event for metrics."""
        # In a real implementation, this would update Prometheus metrics
        # metrics.sandbox_starts_total.inc()
        pass

    def _record_failure(self, failure_type: str) -> None:
        """Record sandbox failure event for metrics."""
        # In a real implementation, this would update Prometheus metrics
        # metrics.sandbox_failures_total.labels(type=failure_type).inc()
        pass

    def _record_duration(self, duration: float) -> None:
        """Record sandbox execution duration for metrics."""
        # In a real implementation, this would update Prometheus metrics
        # metrics.sandbox_execution_duration.observe(duration)
        pass

    def _setup_filesystem_confinement(self, config: SandboxConfig, vm_path: Path) -> dict[str, Any]:
        """Set up filesystem confinement with overlay mounts and ACLs."""
        confinement_config = {
            "overlay_mounts": [],
            "temp_dirs": [],
            "fs_violations": 0
        }

        # Create overlay mounts for read-only paths
        for read_only_path in config.read_only_paths or []:
            if os.path.exists(read_only_path):
                overlay_dir = vm_path / f"overlay_{os.path.basename(read_only_path)}"
                overlay_dir.mkdir(exist_ok=True)

                # Create upper, lower, work directories for overlay
                upper_dir = overlay_dir / "upper"
                work_dir = overlay_dir / "work"
                upper_dir.mkdir(exist_ok=True)
                work_dir.mkdir(exist_ok=True)

                confinement_config["overlay_mounts"].append({
                    "lower": read_only_path,
                    "upper": str(upper_dir),
                    "work": str(work_dir),
                    "target": read_only_path
                })

        # Create temp directories for writable paths
        for temp_path in config.temp_paths or []:
            # Create a safe directory name from the temp path
            safe_name = temp_path.replace('/', '_').replace('\\', '_').lstrip('_')
            temp_dir = vm_path / f"temp_{safe_name}"
            temp_dir.mkdir(parents=True, exist_ok=True)
            confinement_config["temp_dirs"].append({
                "host_path": str(temp_dir),
                "guest_path": temp_path
            })

        return confinement_config

    def _enforce_filesystem_acl(self, command: list[str], config: SandboxConfig) -> list[str]:
        """Enforce filesystem ACL by wrapping command with path restrictions."""
        # Create a wrapper script that enforces filesystem ACLs
        wrapper_cmd = [
            "/bin/bash", "-c",
            f"""
            # Set up filesystem ACL enforcement
            export SANDBOX_READ_ONLY_PATHS="{':'.join(config.read_only_paths or [])}"
            export SANDBOX_TEMP_PATHS="{':'.join(config.temp_paths or [])}"

            # Function to check if path is allowed for writing
            check_write_permission() {{
                local path="$1"
                # Allow writes to temp paths
                for temp_path in ${{SANDBOX_TEMP_PATHS//:/ }}; do
                    if [[ "$path" == "$temp_path"* ]]; then
                        return 0
                    fi
                done
                # Deny writes to read-only paths
                for ro_path in ${{SANDBOX_READ_ONLY_PATHS//:/ }}; do
                    if [[ "$path" == "$ro_path"* ]]; then
                        echo "SANDBOX_VIOLATION: Attempted write to read-only path: $path" >&2
                        # Record violation (in real implementation, this would be sent back to host)
                        echo "VIOLATION:$path" >> /tmp/sandbox_violations.log
                        return 1
                    fi
                done
                # Allow other writes (this would be more restrictive in production)
                return 0
            }}

            # Override common commands to enforce ACLs
            mkdir() {{
                if check_write_permission "$1"; then
                    command mkdir "$@"
                else
                    return 1
                fi
            }}

            touch() {{
                if check_write_permission "$1"; then
                    command touch "$@"
                else
                    return 1
                fi
            }}

            # Execute the original command
            exec {" ".join(command)}
            """
        ]

        return wrapper_cmd

    def _record_filesystem_violation(self, sandbox_id: str, violation_path: str) -> None:
        """Record a filesystem violation for metrics."""
        if sandbox_id in self._sandboxes:
            vm_config = self._sandboxes[sandbox_id]
            vm_config["confinement"]["fs_violations"] += 1
            self.logger.warning(f"Filesystem violation in sandbox {sandbox_id}: {violation_path}")
            # In a real implementation, this would update Prometheus metrics
            # metrics.sandbox_fs_violations_total.inc()

    async def create_sandbox(self, config: SandboxConfig) -> str:
        """Create a new Firecracker microVM sandbox."""
        sandbox_id = str(uuid.uuid4())

        # Create VM directory
        vm_path = self.vm_dir / sandbox_id
        vm_path.mkdir(parents=True, exist_ok=True)

        # Set up filesystem confinement
        confinement_config = self._setup_filesystem_confinement(config, vm_path)

        # Create socket path
        socket_path = self.socket_dir / f"{sandbox_id}.socket"

        vm_config = {
            "sandbox_id": sandbox_id,
            "vm_path": str(vm_path),
            "socket_path": str(socket_path),
            "config": config,
            "confinement": confinement_config,
            "state": SandboxState.CREATED,
            "process": None,
            "created_at": time.time()
        }

        self._sandboxes[sandbox_id] = vm_config
        self.logger.info(f"Created Firecracker sandbox with filesystem confinement: {sandbox_id}")
        return sandbox_id

    async def start_sandbox(self, sandbox_id: str) -> None:
        """Start the Firecracker microVM."""
        if sandbox_id not in self._sandboxes:
            raise ValueError(f"Sandbox {sandbox_id} not found")

        vm_config = self._sandboxes[sandbox_id]
        if vm_config["state"] != SandboxState.CREATED:
            raise SandboxError(f"Sandbox {sandbox_id} is not in CREATED state")

        try:
            vm_config["state"] = SandboxState.STARTING
            self._record_start()

            # Create Firecracker configuration
            config = vm_config["config"]
            socket_path = vm_config["socket_path"]
            vm_path = vm_config["vm_path"]

            # Start Firecracker process
            cmd = [
                self.firecracker_path,
                "--api-sock", socket_path,
                "--id", sandbox_id,
                "--config-file", str(Path(vm_path) / "config.json")
            ]

            # Create config file asynchronously
            import asyncio
            firecracker_config = self._create_firecracker_config(config, vm_path)
            config_path = Path(vm_path) / "config.json"
            config_content = json.dumps(firecracker_config, indent=2)
            await asyncio.to_thread(lambda: config_path.write_text(config_content))

            self.logger.info(f"Starting Firecracker VM: {' '.join(cmd)}")

            # Start the process
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=vm_path
            )

            vm_config["process"] = process
            vm_config["state"] = SandboxState.RUNNING
            vm_config["started_at"] = time.time()

            self.logger.info(f"Firecracker sandbox {sandbox_id} started successfully")

        except Exception as e:
            vm_config["state"] = SandboxState.FAILED
            self._record_failure("start_failed")
            self.logger.error(f"Failed to start Firecracker sandbox {sandbox_id}: {e}")
            raise SandboxError(f"Failed to start Firecracker sandbox: {e}") from e

    def _create_firecracker_config(self, config: SandboxConfig, vm_path: str) -> dict[str, Any]:
        """Create Firecracker configuration."""
        return {
            "boot-source": {
                "kernel_image_path": self.kernel_path,
                "boot_args": "console=ttyS0 reboot=k panic=1 pci=off"
            },
            "drives": [{
                "drive_id": "rootfs",
                "path_on_host": self.rootfs_path,
                "is_root_device": True,
                "is_read_only": False
            }],
            "machine-config": {
                "vcpu_count": config.cpu_count,
                "mem_size_mib": config.memory_mb
            },
            "network-interfaces": [] if not config.network_enabled else [{
                "iface_id": "eth0",
                "guest_mac": "AA:FC:00:00:00:01",
                "host_dev_name": "tap0"
            }],
            "vsock": {
                "guest_cid": 3,
                "uds_path": f"/tmp/vsock_{uuid.uuid4()}"  # noqa: S108
            }
        }

    async def execute_in_sandbox(
        self,
        sandbox_id: str,
        command: list[str],
        env: Optional[dict[str, str]] = None,
        cwd: Optional[str] = None
    ) -> SandboxResult:
        """Execute a command in the Firecracker sandbox via vsock."""
        if sandbox_id not in self._sandboxes:
            raise ValueError(f"Sandbox {sandbox_id} not found")

        vm_config = self._sandboxes[sandbox_id]
        if vm_config["state"] != SandboxState.RUNNING:
            raise SandboxError(f"Sandbox {sandbox_id} is not running")

        start_time = time.time()

        try:
            # For POC, we'll simulate command execution
            # In a real implementation, this would use vsock to communicate with the VM
            config = vm_config["config"]

            # Check if command is allowed based on configuration
            if not self._is_command_allowed(command, config):
                raise SandboxError(f"Command not allowed: {' '.join(command)}")

            # Check cost cap if tool_id is specified
            if config.tool_id:
                # Estimate cost (in a real implementation, this would be based on actual usage)
                estimated_usd_micros = 1000  # $0.001 estimated cost
                estimated_tokens = 10  # 10 tokens estimated

                if not check_tool_cost_cap(config.tool_id, estimated_usd_micros, estimated_tokens):
                    # Log failed invocation due to cost cap
                    self._log_tool_invocation(config.tool_id, command, estimated_usd_micros, estimated_tokens, False)
                    raise SandboxError(f"Cost cap exceeded for tool {config.tool_id}")

            # Enforce filesystem ACLs by wrapping the command
            wrapped_command = self._enforce_filesystem_acl(command, config)

            # Simulate execution (replace with actual vsock communication)
            result = await self._simulate_execution(wrapped_command, env, cwd, config)

            duration = time.time() - start_time
            self._record_duration(duration)

            # Log successful invocation
            if config.tool_id:
                self._log_tool_invocation(config.tool_id, command, estimated_usd_micros if config.tool_id else 0, estimated_tokens if config.tool_id else 0, True)

            return result

        except Exception as e:
            duration = time.time() - start_time
            self._record_duration(duration)
            self._record_failure("execution_failed")
            self.logger.error(f"Failed to execute command in sandbox {sandbox_id}: {e}")

            # Log failed invocation
            if config.tool_id:
                estimated_usd_micros = 1000
                estimated_tokens = 10
                self._log_tool_invocation(config.tool_id, command, estimated_usd_micros, estimated_tokens, False)

            raise SandboxError(f"Failed to execute command in sandbox: {e}") from e

    def _is_command_allowed(self, command: list[str], config: SandboxConfig) -> bool:
        """Check if command is allowed based on sandbox configuration."""
        if not command:
            return False

        # Basic allowlist - in production this would be more sophisticated
        allowed_commands = [
            "python", "python3", "node", "npm", "curl", "wget",
            "ls", "cat", "grep", "head", "tail", "wc"
        ]

        base_cmd = command[0].split('/')[-1]  # Get basename
        return base_cmd in allowed_commands

    async def _simulate_execution(
        self,
        command: list[str],
        env: Optional[dict[str, str]],
        cwd: Optional[str],
        config: SandboxConfig
    ) -> SandboxResult:
        """Simulate command execution for POC purposes."""
        # This is a simulation - in real implementation, use vsock
        await asyncio.sleep(0.1)  # Simulate some processing time

        # Simulate successful execution
        return SandboxResult(
            exit_code=0,
            stdout="Command executed successfully\n",
            stderr="",
            duration_seconds=0.1,
            resource_usage={
                "cpu_percent": 5.0,
                "memory_mb": 50,
                "network_bytes": 0
            }
        )

    async def stop_sandbox(self, sandbox_id: str) -> None:
        """Stop the Firecracker microVM."""
        if sandbox_id not in self._sandboxes:
            raise ValueError(f"Sandbox {sandbox_id} not found")

        vm_config = self._sandboxes[sandbox_id]

        try:
            if vm_config["process"]:
                vm_config["process"].terminate()
                try:
                    await asyncio.wait_for(vm_config["process"].wait(), timeout=10.0)
                except asyncio.TimeoutError:
                    vm_config["process"].kill()
                    await vm_config["process"].wait()

            vm_config["state"] = SandboxState.STOPPED
            self.logger.info(f"Firecracker sandbox {sandbox_id} stopped")

        except Exception as e:
            vm_config["state"] = SandboxState.FAILED
            self._record_failure("stop_failed")
            self.logger.error(f"Failed to stop Firecracker sandbox {sandbox_id}: {e}")
            raise SandboxError(f"Failed to stop sandbox {sandbox_id}: {e}") from e

    async def destroy_sandbox(self, sandbox_id: str) -> None:
        """Destroy the Firecracker microVM and clean up resources."""
        if sandbox_id not in self._sandboxes:
            raise ValueError(f"Sandbox {sandbox_id} not found")

        vm_config = self._sandboxes[sandbox_id]

        try:
            # Stop if still running
            if vm_config["state"] == SandboxState.RUNNING:
                await self.stop_sandbox(sandbox_id)

            # Clean up files
            vm_path = Path(vm_config["vm_path"])
            if vm_path.exists():
                import shutil
                shutil.rmtree(vm_path)

            # Remove from tracking
            del self._sandboxes[sandbox_id]
            self.logger.info(f"Firecracker sandbox {sandbox_id} destroyed")

        except Exception as e:
            self._record_failure("destroy_failed")
            self.logger.error(f"Failed to destroy Firecracker sandbox {sandbox_id}: {e}")
            raise SandboxError(f"Failed to destroy sandbox {sandbox_id}: {e}") from e

    async def get_sandbox_status(self, sandbox_id: str) -> SandboxState:
        """Get the current status of the sandbox."""
        if sandbox_id not in self._sandboxes:
            raise ValueError(f"Sandbox {sandbox_id} not found")

        return self._sandboxes[sandbox_id]["state"]

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup all sandboxes."""
        sandboxes_to_destroy = list(self._sandboxes.keys())
        for sandbox_id in sandboxes_to_destroy:
            try:
                await self.destroy_sandbox(sandbox_id)
            except Exception as e:
                self.logger.error(f"Failed to cleanup sandbox {sandbox_id}: {e}")

        # Clean up temp directories
        try:
            import shutil
            if self.socket_dir.exists():
                shutil.rmtree(self.socket_dir)
            if self.vm_dir.exists():
                shutil.rmtree(self.vm_dir)
        except Exception as e:
            self.logger.error(f"Failed to cleanup temp directories: {e}")
