"""Sandbox factory resolving and instantiating sandbox runtimes."""

from __future__ import annotations

from harness.sandbox.docker import DockerSandboxRuntime
from harness.sandbox.interface import ISandboxRuntime
from harness.sandbox.local import LocalProcessSandboxRuntime


class SandboxFactory:
    """Factory to instantiate the appropriate sandbox runtime."""

    @classmethod
    def create(
        cls,
        runtime_type: str = "docker",
        fallback_to_local: bool = True,
        **kwargs,
    ) -> ISandboxRuntime:
        """Instantiate sandbox runtime based on requested type and system capability."""
        normalized = runtime_type.lower()
        if normalized == "docker":
            if DockerSandboxRuntime.is_docker_available():
                return DockerSandboxRuntime(**kwargs)
            if fallback_to_local:
                return LocalProcessSandboxRuntime()
            raise RuntimeError("Docker runtime requested but Docker daemon is not available.")

        if normalized == "local":
            return LocalProcessSandboxRuntime()

        raise ValueError(f"Unknown sandbox runtime: '{runtime_type}'. Supported: 'docker', 'local'")
