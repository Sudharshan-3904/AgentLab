"""Shell execution tool for Local AI Harness."""

from __future__ import annotations

import subprocess
import time
from typing import Any, Dict, Optional

from harness.tools.interface import (
    ITool,
    ToolDefinition,
    ToolRequest,
    ToolResponse,
    ToolStatus,
)


class ShellTool(ITool):
    """Tool to execute shell commands within the workspace directory."""

    def __init__(self, workspace_root: str = "./workspace", default_timeout: int = 60):
        self.workspace_root = workspace_root
        self.default_timeout = default_timeout

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="shell",
            description="Executes a shell command within the workspace directory.",
            parameters={
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout_seconds": {"type": "integer", "description": "Command timeout", "default": 60},
            },
            danger_level="high_risk",
        )

    def execute(self, request: ToolRequest) -> ToolResponse:
        start_t = time.perf_counter()
        command = request.arguments.get("command")
        if not command:
            return ToolResponse(
                tool_request_id=request.tool_request_id,
                execution_id=request.execution_id,
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="Missing required argument: 'command'",
                duration_ms=(time.perf_counter() - start_t) * 1000.0,
            )

        timeout = request.arguments.get("timeout_seconds", self.default_timeout)

        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            status = ToolStatus.SUCCESS if res.returncode == 0 else ToolStatus.ERROR
            return ToolResponse(
                tool_request_id=request.tool_request_id,
                execution_id=request.execution_id,
                tool_name=self.name,
                status=status,
                output={
                    "command": command,
                    "exit_code": res.returncode,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                },
                error=res.stderr if res.returncode != 0 else None,
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired:
            return ToolResponse(
                tool_request_id=request.tool_request_id,
                execution_id=request.execution_id,
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=f"Command timed out after {timeout} seconds",
                duration_ms=(time.perf_counter() - start_t) * 1000.0,
            )
        except Exception as ex:
            return ToolResponse(
                tool_request_id=request.tool_request_id,
                execution_id=request.execution_id,
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=str(ex),
                duration_ms=(time.perf_counter() - start_t) * 1000.0,
            )
