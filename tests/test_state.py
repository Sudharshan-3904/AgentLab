"""Tests for execution state machine and lifecycle states."""

import pytest
from harness.core.state import (
    ExecutionState,
    ExecutionStateMachine,
    InvalidStateTransitionError,
)


def test_initial_state():
    sm = ExecutionStateMachine()
    assert sm.current_state == ExecutionState.CREATED
    assert not sm.is_terminal
    assert len(sm.history) == 0


def test_valid_lifecycle_transitions():
    sm = ExecutionStateMachine()

    sm.transition_to(ExecutionState.INTAKE, reason="Task intake started")
    assert sm.current_state == ExecutionState.INTAKE

    sm.transition_to(ExecutionState.PLANNING, reason="Task decomposed")
    assert sm.current_state == ExecutionState.PLANNING

    sm.transition_to(ExecutionState.EXECUTING, reason="Plan approved")
    assert sm.current_state == ExecutionState.EXECUTING

    sm.transition_to(ExecutionState.VERIFYING, reason="Code modifications ready")
    assert sm.current_state == ExecutionState.VERIFYING

    sm.transition_to(ExecutionState.TESTING, reason="Unit tests passed")
    assert sm.current_state == ExecutionState.TESTING

    sm.transition_to(ExecutionState.COMPLETED, reason="Execution complete")
    assert sm.current_state == ExecutionState.COMPLETED
    assert sm.is_terminal
    assert len(sm.history) == 6


def test_recovery_lifecycle():
    sm = ExecutionStateMachine()
    sm.transition_to(ExecutionState.INTAKE)
    sm.transition_to(ExecutionState.PLANNING)
    sm.transition_to(ExecutionState.EXECUTING)
    sm.transition_to(ExecutionState.VERIFYING)

    # Verification failure leads to RECOVERY
    sm.transition_to(ExecutionState.RECOVERY, reason="Test failed, entering recovery")
    assert sm.current_state == ExecutionState.RECOVERY

    # From recovery back to executing
    sm.transition_to(ExecutionState.EXECUTING, reason="Retrying code fix")
    assert sm.current_state == ExecutionState.EXECUTING


def test_invalid_transitions():
    sm = ExecutionStateMachine()

    # Cannot jump directly from CREATED to COMPLETED
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(ExecutionState.COMPLETED)

    # Cannot transition out of terminal state
    sm.transition_to(ExecutionState.FAILED)
    assert sm.is_terminal
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(ExecutionState.EXECUTING)


def test_transition_listener():
    records = []
    sm = ExecutionStateMachine(on_transition=lambda rec: records.append(rec))
    sm.transition_to(ExecutionState.INTAKE, reason="intake")
    sm.transition_to(ExecutionState.PLANNING, reason="planning")

    assert len(records) == 2
    assert records[0].from_state == ExecutionState.CREATED
    assert records[0].to_state == ExecutionState.INTAKE
    assert records[1].to_state == ExecutionState.PLANNING
