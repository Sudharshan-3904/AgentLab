"""Task intake and representation models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class Task(BaseModel):
    """Represents a validated user development task submitted to the harness."""

    #TODO - EXP-010: Preserve source/trust labels for repository, test, tool, and external content before prompt-injection evaluation.

    task_id: str = Field(default_factory=lambda: f"task-{uuid.uuid4().hex[:8]}")
    objective: str = Field(..., min_length=1, description="Primary goal or description of task")
    constraints: List[str] = Field(default_factory=list, description="Rules or restrictions")
    requested_output: Optional[str] = Field(default=None, description="Expected artifacts or output format")
    project_context: Dict[str, Any] = Field(default_factory=dict, description="Metadata or context about project")
    user_preferences: Dict[str, Any] = Field(default_factory=dict, description="Autonomy, style, or tool preferences")
    clarification_questions: List[str] = Field(default_factory=list, description="Open clarifications needed from user")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_prompt(cls, prompt: str, **kwargs) -> Task:
        """Create a Task from a user text prompt."""
        return cls(objective=prompt.strip(), **kwargs)
