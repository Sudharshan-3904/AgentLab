"""Execution state machine and lifecycle states for Local AI Harness."""

from __future__ import annotations

from enum import Enum
from typing import Callable, Dict, List, Optional, Set
from datetime import datetime, timezone


class ExecutionState(str, Enum):
    """Execution lifecycle states."""
    CREATED = "CREATED"
    INTAKE = "INTAKE"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    RECOVERY = "RECOVERY"
    TESTING = "TESTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Allowed state transitions graph
VALID_TRANSITIONS: Dict[ExecutionState, Set[ExecutionState]] = {
    ExecutionState.CREATED: {
        ExecutionState.INTAKE,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.INTAKE: {
        ExecutionState.PLANNING,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.PLANNING: {
        ExecutionState.EXECUTING,
        ExecutionState.INTAKE,  # User clarification return
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.EXECUTING: {
        ExecutionState.VERIFYING,
        ExecutionState.RECOVERY,
        ExecutionState.TESTING,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.VERIFYING: {
        ExecutionState.TESTING,
        ExecutionState.RECOVERY,
        ExecutionState.EXECUTING,
        ExecutionState.COMPLETED,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.RECOVERY: {
        ExecutionState.EXECUTING,
        ExecutionState.PLANNING,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    ExecutionState.TESTING: {
        ExecutionState.COMPLETED,
        ExecutionState.EXECUTING,  # Iteration based on testing feedback
        ExecutionState.RECOVERY,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    },
    # Terminal states
    ExecutionState.COMPLETED: set(),
    ExecutionState.FAILED: set(),
    ExecutionState.CANCELLED: set(),
}

TERMINAL_STATES = {
    ExecutionState.COMPLETED,
    ExecutionState.FAILED,
    ExecutionState.CANCELLED,
}


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal state transition is attempted."""

    def __init__(self, current_state: ExecutionState, target_state: ExecutionState):
        super().__init__(
            f"Invalid execution state transition from '{current_state.value}' to '{target_state.value}'."
        )
        self.current_state = current_state
        self.target_state = target_state


class StateTransitionRecord:
    """Record of a transition between states."""

    def __init__(
        self,
        from_state: ExecutionState,
        to_state: ExecutionState,
        reason: Optional[str] = None,
        timestamp: Optional[str] = None,
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason or ""
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, str]:
        return {
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class ExecutionStateMachine:
    """Manages the state transitions for an execution lifecycle."""

    def __init__(
        self,
        initial_state: ExecutionState = ExecutionState.CREATED,
        on_transition: Optional[Callable[[StateTransitionRecord], None]] = None,
    ):
        self._state = initial_state
        self._history: List[StateTransitionRecord] = []
        self._on_transition = on_transition

    @property
    def current_state(self) -> ExecutionState:
        return self._state

    @property
    def is_terminal(self) -> bool:
        return self._state in TERMINAL_STATES

    @property
    def history(self) -> List[StateTransitionRecord]:
        return list(self._history)

    def can_transition_to(self, target_state: ExecutionState) -> bool:
        """Check whether a transition to target_state is permitted."""
        return target_state in VALID_TRANSITIONS.get(self._state, set())

    def transition_to(self, target_state: ExecutionState, reason: str = "") -> StateTransitionRecord:
        """Transition execution to a new state if allowed, otherwise raise InvalidStateTransitionError."""
        if not self.can_transition_to(target_state):
            raise InvalidStateTransitionError(self._state, target_state)

        record = StateTransitionRecord(
            from_state=self._state,
            to_state=target_state,
            reason=reason,
        )
        self._state = target_state
        self._history.append(record)

        if self._on_transition:
            self._on_transition(record)

        return record
