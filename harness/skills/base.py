"""Base implementation for skill suites in Local AI Harness."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from harness.skills.interface import ISkillSuite, SkillContext, SkillTransitionSummary
from harness.tools.interface import ITool


class BaseSkillSuite(ISkillSuite):
    """Abstract base class offering shared utilities for skill suites."""

    def __init__(
        self,
        name: str,
        description: str,
        system_prompt: str,
        tools: Optional[List[ITool]] = None,
    ):
        self._name = name
        self._description = description
        self._system_prompt = system_prompt
        self._tools: List[ITool] = tools or []
        self.context: Optional[SkillContext] = None
        self.completed_items: List[str] = []
        self.pending_items: List[str] = []
        self.decisions: List[str] = []
        self.discovered_facts: List[str] = []
        self.known_failures: List[str] = []
        self.next_verification_step: Optional[str] = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @property
    def tools(self) -> List[ITool]:
        return list(self._tools)

    def add_tool(self, tool: ITool) -> None:
        """Attach a tool to this skill suite."""
        self._tools.append(tool)

    def on_load(self, context: SkillContext) -> None:
        """Rehydrate state from incoming context and continuity summary."""
        self.context = context
        if context.continuity_summary:
            summary = context.continuity_summary
            self.completed_items = list(summary.completed_work)
            self.pending_items = list(summary.pending_work)
            self.decisions = list(summary.relevant_decisions)
            self.discovered_facts = list(summary.discovered_facts)
            self.known_failures = list(summary.known_failures)
            self.next_verification_step = summary.next_verification_step

    def on_unload(self) -> SkillTransitionSummary:
        """Package current progress and decisions into a continuity summary."""
        objective = ""
        if self.context and self.context.continuity_summary:
            objective = self.context.continuity_summary.objective
        elif self.context and "objective" in self.context.scratchpad_data:
            objective = self.context.scratchpad_data["objective"]

        return SkillTransitionSummary(
            source_skill=self.name,
            objective=objective,
            completed_work=list(self.completed_items),
            pending_work=list(self.pending_items),
            relevant_decisions=list(self.decisions),
            constraints=(
                self.context.scratchpad_data.get("constraints", [])
                if self.context
                else []
            ),
            discovered_facts=list(self.discovered_facts),
            known_failures=list(self.known_failures),
            next_verification_step=self.next_verification_step,
        )
