"""Unit tests for the initial 6 harness tools."""

from pathlib import Path
import pytest

from harness.tools.fs import ListFilesTool, ReadFileTool, WriteFileTool
from harness.tools.git import GitTool
from harness.tools.interface import ToolRequest, ToolStatus
from harness.tools.shell import ShellTool
from harness.tools.testing import TestRunnerTool


def test_write_and_read_file_tool(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    write_tool = WriteFileTool(workspace_root=str(workspace))
    read_tool = ReadFileTool(workspace_root=str(workspace))

    # Write file
    w_req = ToolRequest(
        execution_id="exec-t1",
        tool_name="write_file",
        arguments={"path": "src/app.py", "content": "print('hello from tool')"},
    )
    w_res = write_tool.execute(w_req)
    assert w_res.status == ToolStatus.SUCCESS
    assert w_res.output["bytes_written"] > 0
    assert (workspace / "src" / "app.py").exists()

    # Read file
    r_req = ToolRequest(
        execution_id="exec-t1",
        tool_name="read_file",
        arguments={"path": "src/app.py"},
    )
    r_res = read_tool.execute(r_req)
    assert r_res.status == ToolStatus.SUCCESS
    assert r_res.output == "print('hello from tool')"


def test_fs_tools_path_traversal_protection(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("secret", encoding="utf-8")

    read_tool = ReadFileTool(workspace_root=str(workspace))
    req = ToolRequest(
        execution_id="exec-t2",
        tool_name="read_file",
        arguments={"path": "../secret.txt"},
    )
    res = read_tool.execute(req)
    assert res.status == ToolStatus.ERROR
    assert "escapes workspace root" in res.error


def test_list_files_tool(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "file1.txt").write_text("123", encoding="utf-8")
    (workspace / "subdir").mkdir()

    list_tool = ListFilesTool(workspace_root=str(workspace))
    req = ToolRequest(
        execution_id="exec-t3",
        tool_name="list_files",
        arguments={"directory": "."},
    )
    res = list_tool.execute(req)
    assert res.status == ToolStatus.SUCCESS
    entry_names = [e["name"] for e in res.output["entries"]]
    assert "file1.txt" in entry_names
    assert "subdir" in entry_names


def test_shell_tool(tmp_path: Path):
    shell_tool = ShellTool(workspace_root=str(tmp_path))
    req = ToolRequest(
        execution_id="exec-t4",
        tool_name="shell",
        arguments={"command": "python -c \"print('shell output')\""},
    )
    res = shell_tool.execute(req)
    assert res.status == ToolStatus.SUCCESS
    assert "shell output" in res.output["stdout"]


def test_git_tool(tmp_path: Path):
    import subprocess
    # Init a git repo in tmp_path
    subprocess.run("git init", shell=True, cwd=str(tmp_path), capture_output=True)

    git_tool = GitTool(workspace_root=str(tmp_path))
    req = ToolRequest(
        execution_id="exec-t5",
        tool_name="git",
        arguments={"operation": "status"},
    )
    res = git_tool.execute(req)
    assert res.status == ToolStatus.SUCCESS
    assert "On branch" in res.output["stdout"] or "branch" in res.output["stdout"]


def test_test_runner_tool(tmp_path: Path):
    # Create a small valid test file in tmp_path
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text(
        "def test_pass(): assert 1 + 1 == 2\n",
        encoding="utf-8"
    )

    test_tool = TestRunnerTool(workspace_root=str(tmp_path))
    req = ToolRequest(
        execution_id="exec-t6",
        tool_name="test_runner",
        arguments={"test_path": "tests/test_sample.py"},
    )
    res = test_tool.execute(req)
    assert res.status == ToolStatus.SUCCESS
    assert res.output["all_passed"] is True
    assert res.output["passed_count"] >= 1
