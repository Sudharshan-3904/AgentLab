"""Tests for workspace checkpoint and rollback event ledger integration."""

from pathlib import Path
import pytest

from harness.core.config import HarnessConfig
from harness.core.events import EventType
from harness.core.harness import Harness
from harness.tasks.task import Task
from harness.workspace.manager import WorkspaceManager


def test_checkpoint_and_rollback_ledger_events(tmp_path: Path):
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    db_file = tmp_path / "ledger.db"

    config = HarnessConfig()
    config.workspace.root = str(ws_dir)
    config.workspace.git_enabled = True

    harness = Harness(config=config, db_path=str(db_file))
    exec_mgr = harness.create_execution(Task(objective="Test rollback telemetry"))

    # Initial file and checkpoint
    test_file = ws_dir / "index.js"
    test_file.write_text("console.log('v1');", encoding="utf-8")

    cp = exec_mgr.create_checkpoint("Initial v1 checkpoint")
    assert cp is not None
    assert cp.commit_hash is not None

    # Check CHECKPOINT event in ledger
    events = harness.get_events(exec_mgr.execution_id)
    cp_events = [e for e in events if e.type == EventType.CHECKPOINT]
    assert len(cp_events) == 1
    assert cp_events[0].payload["checkpoint_id"] == cp.checkpoint_id
    assert cp_events[0].payload["commit_hash"] == cp.commit_hash

    # Modify file
    test_file.write_text("console.log('broken v2');", encoding="utf-8")
    status = exec_mgr.get_workspace_status()
    assert "index.js" in status.modified_files

    # Rollback to checkpoint
    success = exec_mgr.rollback(cp.checkpoint_id)
    assert success is True
    assert test_file.read_text(encoding="utf-8") == "console.log('v1');"

    # Check ROLLBACK event in ledger
    events_after = harness.get_events(exec_mgr.execution_id)
    rb_events = [e for e in events_after if e.type == EventType.ROLLBACK]
    assert len(rb_events) == 1
    assert rb_events[0].payload["checkpoint_id"] == cp.checkpoint_id
    assert rb_events[0].payload["success"] is True

    harness.close()
