"""Workspace Manager implementing Git checkpoints, diffs, status, and rollbacks."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time
from typing import Dict, List, Optional
import uuid

from harness.workspace.interface import (
    CheckpointRecord,
    IWorkspaceManager,
    WorkspaceStatus,
)


class WorkspaceManager(IWorkspaceManager):
    """Manages workspace revisions, Git checkpoints, diffs, and rollback restorations."""

    def __init__(self, workspace_root: str | Path = "./workspace"):
        self.workspace_root = str(Path(workspace_root).resolve())
        Path(self.workspace_root).mkdir(parents=True, exist_ok=True)
        self._checkpoints: Dict[str, CheckpointRecord] = {}

    @property
    def checkpoints(self) -> List[CheckpointRecord]:
        """Return list of created checkpoints."""
        return list(self._checkpoints.values())

    def _run_git(self, args: List[str]) -> subprocess.CompletedProcess:
        """Run git command inside workspace root."""
        return subprocess.run(
            ["git"] + args,
            cwd=self.workspace_root,
            capture_output=True,
            text=True,
            check=False,
        )

    def initialize(self, root_path: Optional[str] = None) -> None:
        """Initialize or verify Git tracking inside workspace root."""
        if root_path:
            self.workspace_root = str(Path(root_path).resolve())
            Path(self.workspace_root).mkdir(parents=True, exist_ok=True)

        git_dir = Path(self.workspace_root) / ".git"
        if not git_dir.exists():
            self._run_git(["init"])

        # Configure local git user if not present
        res_name = self._run_git(["config", "user.name"])
        if not res_name.stdout.strip():
            self._run_git(["config", "user.name", "Harness Agent"])
            self._run_git(["config", "user.email", "agent@local.harness"])

        # Ensure initial commit exists
        head_res = self._run_git(["rev-parse", "--verify", "HEAD"])
        if head_res.returncode != 0:
            # Empty initial commit
            self._run_git(["commit", "--allow-empty", "-m", "chore: initial workspace commit"])

    def create_checkpoint(self, execution_id: str, message: str) -> CheckpointRecord:
        """Create a git checkpoint commit of current workspace state."""
        self.initialize()
        self._run_git(["add", "-A"])

        checkpoint_id = f"cp-{uuid.uuid4().hex[:8]}"
        commit_msg = f"[checkpoint:{checkpoint_id}] {message}"
        commit_res = self._run_git(["commit", "--allow-empty", "-m", commit_msg])

        rev_res = self._run_git(["rev-parse", "HEAD"])
        commit_hash = rev_res.stdout.strip()
        timestamp = datetime.now(timezone.utc).isoformat()

        record = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            execution_id=execution_id,
            commit_hash=commit_hash,
            message=message,
            timestamp=timestamp,
        )
        self._checkpoints[checkpoint_id] = record
        return record

    def rollback(self, checkpoint_id: str) -> bool:
        """Revert workspace to specified checkpoint commit, cleaning untracked files."""
        target_hash = None
        if checkpoint_id in self._checkpoints:
            target_hash = self._checkpoints[checkpoint_id].commit_hash
        else:
            # Assume checkpoint_id is a direct commit hash
            target_hash = checkpoint_id

        reset_res = self._run_git(["reset", "--hard", target_hash])
        clean_res = self._run_git(["clean", "-fd"])

        return reset_res.returncode == 0 and clean_res.returncode == 0

    def get_diff(self, base_ref: Optional[str] = None) -> str:
        """Compute git diff from specified base_ref or HEAD."""
        cmd = ["diff"]
        if base_ref:
            cmd.append(base_ref)
        else:
            cmd.append("HEAD")
        res = self._run_git(cmd)
        return res.stdout

    def get_status(self) -> WorkspaceStatus:
        """Inspect modified, untracked, and deleted files in workspace."""
        rev_res = self._run_git(["rev-parse", "HEAD"])
        current_commit = rev_res.stdout.strip() if rev_res.returncode == 0 else None

        status_res = self._run_git(["status", "--porcelain"])
        modified_files: List[str] = []
        untracked_files: List[str] = []
        deleted_files: List[str] = []

        for line in status_res.stdout.splitlines():
            if not line:
                continue
            code = line[:2]
            filename = line[3:].strip()
            if "??" in code:
                untracked_files.append(filename)
            elif "D" in code:
                deleted_files.append(filename)
            else:
                modified_files.append(filename)

        return WorkspaceStatus(
            current_commit=current_commit,
            modified_files=modified_files,
            untracked_files=untracked_files,
            deleted_files=deleted_files,
        )
