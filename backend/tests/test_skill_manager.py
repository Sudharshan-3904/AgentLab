"""Tests for SkillManager transitions, events, and rehydration."""

import pytest
from harness.core.events import EventType
from harness.skills.manager import SkillManager
from harness.skills.suites import (
    CodingSkillSuite,
    DebuggingSkillSuite,
    PlanningSkillSuite,
    TestingSkillSuite,
)


def test_skill_manager_registration_and_transition():
    events_emitted = []
    manager = SkillManager(
        execution_id="exec-sm-1",
        on_event=lambda ev_type, src, payload: events_emitted.append((ev_type, payload)),
    )

    planning = PlanningSkillSuite()
    coding = CodingSkillSuite()
    manager.register_skill(planning)
    manager.register_skill(coding)

    assert manager.active_skill is None
    assert manager.active_tools == []

    # Transition to planning
    summary1 = manager.transition_to("planning", scratchpad_data={"objective": "Build cache"})
    assert manager.active_skill.name == "planning"
    assert "planner" in manager.active_system_prompt.lower()
    assert len(events_emitted) == 1
    assert events_emitted[0][0] == EventType.SKILL_LOADED
    assert events_emitted[0][1]["loaded_skill"] == "planning"

    # Advance work in planning
    manager.active_skill.completed_items.append("Plan redis schema")
    manager.active_skill.pending_items.append("Code cache client")

    # Transition to coding
    summary2 = manager.transition_to("coding")
    assert manager.active_skill.name == "coding"
    assert "engineer" in manager.active_system_prompt.lower()
    assert summary2.source_skill == "planning"
    assert summary2.target_skill == "coding"
    assert "Plan redis schema" in summary2.completed_work

    # Verify both UNLOADED and LOADED events were fired
    assert len(events_emitted) == 3
    assert events_emitted[1][0] == EventType.SKILL_UNLOADED
    assert events_emitted[1][1]["unloaded_skill"] == "planning"
    assert events_emitted[2][0] == EventType.SKILL_LOADED
    assert events_emitted[2][1]["loaded_skill"] == "coding"

    # Verify coding suite rehydrated the work
    assert "Plan redis schema" in manager.active_skill.completed_items
    assert "Code cache client" in manager.active_skill.pending_items


def test_skill_manager_unregistered_skill_error():
    manager = SkillManager(execution_id="exec-sm-2")
    with pytest.raises(ValueError) as exc:
        manager.transition_to("non_existent_skill")
    assert "unregistered skill" in str(exc.value)
