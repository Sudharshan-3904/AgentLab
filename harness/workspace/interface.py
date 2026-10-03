"""Workspace manager interface and contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel, Field


class WorkspaceStatus(BaseModel):
    current_commit: Optional[str] = None
    modified_files: List[str] = Field(default_factory=list)
    untracked_files: List[str] = Field(default_factory=list)
    deleted_files: List[str] = Field(default_factory=list)


class CheckpointRecord(BaseModel):
    checkpoint_id: str
    execution_id: str
    commit_hash: str
    message: str
    timestamp: str


class IWorkspaceManager(ABC):
    """Abstract interface for workspace revision control and rollbacks."""

    @abstractmethod
    def initialize(self, root_path: str) -> None:
        """Initialize or verify Git tracking in workspace root."""
        pass

    @abstractmethod
    def create_checkpoint(self, execution_id: str, message: str) -> CheckpointRecord:
        """Create a checkpoint commit of current workspace state."""
        pass

    @abstractmethod
    def rollback(self, checkpoint_id: str) -> bool:
        """Rollback workspace to specified checkpoint."""
        pass

    @abstractmethod
    def get_diff(self, base_ref: Optional[str] = None) -> str:
        """Get git diff from base revision or working tree."""
        pass

    @abstractmethod
    def get_status(self) -> WorkspaceStatus:
        """Inspect current modified, untracked, and deleted files."""
        pass
