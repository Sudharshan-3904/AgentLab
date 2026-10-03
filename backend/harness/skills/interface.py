"""Skill suite interface and continuity summary contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from harness.tools.interface import ITool


class SkillType(str, Enum):
    """Standard MVP skill suite types."""
    PLANNING = "planning"
    CODING = "coding"
    TESTING = "testing"
    DEBUGGING = "debugging"


class SkillTransitionSummary(BaseModel):
    """Structured summary passed forward across skill transitions to maintain continuity."""
    source_skill: str
    target_skill: Optional[str] = None
    objective: str
    completed_work: List[str] = Field(default_factory=list)
    pending_work: List[str] = Field(default_factory=list)
    relevant_decisions: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    discovered_facts: List[str] = Field(default_factory=list)
    known_failures: List[str] = Field(default_factory=list)
    next_verification_step: Optional[str] = None


class SkillContext(BaseModel):
    """Contextual information provided to a skill suite upon loading."""
    execution_id: str
    skill_name: str
    continuity_summary: Optional[SkillTransitionSummary] = None
    scratchpad_data: Dict[str, Any] = Field(default_factory=dict)
    workspace_root: str = "./workspace"


class ISkillSuite(ABC):
    """Abstract interface for a loadable behavioral skill suite."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the skill suite (e.g. 'planning', 'coding')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of the skill's purpose and scope."""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System instruction prompt specialized for this skill suite."""
        pass

    @property
    @abstractmethod
    def tools(self) -> List[ITool]:
        """List of tools available while this skill suite is active."""
        pass

    @abstractmethod
    def on_load(self, context: SkillContext) -> None:
        """Lifecycle hook invoked when the skill suite is loaded."""
        pass

    @abstractmethod
    def on_unload(self) -> SkillTransitionSummary:
        """Lifecycle hook invoked when unloading to yield continuity summary."""
        pass
