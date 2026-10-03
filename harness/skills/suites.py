"""Specialized MVP skill suites: Planning, Coding, Testing, and Debugging."""

from __future__ import annotations

from typing import List, Optional
from harness.skills.base import BaseSkillSuite
from harness.tools.interface import ITool


class PlanningSkillSuite(BaseSkillSuite):
    """Skill suite focused on task intake, analysis, decomposition, and planning."""

    DEFAULT_PROMPT = (
        "You are an expert software architect and planner. "
        "Your task is to analyze user requirements, identify constraints, "
        "decompose complex objectives into clear subtasks, and define verification criteria."
    )

    def __init__(self, tools: Optional[List[ITool]] = None):
        super().__init__(
            name="planning",
            description="Decomposes requirements, evaluates architectural constraints, and builds plan.",
            system_prompt=self.DEFAULT_PROMPT,
            tools=tools,
        )


class CodingSkillSuite(BaseSkillSuite):
    """Skill suite focused on implementation, code synthesis, and file modifications."""

    DEFAULT_PROMPT = (
        "You are an expert software engineer. "
        "Your role is to implement planned features with clean, maintainable, modular code. "
        "Modify only necessary files, follow established coding conventions, and prepare for verification."
    )

    def __init__(self, tools: Optional[List[ITool]] = None):
        super().__init__(
            name="coding",
            description="Writes, edits, refactors code and manages project files.",
            system_prompt=self.DEFAULT_PROMPT,
            tools=tools,
        )


class TestingSkillSuite(BaseSkillSuite):
    """Skill suite focused on test creation, test execution, and verification."""

    __test__ = False

    DEFAULT_PROMPT = (
        "You are an expert QA and test engineer. "
        "Your role is to write comprehensive tests, execute test suites, "
        "verify implementation correctness against constraints, and report defect details."
    )

    def __init__(self, tools: Optional[List[ITool]] = None):
        super().__init__(
            name="testing",
            description="Executes test suites and verifies functionality against criteria.",
            system_prompt=self.DEFAULT_PROMPT,
            tools=tools,
        )


class DebuggingSkillSuite(BaseSkillSuite):
    """Skill suite focused on failure diagnosis, root-cause analysis, and recovery fixes."""

    DEFAULT_PROMPT = (
        "You are an expert software troubleshooter and debugger. "
        "Your role is to analyze error traces, isolate root causes of test or runtime failures, "
        "and produce targeted fixes to restore functionality."
    )

    def __init__(self, tools: Optional[List[ITool]] = None):
        super().__init__(
            name="debugging",
            description="Diagnoses errors, investigates failures, and formulates targeted fixes.",
            system_prompt=self.DEFAULT_PROMPT,
            tools=tools,
        )
