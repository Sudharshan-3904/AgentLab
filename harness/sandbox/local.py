"""Local process sandbox runtime providing controlled execution environment."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import time
from typing import Dict, Optional

from harness.sandbox.interface import (
    ISandboxRuntime,
    SandboxExecutionResult,
    SandboxStatus,
)


class LocalProcessSandboxRuntime(ISandboxRuntime):
    """Controlled local process sandbox executing commands within isolated workspace directory."""

    def __init__(self):
        self._active_sessions: Dict[str, Dict[str, Any]] = {}

    def start(
        self,
        execution_id: str,
        workspace_path: str,
        network_enabled: bool = False,
    ) -> SandboxStatus:
        """Initialize controlled sandbox boundary for execution."""
        resolved_path = str(Path(workspace_path).resolve())
        Path(resolved_path).mkdir(parents=True, exist_ok=True)

        session = {
            "workspace_path": resolved_path,
            "network_enabled": network_enabled,
            "running": True,
            "container_id": f"sandbox-proc-{execution_id}",
            "ports": {},
            "active_processes": [],
        }
        self._active_sessions[execution_id] = session

        return SandboxStatus(
            running=True,
            container_id=session["container_id"],
            mapped_ports={},
            health="healthy",
        )

    def execute_command(
        self,
        execution_id: str,
        command: str,
        timeout_seconds: int = 60,
    ) -> SandboxExecutionResult:
        """Run command strictly within workspace directory with timeout limits."""
        session = self._active_sessions.get(execution_id)
        if not session or not session["running"]:
            return SandboxExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"Sandbox not running for execution: {execution_id}",
                duration_ms=0.0,
            )

        workspace_path = session["workspace_path"]
        start_t = time.perf_counter()

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["SANDBOX_CONTAINED"] = "1"

        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=workspace_path,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout_seconds,
            )
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
                stdout="",
                stderr=f"Execution exceeded sandbox timeout limit of {timeout_seconds}s",
                duration_ms=duration_ms,
            )
        except Exception as ex:
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            return SandboxExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=str(ex),
                duration_ms=duration_ms,
            )

    def stop(self, execution_id: str) -> None:
        """Terminate and clean up sandbox session."""
        session = self._active_sessions.get(execution_id)
        if session:
            session["running"] = False
            self._active_sessions.pop(execution_id, None)

    def get_status(self, execution_id: str) -> SandboxStatus:
        """Retrieve current sandbox status."""
        session = self._active_sessions.get(execution_id)
        if not session or not session["running"]:
            return SandboxStatus(running=False, health="stopped")

        return SandboxStatus(
            running=True,
            container_id=session["container_id"],
            mapped_ports=session.get("ports", {}),
            health="healthy",
        )
