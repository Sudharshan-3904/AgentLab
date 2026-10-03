"""Docker-based sandbox runtime implementation for container isolation."""

from __future__ import annotations

import subprocess
import time
from typing import Dict, Optional

from harness.sandbox.interface import (
    ISandboxRuntime,
    SandboxExecutionResult,
    SandboxStatus,
)


class DockerSandboxRuntime(ISandboxRuntime):
    """Executes code and commands inside an isolated Docker container."""

    def __init__(
        self,
        image: str = "python:3.11-slim",
        memory_limit: str = "1g",
        cpu_limit: str = "1.0",
    ):
        self.image = image
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self._containers: Dict[str, str] = {}

    @classmethod
    def is_docker_available(cls) -> bool:
        """Check whether the docker CLI and daemon are reachable."""
        try:
            res = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
            return res.returncode == 0
        except Exception:
            return False

    def start(
        self,
        execution_id: str,
        workspace_path: str,
        network_enabled: bool = False,
    ) -> SandboxStatus:
        """Start an isolated Docker container with workspace mounted."""
        if not self.is_docker_available():
            raise RuntimeError("Docker daemon is not available or not installed on this host system.")

        container_name = f"harness-sandbox-{execution_id}"
        cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "-v", f"{workspace_path}:/workspace",
            "-w", "/workspace",
            f"--memory={self.memory_limit}",
            f"--cpus={self.cpu_limit}",
        ]
        if not network_enabled:
            cmd.extend(["--network", "none"])

        cmd.extend([self.image, "tail", "-f", "/dev/null"])

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Failed to start Docker container: {res.stderr}")

        container_id = res.stdout.strip()
        self._containers[execution_id] = container_id

        return SandboxStatus(
            running=True,
            container_id=container_id,
            mapped_ports={},
            health="healthy",
        )

    def execute_command(
        self,
        execution_id: str,
        command: str,
        timeout_seconds: int = 60,
    ) -> SandboxExecutionResult:
        """Execute command inside the container using docker exec."""
        container_id = self._containers.get(execution_id)
        if not container_id:
            return SandboxExecutionResult(
                exit_code=-1,
                stderr=f"No container found for execution: {execution_id}",
            )

        start_t = time.perf_counter()
        cmd = ["docker", "exec", container_id, "sh", "-c", command]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            return SandboxExecutionResult(
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired:
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            return SandboxExecutionResult(
                exit_code=-1,
                stderr=f"Docker execution timed out after {timeout_seconds}s",
                duration_ms=duration_ms,
            )

    def stop(self, execution_id: str) -> None:
        """Stop and remove the Docker container."""
        container_id = self._containers.pop(execution_id, None)
        if container_id and self.is_docker_available():
            subprocess.run(["docker", "rm", "-f", container_id], capture_output=True)

    def get_status(self, execution_id: str) -> SandboxStatus:
        """Check status of the Docker container."""
        container_id = self._containers.get(execution_id)
        if not container_id:
            return SandboxStatus(running=False, health="stopped")

        return SandboxStatus(running=True, container_id=container_id, health="healthy")
