"""Integration test verifying Phase 5 Exit Criteria:
A failed execution can be reverted to a known checkpoint.
"""

from pathlib import Path
import pytest

from harness.core.config import AutonomyLevel, HarnessConfig
from harness.core.events import EventType
from harness.core.harness import Harness
from harness.core.state import ExecutionState
from harness.security.policy import PolicyEngine
from harness.tasks.task import Task
from harness.tools.fs import ReadFileTool, WriteFileTool
from harness.tools.interface import ToolStatus
from harness.tools.testing import TestRunnerTool


def test_phase5_exit_criteria_rollback_on_failure(tmp_path: Path):
    """
    Exit Criteria:
    A failed execution can be reverted to a known checkpoint.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db_file = tmp_path / "rollback_integration.db"

    config = HarnessConfig()
    config.execution.autonomy = AutonomyLevel.AUTONOMOUS
    config.workspace.root = str(workspace)
    config.workspace.git_enabled = True

    harness = Harness(config=config, db_path=str(db_file), policy_engine=PolicyEngine())
    harness.register_tool(WriteFileTool(workspace_root=str(workspace)))
    harness.register_tool(ReadFileTool(workspace_root=str(workspace)))
    harness.register_tool(TestRunnerTool(workspace_root=str(workspace)))

    task = Task(objective="Implement verified string utility with rollback capability")
    exec_mgr = harness.create_execution(task)
    execution_id = exec_mgr.execution_id

    # 1. Setup known good working code and tests
    code_path = workspace / "string_utils.py"
    test_path = workspace / "test_string_utils.py"

    code_path.write_text("def reverse_str(s: str) -> str: return s[::-1]\n", encoding="utf-8")
    test_path.write_text(
        "from string_utils import reverse_str\n\n"
        "def test_reverse(): assert reverse_str('hello') == 'olleh'\n",
        encoding="utf-8"
    )

    # Verify tests pass initially
    init_test = exec_mgr.execute_tool(harness.tools["test_runner"], {"test_path": "test_string_utils.py"})
    assert init_test.status == ToolStatus.SUCCESS
    assert init_test.output["all_passed"] is True

    # 2. Create Checkpoint 1 (Known good state)
    cp1 = exec_mgr.create_checkpoint("Working string_utils baseline")
    assert cp1 is not None

    # 3. Simulate an agent attempting an optimization that breaks the implementation
    exec_mgr.transition_to(ExecutionState.PLANNING, reason="Refactor string reverse")
    exec_mgr.transition_to(ExecutionState.EXECUTING, reason="Apply broken optimization")

    # Introduce regression in string_utils.py and add junk file
    exec_mgr.execute_tool(
        harness.tools["write_file"],
        {"path": "string_utils.py", "content": "def reverse_str(s: str) -> str: return s # BROKEN BUG\n"},
    )
    exec_mgr.execute_tool(
        harness.tools["write_file"],
        {"path": "unwanted_scratch.tmp", "content": "temporary garbage file"},
    )
    assert (workspace / "unwanted_scratch.tmp").exists()

    # 4. Verify Phase: tests run and FAIL
    exec_mgr.transition_to(ExecutionState.VERIFYING, reason="Verify optimization")
    failing_test = exec_mgr.execute_tool(harness.tools["test_runner"], {"test_path": "test_string_utils.py"})
    assert failing_test.status == ToolStatus.ERROR
    assert failing_test.output["all_passed"] is False

    # 5. Recovery triggers Rollback
    recovered = exec_mgr.trigger_recovery("Optimization failed tests, reverting to known checkpoint")
    assert recovered is True
    assert exec_mgr.current_state == ExecutionState.RECOVERY

    # Perform Rollback
    rollback_success = exec_mgr.rollback(cp1.checkpoint_id)
    assert rollback_success is True

    # 6. Verify workspace restored completely:
    # - string_utils.py restored to working version
    # - unwanted_scratch.tmp deleted
    restored_code = code_path.read_text(encoding="utf-8")
    assert "return s[::-1]" in restored_code
    assert "BROKEN BUG" not in restored_code
    assert not (workspace / "unwanted_scratch.tmp").exists()

    # Working tree is clean
    status = exec_mgr.get_workspace_status()
    assert len(status.modified_files) == 0
    assert len(status.untracked_files) == 0

    # 7. Re-test passes after rollback
    exec_mgr.transition_to(ExecutionState.EXECUTING, reason="Re-evaluating after rollback")
    exec_mgr.transition_to(ExecutionState.VERIFYING, reason="Re-verifying rolled back code")
    retest = exec_mgr.execute_tool(harness.tools["test_runner"], {"test_path": "test_string_utils.py"})
    assert retest.status == ToolStatus.SUCCESS
    assert retest.output["all_passed"] is True

    # 8. Complete execution
    exec_mgr.complete(reason="Execution restored to baseline and verified")
    assert exec_mgr.current_state == ExecutionState.COMPLETED

    # 9. Verify event trail in SQLite ledger
    events = harness.get_events(execution_id)
    event_types = [e.type for e in events]
    assert EventType.CHECKPOINT in event_types
    assert EventType.RECOVERY_STARTED in event_types
    assert EventType.ROLLBACK in event_types
    assert EventType.EXECUTION_COMPLETED in event_types

    harness.close()
