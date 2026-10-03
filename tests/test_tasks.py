"""Tests for Task intake model and Scratchpad."""

import pytest
from harness.tasks.scratchpad import Scratchpad
from harness.tasks.task import Task


def test_task_creation_and_defaults():
    task = Task.from_prompt("Build an API service in FastAPI")
    assert task.objective == "Build an API service in FastAPI"
    assert task.task_id.startswith("task-")
    assert task.constraints == []
    assert task.created_at is not None


def test_task_with_constraints_and_preferences():
    task = Task(
        objective="Refactor auth layer",
        constraints=["Do not modify DB schema", "Maintain backward compatibility"],
        user_preferences={"autonomy": "balanced"},
    )
    assert len(task.constraints) == 2
    assert task.user_preferences["autonomy"] == "balanced"


def test_scratchpad_lifecycle_and_subtasks():
    sp = Scratchpad(objective="Implement logging system")
    assert sp.objective == "Implement logging system"
    assert sp.subtasks == []

    sp.set_subtasks(["task-1: add logger config", "task-2: add middleware"])
    assert len(sp.pending) == 2
    assert len(sp.completed) == 0

    sp.complete_subtask("task-1: add logger config")
    assert len(sp.pending) == 1
    assert "task-1: add logger config" in sp.completed

    sp.fail_subtask("task-2: add middleware", "ImportError on middleware")
    assert len(sp.pending) == 0
    assert len(sp.failed) == 1
    assert "ImportError" in sp.failed[0]


def test_scratchpad_recovery_history():
    sp = Scratchpad(objective="Deploy script")
    sp.add_recovery(
        attempt=1,
        failure="Port 8000 already in use",
        action="Switched to port 8001",
        resolved=True,
    )
    assert len(sp.recovery_history) == 1
    assert sp.recovery_history[0].attempt == 1
    assert sp.recovery_history[0].resolved is True
