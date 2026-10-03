"""Integration test verifying Phase 4 Exit Criteria:
The model can safely perform basic coding tasks using the tool runtime.
"""

from pathlib import Path
import subprocess
import pytest

from harness.core.config import AutonomyLevel, HarnessConfig
from harness.core.events import EventType
from harness.core.harness import Harness
from harness.core.state import ExecutionState
from harness.security.policy import PolicyEngine
from harness.tools.fs import ListFilesTool, ReadFileTool, WriteFileTool
from harness.tools.git import GitTool
from harness.tools.interface import ToolStatus
from harness.tools.shell import ShellTool
from harness.tools.testing import TestRunnerTool
from harness.tasks.task import Task


def test_phase4_exit_criteria_safe_coding_task(tmp_path: Path):
    """
    Exit Criteria:
    The model can safely perform basic coding tasks with policy evaluation,
    request/response correlation, and full event ledger recording.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db_file = tmp_path / "tool_runtime.db"

    # Initialize git repo in workspace for GitTool testing
    subprocess.run("git init", shell=True, cwd=str(workspace), capture_output=True)

    # Configure harness with autonomous mode for smooth execution within workspace
    config = HarnessConfig()
    config.execution.autonomy = AutonomyLevel.AUTONOMOUS
    config.workspace.root = str(workspace)

    policy = PolicyEngine()
    harness = Harness(
        config=config,
        db_path=str(db_file),
        policy_engine=policy,
    )

    # Register tools
    harness.register_tool(WriteFileTool(workspace_root=str(workspace)))
    harness.register_tool(ReadFileTool(workspace_root=str(workspace)))
    harness.register_tool(ListFilesTool(workspace_root=str(workspace)))
    harness.register_tool(ShellTool(workspace_root=str(workspace)))
    harness.register_tool(GitTool(workspace_root=str(workspace)))
    harness.register_tool(TestRunnerTool(workspace_root=str(workspace)))

    task = Task(objective="Implement fibonacci utility and verified unit tests")
    exec_mgr = harness.create_execution(task)
    execution_id = exec_mgr.execution_id

    exec_mgr.transition_to(ExecutionState.PLANNING, reason="Decompose fibonacci task")
    exec_mgr.transition_to(ExecutionState.EXECUTING, reason="Implement code and tests")

    # 1. Step 1: Write source code file
    code_content = (
        "def fib(n: int) -> int:\n"
        "    if n <= 0: return 0\n"
        "    if n == 1: return 1\n"
        "    a, b = 0, 1\n"
        "    for _ in range(2, n + 1):\n"
        "        a, b = b, a + b\n"
        "    return b\n"
    )
    write_code_res = exec_mgr.execute_tool(
        harness.tools["write_file"],
        {"path": "fibonacci.py", "content": code_content},
    )
    assert write_code_res.status == ToolStatus.SUCCESS
    assert (workspace / "fibonacci.py").exists()

    # 2. Step 2: Write test file
    test_content = (
        "from fibonacci import fib\n\n"
        "def test_fib_zero():\n"
        "    assert fib(0) == 0\n\n"
        "def test_fib_base():\n"
        "    assert fib(1) == 1\n\n"
        "def test_fib_sequence():\n"
        "    assert fib(5) == 5\n"
        "    assert fib(6) == 8\n"
    )
    write_test_res = exec_mgr.execute_tool(
        harness.tools["write_file"],
        {"path": "test_fibonacci.py", "content": test_content},
    )
    assert write_test_res.status == ToolStatus.SUCCESS
    assert (workspace / "test_fibonacci.py").exists()

    # 3. Step 3: Read back file to verify content
    read_res = exec_mgr.execute_tool(
        harness.tools["read_file"],
        {"path": "fibonacci.py"},
    )
    assert read_res.status == ToolStatus.SUCCESS
    assert "def fib" in read_res.output

    # 4. Step 4: List workspace files
    list_res = exec_mgr.execute_tool(
        harness.tools["list_files"],
        {"directory": "."},
    )
    assert list_res.status == ToolStatus.SUCCESS
    file_names = [e["name"] for e in list_res.output["entries"]]
    assert "fibonacci.py" in file_names
    assert "test_fibonacci.py" in file_names

    # 5. Step 5: Run tests with TestRunnerTool
    exec_mgr.transition_to(ExecutionState.VERIFYING, reason="Run automated test suite")
    test_res = exec_mgr.execute_tool(
        harness.tools["test_runner"],
        {"test_path": "test_fibonacci.py"},
    )
    assert test_res.status == ToolStatus.SUCCESS
    assert test_res.output["all_passed"] is True
    assert test_res.output["passed_count"] == 3

    # 6. Step 6: Git add & status check
    git_res = exec_mgr.execute_tool(
        harness.tools["git"],
        {"operation": "status", "args": "--short"},
    )
    assert git_res.status == ToolStatus.SUCCESS

    # 7. Step 7: Attempt unsafe action (path traversal) - verify policy denial
    unsafe_res = exec_mgr.execute_tool(
        harness.tools["read_file"],
        {"path": "../../etc/shadow"},
    )
    assert unsafe_res.status == ToolStatus.DENIED
    assert "escapes workspace boundary" in unsafe_res.error

    # 8. Verify all event correlation in SQLite ledger
    events = harness.get_events(execution_id)
    tool_reqs = [e for e in events if e.type == EventType.TOOL_REQUEST]
    tool_decisions = [e for e in events if e.type == EventType.TOOL_POLICY_DECISION]
    tool_resps = [e for e in events if e.type == EventType.TOOL_RESPONSE]

    # Exactly 7 tool invocations performed
    assert len(tool_reqs) == 7
    assert len(tool_decisions) == 7
    assert len(tool_resps) == 7

    # Ensure every single request has matching decision and response correlation IDs
    for req_e, dec_e, resp_e in zip(tool_reqs, tool_decisions, tool_resps):
        assert req_e.correlation_id == dec_e.correlation_id == resp_e.correlation_id

    # Complete execution successfully
    exec_mgr.complete()
    assert exec_mgr.is_finished is True

    harness.close()
