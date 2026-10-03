"""Sandbox runtime interface and contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SandboxExecutionResult(BaseModel):
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0


class SandboxStatus(BaseModel):
    running: bool
    container_id: Optional[str] = None
    mapped_ports: Dict[str, int] = Field(default_factory=dict)
    health: str = "healthy"


class ISandboxRuntime(ABC):
    """Abstract interface for isolated execution environments."""

    @abstractmethod
    def start(self, execution_id: str, workspace_path: str, network_enabled: bool = False) -> SandboxStatus:
        """Start the sandbox environment with workspace mounted."""
        pass

    @abstractmethod
    def execute_command(self, execution_id: str, command: str, timeout_seconds: int = 60) -> SandboxExecutionResult:
        """Run a command inside the sandbox."""
        pass

    @abstractmethod
    def stop(self, execution_id: str) -> None:
        """Stop and clean up the sandbox environment."""
        pass

    @abstractmethod
    def get_status(self, execution_id: str) -> SandboxStatus:
        """Query runtime health and port mappings."""
        pass
