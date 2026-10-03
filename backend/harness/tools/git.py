"""Git tool for workspace revision operations."""

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


class GitTool(ITool):
    """Tool to inspect and manipulate Git repository in the workspace."""

    def __init__(self, workspace_root: str = "./workspace"):
        self.workspace_root = workspace_root

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git",
            description="Executes Git commands (status, diff, log, add, commit) in the workspace.",
            parameters={
                "operation": {"type": "string", "description": "Git operation: status, diff, log, add, commit"},
                "args": {"type": "string", "description": "Optional arguments for git command", "default": ""},
            },
            danger_level="normal",
        )

    def execute(self, request: ToolRequest) -> ToolResponse:
        start_t = time.perf_counter()
        operation = request.arguments.get("operation")
        if not operation:
            return ToolResponse(
                tool_request_id=request.tool_request_id,
                execution_id=request.execution_id,
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="Missing required argument: 'operation'",
                duration_ms=(time.perf_counter() - start_t) * 1000.0,
            )

        args = request.arguments.get("args", "")
        cmd = f"git {operation} {args}".strip()

        try:
            res = subprocess.run(
                cmd,
                shell=True,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            status = ToolStatus.SUCCESS if res.returncode == 0 else ToolStatus.ERROR
            return ToolResponse(
                tool_request_id=request.tool_request_id,
                execution_id=request.execution_id,
                tool_name=self.name,
                status=status,
                output={
                    "operation": operation,
                    "exit_code": res.returncode,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                },
                error=res.stderr if res.returncode != 0 else None,
                duration_ms=duration_ms,
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
