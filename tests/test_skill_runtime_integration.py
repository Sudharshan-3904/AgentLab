"""Integration test verifying Phase 3 Exit Criteria:
One execution can move: Planning -> Coding -> Testing -> Debugging
without losing task continuity.
"""

from pathlib import Path
import pytest

from harness.core.config import HarnessConfig
from harness.core.events import EventType
from harness.core.harness import Harness
from harness.skills.suites import (
    CodingSkillSuite,
    DebuggingSkillSuite,
    PlanningSkillSuite,
    TestingSkillSuite,
)
from harness.tasks.task import Task


def test_phase3_exit_criteria_skill_progression(tmp_path: Path):
    """
    Exit Criteria:
    One execution can move: Planning -> Coding -> Testing -> Debugging
    without losing task continuity.
    """
    db_file = tmp_path / "skill_runtime_ledger.db"
    harness = Harness(db_path=str(db_file))

    # Register all 4 MVP skill suites
    harness.register_skill(PlanningSkillSuite())
    harness.register_skill(CodingSkillSuite())
    harness.register_skill(TestingSkillSuite())
    harness.register_skill(DebuggingSkillSuite())

    # Create execution with explicit constraints
    task = Task(
        objective="Implement database connection pool with automatic retry",
        constraints=["Max 10 connections", "Timeout 3 seconds", "Thread-safe"],
    )
    exec_mgr = harness.create_execution(task)
    execution_id = exec_mgr.execution_id

    # -------------------------------------------------------------
    # 1. PLANNING SUITE
    # -------------------------------------------------------------
    exec_mgr.switch_skill("planning")
    assert exec_mgr.active_skill.name == "planning"
    assert "planner" in exec_mgr.skill_manager.active_system_prompt.lower()

    # Planner records decomposition and decisions
    exec_mgr.active_skill.completed_items.append("Decomposed connection pool architecture")
    exec_mgr.active_skill.pending_items.append("Implement ConnectionPool class")
    exec_mgr.active_skill.decisions.append("Use thread-safe queue.Queue for pool storage")
    exec_mgr.active_skill.next_verification_step = "Run concurrent pool acquire tests"

    # -------------------------------------------------------------
    # 2. CODING SUITE
    # -------------------------------------------------------------
    exec_mgr.switch_skill("coding")
    assert exec_mgr.active_skill.name == "coding"
    assert "engineer" in exec_mgr.skill_manager.active_system_prompt.lower()

    # Verify continuity from Planning
    assert "Decomposed connection pool architecture" in exec_mgr.active_skill.completed_items
    assert "Implement ConnectionPool class" in exec_mgr.active_skill.pending_items
    assert "Use thread-safe queue.Queue for pool storage" in exec_mgr.active_skill.decisions

    # Coder completes implementation and adds new decisions
    exec_mgr.active_skill.completed_items.append("Implement ConnectionPool class")
    exec_mgr.active_skill.pending_items.remove("Implement ConnectionPool class")
    exec_mgr.active_skill.decisions.append("Added exponential backoff to retry logic")
    exec_mgr.active_skill.next_verification_step = "Run pytest on pool acquire timeout"

    # -------------------------------------------------------------
    # 3. TESTING SUITE
    # -------------------------------------------------------------
    exec_mgr.switch_skill("testing")
    assert exec_mgr.active_skill.name == "testing"
    assert "test engineer" in exec_mgr.skill_manager.active_system_prompt.lower()

    # Verify continuity from Coding
    assert "Implement ConnectionPool class" in exec_mgr.active_skill.completed_items
    assert "Added exponential backoff to retry logic" in exec_mgr.active_skill.decisions

    # Tester discovers a defect
    exec_mgr.active_skill.known_failures.append(
        "ConnectionTimeoutError: Retry backoff exceeded 3s timeout constraint under load"
    )
    exec_mgr.active_skill.discovered_facts.append(
        "Retry interval was set to 1.5s multiplier which quickly breached 3s constraint"
    )
    exec_mgr.active_skill.next_verification_step = "Re-test with tuned backoff parameters"

    # -------------------------------------------------------------
    # 4. DEBUGGING SUITE
    # -------------------------------------------------------------
    exec_mgr.switch_skill("debugging")
    assert exec_mgr.active_skill.name == "debugging"
    assert "troubleshooter" in exec_mgr.skill_manager.active_system_prompt.lower()

    # Verify continuity from Testing into Debugging
    assert len(exec_mgr.active_skill.known_failures) == 1
    assert "Retry backoff exceeded 3s" in exec_mgr.active_skill.known_failures[0]
    assert "Retry interval was set to 1.5s" in exec_mgr.active_skill.discovered_facts[0]

    # Debugger records root cause and targeted fix
    exec_mgr.active_skill.decisions.append("Capped maximum backoff sleep to 0.5s")
    exec_mgr.active_skill.completed_items.append("Diagnosed and patched backoff ceiling")
    exec_mgr.active_skill.next_verification_step = "Final suite pass verification"

    # -------------------------------------------------------------
    # 5. VERIFY COMPLETE CONTINUITY IN FINAL SUMMARY
    # -------------------------------------------------------------
    final_summary = exec_mgr.active_skill.on_unload()

    # Complete work across all 4 stages preserved
    assert "Decomposed connection pool architecture" in final_summary.completed_work
    assert "Implement ConnectionPool class" in final_summary.completed_work
    assert "Diagnosed and patched backoff ceiling" in final_summary.completed_work

    # Decisions across all stages preserved
    assert "Use thread-safe queue.Queue for pool storage" in final_summary.relevant_decisions
    assert "Added exponential backoff to retry logic" in final_summary.relevant_decisions
    assert "Capped maximum backoff sleep to 0.5s" in final_summary.relevant_decisions

    # Known failures and facts preserved
    assert len(final_summary.known_failures) == 1
    assert len(final_summary.discovered_facts) == 1

    # -------------------------------------------------------------
    # 6. VERIFY PERSISTED EVENTS IN SQLITE LEDGER
    # -------------------------------------------------------------
    events = harness.get_events(execution_id)
    skill_loaded_events = [e for e in events if e.type == EventType.SKILL_LOADED]
    skill_unloaded_events = [e for e in events if e.type == EventType.SKILL_UNLOADED]

    # 4 loads: planning -> coding -> testing -> debugging
    assert len(skill_loaded_events) == 4
    assert [e.payload["loaded_skill"] for e in skill_loaded_events] == [
        "planning",
        "coding",
        "testing",
        "debugging",
    ]

    # 3 unloads: planning, coding, testing
    assert len(skill_unloaded_events) == 3
    assert [e.payload["unloaded_skill"] for e in skill_unloaded_events] == [
        "planning",
        "coding",
        "testing",
    ]

    harness.close()
