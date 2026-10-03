"""Unit tests for FailureClassifier and RecoveryStrategyEngine."""

import pytest

from harness.core.config import HarnessConfig
from harness.core.events import EventType
from harness.core.state import ExecutionState
from harness.execution.manager import ExecutionManager
from harness.execution.recovery import (
    FailureClassifier,
    FailureType,
    RecoveryContext,
    RecoveryStrategyEngine,
)
from harness.ledger.sqlite import SQLiteEventLedger
from harness.models.interface import ChatMessage
from harness.tasks.task import Task
from tests.test_interfaces import MockPolicyEngine


def test_failure_classifier_types():
    assert FailureClassifier.classify("SyntaxError: invalid syntax on line 12") == FailureType.SYNTAX_ERROR
    assert FailureClassifier.classify("IndentationError: unexpected indent") == FailureType.SYNTAX_ERROR
    assert FailureClassifier.classify("AssertionError: assert 4 == 5") == FailureType.TEST_FAILURE
    assert FailureClassifier.classify("Pytest run failed: 1 failure") == FailureType.TEST_FAILURE
    assert FailureClassifier.classify("Process timed out after 30.0s") == FailureType.TIMEOUT
    assert FailureClassifier.classify("PolicyEngine denied tool execution") == FailureType.TOOL_ERROR
    assert FailureClassifier.classify("RuntimeError: file not found") == FailureType.RUNTIME_ERROR
    assert FailureClassifier.classify("Something bizarre happened") == FailureType.UNKNOWN


def test_formulate_recovery_prompt():
    ctx = RecoveryContext(
        failure_reason="Test assertion failed",
        failure_type=FailureType.TEST_FAILURE,
        error_details="assert result.code == 200",
        history_messages=[ChatMessage(role="user", content="Build an API endpoint")],
    )

    prompt = RecoveryStrategyEngine.formulate_recovery_prompt(
        objective="Build an API endpoint",
        context=ctx,
    )

    assert len(prompt) == 2
    assert prompt[0].content == "Build an API endpoint"
    assert "TEST_FAILURE" in prompt[1].content
    assert "assert result.code == 200" in prompt[1].content
    assert "corrected implementation" in prompt[1].content


def test_recovery_engine_execute_recovery():
    task = Task.from_prompt("Generate calculator")
    config = HarnessConfig()
    config.execution.max_recovery_attempts = 1
    ledger = SQLiteEventLedger(":memory:")
    policy = MockPolicyEngine()

    manager = ExecutionManager(
        task=task,
        config=config,
        ledger=ledger,
        policy_engine=policy,
    )

    # Transition to EXECUTING
    manager.transition_to(ExecutionState.PLANNING)
    manager.transition_to(ExecutionState.EXECUTING)

    # First recovery attempt should succeed
    res1 = RecoveryStrategyEngine.execute_recovery(
        manager=manager,
        failure_reason="SyntaxError in calc.py",
        error_details="SyntaxError: invalid syntax at line 5",
    )

    assert res1.success is True
    assert res1.attempt == 1
    assert manager.current_state == ExecutionState.RECOVERY
    assert len(manager.scratchpad.recovery_history) == 1
    assert manager.scratchpad.recovery_history[0].attempt == 1
    assert "SYNTAX_ERROR" in manager.scratchpad.recovery_history[0].failure_description

    # Second recovery attempt should fail as budget is 1
    res2 = RecoveryStrategyEngine.execute_recovery(
        manager=manager,
        failure_reason="SyntaxError still present",
    )

    assert res2.success is False
    assert manager.current_state == ExecutionState.FAILED

    events = ledger.get_events(manager.execution_id)
    event_types = [e.type for e in events]
    assert EventType.RECOVERY_STARTED in event_types
    assert EventType.ERROR in event_types
