"""Unit test for ExecutionManager automated recovery and resolution lifecycle."""

from pathlib import Path
import pytest

from harness.core.config import HarnessConfig
from harness.core.events import EventType
from harness.core.state import ExecutionState
from harness.execution.manager import ExecutionManager
from harness.ledger.sqlite import SQLiteEventLedger
from harness.tasks.task import Task
from harness.workspace.manager import WorkspaceManager
from tests.test_interfaces import MockPolicyEngine


def test_execution_manager_recovery_and_resolution(tmp_path: Path):
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()

    # Workspace setup with initial git checkpoint
    wm = WorkspaceManager(str(ws_dir))
    wm.initialize()

    test_file = ws_dir / "math_helper.py"
    test_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    task = Task.from_prompt("Add multiplication to math_helper.py")
    config = HarnessConfig()
    config.workspace.root = str(ws_dir)
    config.execution.max_recovery_attempts = 2

    ledger = SQLiteEventLedger(":memory:")
    policy = MockPolicyEngine()

    manager = ExecutionManager(
        task=task,
        config=config,
        ledger=ledger,
        policy_engine=policy,
        workspace_manager=wm,
    )

    manager.transition_to(ExecutionState.PLANNING)
    manager.transition_to(ExecutionState.EXECUTING)

    # Create baseline checkpoint
    cp = manager.create_checkpoint("Working baseline commit")
    assert cp is not None

    # Simulate buggy edit by agent
    test_file.write_text("def add(a, b):\n    return a + \n", encoding="utf-8")  # syntax error

    # Trigger recovery
    recovered = manager.trigger_recovery(
        failure_reason="SyntaxError: invalid syntax on line 2",
        error_details="SyntaxError: unexpected EOF while parsing",
    )
    assert recovered is True
    assert manager.current_state == ExecutionState.RECOVERY
    assert manager.recovery_attempts == 1
    assert manager.last_recovery_result is not None
    assert manager.last_recovery_result.rollback_performed is True

    # Verify rollback restored the original working content
    assert test_file.read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"

    # Resolve recovery
    manager.resolve_recovery("Fixed syntax error by restoring clean baseline and retrying")
    assert manager.current_state == ExecutionState.EXECUTING
    assert manager.scratchpad.recovery_history[0].resolved is True

    # Advance to verification and completion
    manager.transition_to(ExecutionState.VERIFYING)
    manager.complete("Multiplication added and verified")
    assert manager.current_state == ExecutionState.COMPLETED

    # Check ledger events
    events = ledger.get_events(manager.execution_id)
    event_types = [e.type for e in events]
    assert EventType.RECOVERY_STARTED in event_types
    assert EventType.RECOVERY_COMPLETED in event_types
    assert EventType.ROLLBACK in event_types
