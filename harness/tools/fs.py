"""Filesystem tools: ReadFileTool, WriteFileTool, ListFilesTool."""

from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from harness.tools.interface import (
    ITool,
    ToolDefinition,
    ToolRequest,
    ToolResponse,
    ToolStatus,
)


def _resolve_safe_path(requested_path: str, workspace_root: str) -> Path:
    """Resolve path and verify it stays strictly inside the workspace root."""
    root = Path(workspace_root).resolve()
    target = (root / requested_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise PermissionError(f"Access denied: path '{requested_path}' escapes workspace root '{workspace_root}'")
    return target


class ReadFileTool(ITool):
    """Tool to read text content from a file inside the workspace."""

    def __init__(self, workspace_root: str = "./workspace"):
        self.workspace_root = workspace_root

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description="Reads text content from a file inside the workspace.",
            parameters={
                "path": {"type": "string", "description": "Relative path to file"},
            },
            danger_level="read_only",
        )

    def execute(self, request: ToolRequest) -> ToolResponse:
        start_t = time.perf_counter()
        rel_path = request.arguments.get("path")
        if not rel_path:
            return ToolResponse(
                tool_request_id=request.tool_request_id,
                execution_id=request.execution_id,
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="Missing required argument: 'path'",
                duration_ms=(time.perf_counter() - start_t) * 1000.0,
            )

        try:
            safe_path = _resolve_safe_path(rel_path, self.workspace_root)
            if not safe_path.exists():
                return ToolResponse(
                    tool_request_id=request.tool_request_id,
                    execution_id=request.execution_id,
                    tool_name=self.name,
                    status=ToolStatus.ERROR,
                    error=f"File not found: {rel_path}",
                    duration_ms=(time.perf_counter() - start_t) * 1000.0,
                )
            content = safe_path.read_text(encoding="utf-8")
            return ToolResponse(
                tool_request_id=request.tool_request_id,
                execution_id=request.execution_id,
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output=content,
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


class WriteFileTool(ITool):
    """Tool to write text content to a file inside the workspace."""

    def __init__(self, workspace_root: str = "./workspace"):
        self.workspace_root = workspace_root

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write_file",
            description="Writes text content to a file, creating directories if needed.",
            parameters={
                "path": {"type": "string", "description": "Relative path to file"},
                "content": {"type": "string", "description": "Text content to write"},
            },
            danger_level="normal",
        )

    def execute(self, request: ToolRequest) -> ToolResponse:
        start_t = time.perf_counter()
        rel_path = request.arguments.get("path")
        content = request.arguments.get("content", "")

        if not rel_path:
            return ToolResponse(
                tool_request_id=request.tool_request_id,
                execution_id=request.execution_id,
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error="Missing required argument: 'path'",
                duration_ms=(time.perf_counter() - start_t) * 1000.0,
            )

        try:
            safe_path = _resolve_safe_path(rel_path, self.workspace_root)
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            safe_path.write_text(content, encoding="utf-8")
            return ToolResponse(
                tool_request_id=request.tool_request_id,
                execution_id=request.execution_id,
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output={"path": rel_path, "bytes_written": len(content.encode("utf-8"))},
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


class ListFilesTool(ITool):
    """Tool to inspect directories and list files in workspace."""

    def __init__(self, workspace_root: str = "./workspace"):
        self.workspace_root = workspace_root

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_files",
            description="Lists files and subdirectories within a directory path.",
            parameters={
                "directory": {"type": "string", "description": "Relative path to directory", "default": "."},
            },
            danger_level="read_only",
        )

    def execute(self, request: ToolRequest) -> ToolResponse:
        start_t = time.perf_counter()
        rel_dir = request.arguments.get("directory", ".")

        try:
            safe_path = _resolve_safe_path(rel_dir, self.workspace_root)
            if not safe_path.exists() or not safe_path.is_dir():
                return ToolResponse(
                    tool_request_id=request.tool_request_id,
                    execution_id=request.execution_id,
                    tool_name=self.name,
                    status=ToolStatus.ERROR,
                    error=f"Directory not found: {rel_dir}",
                    duration_ms=(time.perf_counter() - start_t) * 1000.0,
                )

            items = []
            for entry in safe_path.iterdir():
                items.append({
                    "name": entry.name,
                    "is_dir": entry.is_dir(),
                    "size_bytes": entry.stat().st_size if entry.is_file() else None,
                })

            return ToolResponse(
                tool_request_id=request.tool_request_id,
                execution_id=request.execution_id,
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output={"directory": rel_dir, "entries": items},
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
