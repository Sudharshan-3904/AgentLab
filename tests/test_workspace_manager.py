"""Tests for WorkspaceManager checkpoints, diffs, status, and rollback."""

from pathlib import Path
import pytest

from harness.workspace.manager import WorkspaceManager


def test_workspace_manager_initialization(tmp_path: Path):
    ws_dir = tmp_path / "test_workspace"
    manager = WorkspaceManager(ws_dir)
    manager.initialize()

    assert (ws_dir / ".git").exists()
    status = manager.get_status()
    assert status.current_commit is not None
    assert len(status.modified_files) == 0


def test_workspace_manager_checkpoint_and_rollback(tmp_path: Path):
    ws_dir = tmp_path / "rollback_workspace"
    manager = WorkspaceManager(ws_dir)
    manager.initialize()

    # Create file A
    file_a = ws_dir / "file_a.txt"
    file_a.write_text("initial version", encoding="utf-8")

    # Checkpoint 1
    cp1 = manager.create_checkpoint("exec-w1", "Add initial file_a")
    assert cp1.checkpoint_id.startswith("cp-")
    assert cp1.commit_hash is not None

    # Now modify file A, create file B
    file_a.write_text("broken modification", encoding="utf-8")
    file_b = ws_dir / "file_b.txt"
    file_b.write_text("unwanted file", encoding="utf-8")

    status_before_rollback = manager.get_status()
    assert "file_a.txt" in status_before_rollback.modified_files
    assert "file_b.txt" in status_before_rollback.untracked_files

    # Execute rollback to Checkpoint 1
    success = manager.rollback(cp1.checkpoint_id)
    assert success is True

    # Verify state reverted cleanly
    assert file_a.read_text(encoding="utf-8") == "initial version"
    assert not file_b.exists()

    status_after_rollback = manager.get_status()
    assert len(status_after_rollback.modified_files) == 0
    assert len(status_after_rollback.untracked_files) == 0


def test_workspace_manager_diff(tmp_path: Path):
    ws_dir = tmp_path / "diff_workspace"
    manager = WorkspaceManager(ws_dir)
    manager.initialize()

    code_file = ws_dir / "calc.py"
    code_file.write_text("def add(a, b): return a + b\n", encoding="utf-8")
    cp = manager.create_checkpoint("exec-w2", "Base calc implementation")

    code_file.write_text("def add(a, b): return a + b + 1\n", encoding="utf-8")
    diff = manager.get_diff()
    assert "+def add(a, b): return a + b + 1" in diff
