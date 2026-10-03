"""Test runner tool for executing automated unit and integration tests."""

from __future__ import annotations

import re
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


class TestRunnerTool(ITool):
    """Tool to execute pytest or unittest test suites inside the workspace."""

    __test__ = False  # Avoid pytest collection warning

    def __init__(self, workspace_root: str = "./workspace"):
        self.workspace_root = workspace_root

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="test_runner",
            description="Executes test suites (e.g. pytest) and reports pass/fail counts.",
            parameters={
                "test_path": {"type": "string", "description": "Relative path to test directory or file", "default": "tests"},
                "extra_args": {"type": "string", "description": "Optional flags (e.g. -v, -k test_name)", "default": ""},
            },
            danger_level="normal",
        )

    def execute(self, request: ToolRequest) -> ToolResponse:
        start_t = time.perf_counter()
        test_path = request.arguments.get("test_path", "tests")
        extra_args = request.arguments.get("extra_args", "")
        cmd = f"pytest {test_path} {extra_args}".strip()

        try:
            res = subprocess.run(
                cmd,
                shell=True,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            duration_ms = (time.perf_counter() - start_t) * 1000.0

            # Parse pytest summary lines (e.g., '14 passed in 0.05s', '1 failed, 13 passed')
            passed_match = re.search(r"(\d+)\s+passed", res.stdout)
            failed_match = re.search(r"(\d+)\s+failed", res.stdout)

            passed_count = int(passed_match.group(1)) if passed_match else 0
            failed_count = int(failed_match.group(1)) if failed_match else 0
            all_passed = (res.returncode == 0) and (failed_count == 0)

            return ToolResponse(
                tool_request_id=request.tool_request_id,
                execution_id=request.execution_id,
                tool_name=self.name,
                status=ToolStatus.SUCCESS if all_passed else ToolStatus.ERROR,
                output={
                    "all_passed": all_passed,
                    "passed_count": passed_count,
                    "failed_count": failed_count,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                    "exit_code": res.returncode,
                },
                error=res.stderr if not all_passed and res.stderr else (res.stdout if not all_passed else None),
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
