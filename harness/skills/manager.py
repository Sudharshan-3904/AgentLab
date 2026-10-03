"""Skill Manager orchestrating single active skill suite and transitions."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
from harness.core.events import EventType
from harness.skills.interface import ISkillSuite, SkillContext, SkillTransitionSummary
from harness.tools.interface import ITool


class SkillManager:
    """Maintains exactly one active skill suite and executes clean context transitions."""

    def __init__(
        self,
        execution_id: str,
        workspace_root: str = "./workspace",
        on_event: Optional[Callable[[EventType, str, Dict[str, Any]], None]] = None,
    ):
        self.execution_id = execution_id
        self.workspace_root = workspace_root
        self._on_event = on_event

        self._registered_skills: Dict[str, ISkillSuite] = {}
        self.active_skill: Optional[ISkillSuite] = None
        self.latest_continuity_summary: Optional[SkillTransitionSummary] = None
        self.transition_history: List[Dict[str, Any]] = []

    def register_skill(self, skill: ISkillSuite) -> None:
        """Register a skill suite."""
        self._registered_skills[skill.name] = skill

    def get_skill(self, name: str) -> Optional[ISkillSuite]:
        """Lookup registered skill by name."""
        return self._registered_skills.get(name)

    @property
    def active_tools(self) -> List[ITool]:
        """Tools exposed by the currently active skill suite."""
        return self.active_skill.tools if self.active_skill else []

    @property
    def active_system_prompt(self) -> str:
        """System prompt exposed by the currently active skill suite."""
        return self.active_skill.system_prompt if self.active_skill else ""

    def transition_to(
        self,
        target_skill_name: str,
        scratchpad_data: Optional[Dict[str, Any]] = None,
    ) -> SkillTransitionSummary:
        """Switch active skill suite to target_skill_name, maintaining task continuity."""
        if target_skill_name not in self._registered_skills:
            raise ValueError(
                f"Cannot transition to unregistered skill: '{target_skill_name}'. "
                f"Available: {list(self._registered_skills.keys())}"
            )

        old_skill = self.active_skill
        if old_skill:
            summary = old_skill.on_unload()
            summary.target_skill = target_skill_name
            self.latest_continuity_summary = summary

            if self._on_event:
                self._on_event(
                    EventType.SKILL_UNLOADED,
                    "skill_manager",
                    {
                        "unloaded_skill": old_skill.name,
                        "target_skill": target_skill_name,
                        "summary": summary.model_dump(),
                    },
                )

        target_skill = self._registered_skills[target_skill_name]
        context = SkillContext(
            execution_id=self.execution_id,
            skill_name=target_skill_name,
            continuity_summary=self.latest_continuity_summary,
            scratchpad_data=scratchpad_data or {},
            workspace_root=self.workspace_root,
        )
        target_skill.on_load(context)
        self.active_skill = target_skill

        self.transition_history.append({
            "from_skill": old_skill.name if old_skill else None,
            "to_skill": target_skill_name,
        })

        if self._on_event:
            self._on_event(
                EventType.SKILL_LOADED,
                "skill_manager",
                {"loaded_skill": target_skill_name},
            )

        return self.latest_continuity_summary or SkillTransitionSummary(
            source_skill="init",
            target_skill=target_skill_name,
            objective=scratchpad_data.get("objective", "") if scratchpad_data else "",
        )
