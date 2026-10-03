"""Tests for base skill suite and the 4 MVP specialized skill suites."""

import pytest
from harness.core.interfaces import SkillContext, SkillTransitionSummary
from harness.skills.base import BaseSkillSuite
from harness.skills.suites import (
    CodingSkillSuite,
    DebuggingSkillSuite,
    PlanningSkillSuite,
    TestingSkillSuite,
)


def test_planning_skill_suite():
    suite = PlanningSkillSuite()
    assert suite.name == "planning"
    assert "planner" in suite.system_prompt.lower()

    ctx = SkillContext(
        execution_id="exec-s1",
        skill_name="planning",
        scratchpad_data={"objective": "Build user auth", "constraints": ["No plaintext passwords"]},
    )
    suite.on_load(ctx)
    suite.completed_items.append("Plan auth endpoints")
    suite.pending_items.append("Implement hashing")
    suite.decisions.append("Use bcrypt for password hashing")
    suite.next_verification_step = "Run auth unit tests"

    summary = suite.on_unload()
    assert summary.source_skill == "planning"
    assert summary.objective == "Build user auth"
    assert "Plan auth endpoints" in summary.completed_work
    assert "Implement hashing" in summary.pending_work
    assert "Use bcrypt for password hashing" in summary.relevant_decisions
    assert "No plaintext passwords" in summary.constraints
    assert summary.next_verification_step == "Run auth unit tests"


def test_coding_rehydrates_from_planning_summary():
    planning = PlanningSkillSuite()
    planning_ctx = SkillContext(
        execution_id="exec-s2",
        skill_name="planning",
        scratchpad_data={"objective": "Add caching layer"},
    )
    planning.on_load(planning_ctx)
    planning.completed_items.append("Architecture design approved")
    planning.pending_items.append("Implement redis cache adapter")
    planning.decisions.append("Set TTL to 300s")
    planning_summary = planning.on_unload()

    coding = CodingSkillSuite()
    coding_ctx = SkillContext(
        execution_id="exec-s2",
        skill_name="coding",
        continuity_summary=planning_summary,
    )
    coding.on_load(coding_ctx)

    # State rehydrated seamlessly
    assert "Architecture design approved" in coding.completed_items
    assert "Implement redis cache adapter" in coding.pending_items
    assert "Set TTL to 300s" in coding.decisions

    # Advance work in coding
    coding.completed_items.append("Implement redis cache adapter")
    coding.pending_items.remove("Implement redis cache adapter")
    coding_summary = coding.on_unload()

    assert "Implement redis cache adapter" in coding_summary.completed_work
    assert len(coding_summary.pending_work) == 0


def test_testing_and_debugging_suite_handoff():
    testing = TestingSkillSuite()
    ctx = SkillContext(
        execution_id="exec-s3",
        skill_name="testing",
        scratchpad_data={"objective": "Validate payment flow"},
    )
    testing.on_load(ctx)
    testing.known_failures.append("PaymentTimeoutError on mock gateway")
    test_summary = testing.on_unload()

    assert "PaymentTimeoutError on mock gateway" in test_summary.known_failures

    # Debugging rehydrates testing failure
    debugging = DebuggingSkillSuite()
    debug_ctx = SkillContext(
        execution_id="exec-s3",
        skill_name="debugging",
        continuity_summary=test_summary,
    )
    debugging.on_load(debug_ctx)

    assert "PaymentTimeoutError on mock gateway" in debugging.known_failures
    debugging.decisions.append("Increase gateway mock timeout from 100ms to 500ms")
    debugging.discovered_facts.append("Network delay in CI environment was 250ms")
    debug_summary = debugging.on_unload()

    assert "Increase gateway mock timeout" in debug_summary.relevant_decisions[0]
    assert "Network delay in CI" in debug_summary.discovered_facts[0]
