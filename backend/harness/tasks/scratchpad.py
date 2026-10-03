"""Structured execution scratchpad outside model context."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RecoveryEntry(BaseModel):
    attempt: int
    failure_description: str
    action_taken: str
    resolved: bool = False


class Scratchpad(BaseModel):
    """Execution scratchpad maintaining structured execution progress and state."""

    objective: str
    constraints: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    subtasks: List[str] = Field(default_factory=list)
    verification: List[str] = Field(default_factory=list)
    clarifications: List[str] = Field(default_factory=list)
    completed: List[str] = Field(default_factory=list)
    failed: List[str] = Field(default_factory=list)
    pending: List[str] = Field(default_factory=list)
    recovery_history: List[RecoveryEntry] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)

    def append_note(self, note: str) -> None:
        """Record an informational note or user feedback."""
        self.notes.append(note)

    def set_subtasks(self, subtasks: List[str]) -> None:
        """Set decomposed subtasks and populate pending queue."""
        self.subtasks = list(subtasks)
        self.pending = list(subtasks)

    def complete_subtask(self, subtask: str) -> None:
        """Mark a subtask as completed."""
        if subtask in self.pending:
            self.pending.remove(subtask)
        if subtask not in self.completed:
            self.completed.append(subtask)

    mark_completed = complete_subtask

    def fail_subtask(self, subtask: str, reason: str = "") -> None:
        """Mark a subtask as failed."""
        if subtask in self.pending:
            self.pending.remove(subtask)
        failure_str = f"{subtask}: {reason}" if reason else subtask
        if failure_str not in self.failed:
            self.failed.append(failure_str)

    def add_recovery(self, attempt: int, failure: str, action: str, resolved: bool = False) -> None:
        """Record an automated recovery attempt."""
        self.recovery_history.append(
            RecoveryEntry(
                attempt=attempt,
                failure_description=failure,
                action_taken=action,
                resolved=resolved,
            )
        )
