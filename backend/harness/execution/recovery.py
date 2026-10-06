"""Automated recovery strategy engine for Local AI Harness."""

from __future__ import annotations

from enum import Enum
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from harness.core.events import EventType
from harness.core.state import ExecutionState
from harness.models.interface import ChatMessage, ModelRequest

logger = logging.getLogger("agentlab.recovery")


class FailureType(str, Enum):
    """Classification of execution failures."""
    SYNTAX_ERROR = "SYNTAX_ERROR"
    TEST_FAILURE = "TEST_FAILURE"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


class FailureClassifier:
    """Categorizes raw error outputs into standard failure types."""

    @classmethod
    def classify(cls, error_text: str) -> FailureType:
        text_lower = error_text.lower()
        if "syntaxerror" in text_lower or "indentationerror" in text_lower:
            return FailureType.SYNTAX_ERROR
        if "assertionerror" in text_lower or "failed" in text_lower or "pytest" in text_lower or "assert" in text_lower:
            return FailureType.TEST_FAILURE
        if "timeout" in text_lower or "timed out" in text_lower:
            return FailureType.TIMEOUT
        if "policy" in text_lower or "denied" in text_lower or "forbidden" in text_lower:
            return FailureType.TOOL_ERROR
        if "traceback" in text_lower or "exception" in text_lower or "error" in text_lower:
            return FailureType.RUNTIME_ERROR
        return FailureType.UNKNOWN


class RecoveryContext(BaseModel):
    """Contextual metadata gathered for diagnosing and recovering from an error."""
    failure_reason: str
    failure_type: FailureType
    error_details: str = ""
    history_messages: List[ChatMessage] = Field(default_factory=list)
    checkpoint_id: Optional[str] = None
    attempt_number: int = 1


class RecoveryResult(BaseModel):
    """Outcome of an automated recovery action."""
    attempt: int
    success: bool
    recovery_prompt: List[ChatMessage] = Field(default_factory=list)
    action_taken: str
    rollback_performed: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.success


class RecoveryStrategyEngine:
    """Orchestrates failure capture, scratchpad updates, rollback, and model re-prompting."""

    #TODO - EXP-006: Add selectable alternate-model, alternate-skill, context-reduction, and diagnosis strategies for comparison.

    @classmethod
    def formulate_recovery_prompt(
        cls,
        objective: str,
        context: RecoveryContext,
    ) -> List[ChatMessage]:
        """Construct the prompt messages sent to the model to correct the failure."""
        base_messages = list(context.history_messages)

        error_summary = (
            f"The previous attempt failed with a {context.failure_type.value}:\n"
            f"Reason: {context.failure_reason}\n"
        )
        if context.error_details:
            error_summary += f"Details / Traceback:\n```\n{context.error_details}\n```\n"

        instructions = (
            f"{error_summary}\n"
            f"Objective: {objective}\n"
            "Please analyze the failure, explain the root cause concisely, and generate the corrected implementation."
        )

        corrective_message = ChatMessage(
            role="user",
            content=instructions,
        )

        return base_messages + [corrective_message]

    @classmethod
    def execute_recovery(
        cls,
        manager: Any,
        failure_reason: str,
        error_details: Optional[str] = None,
        checkpoint_id: Optional[str] = None,
        messages: Optional[List[ChatMessage]] = None,
    ) -> RecoveryResult:
        """Execute the MVP recovery sequence:

        1. Capture error & classify
        2. Capture relevant conversation
        3. Append failure to scratchpad
        4. (Optional) Rollback to checkpoint
        5. Formulate recovery prompt and resend
        """
        max_attempts = manager.config.execution.max_recovery_attempts
        if manager.recovery_attempts >= max_attempts:
            manager.emit_event(
                EventType.ERROR,
                source="recovery_engine",
                payload={
                    "error": f"Max recovery attempts ({max_attempts}) exceeded",
                    "attempts": manager.recovery_attempts,
                    "failure_reason": failure_reason,
                },
            )
            manager.fail(f"Recovery exhausted after {manager.recovery_attempts} attempt(s): {failure_reason}")
            return RecoveryResult(
                attempt=manager.recovery_attempts,
                success=False,
                action_taken="Max recovery attempts exceeded",
                rollback_performed=False,
                details={"reason": failure_reason},
            )

        manager.recovery_attempts += 1
        current_attempt = manager.recovery_attempts

        # 1. Capture and classify error
        failure_type = FailureClassifier.classify(f"{failure_reason}\n{error_details or ''}")

        # 2. Capture conversation
        conv_messages = list(messages or [])
        if not conv_messages and manager.model_call_records:
            # Reconstruct from last model call if available
            last_record = manager.model_call_records[-1]
            req = getattr(last_record, "request", None)
            if req and hasattr(req, "messages"):
                conv_messages = list(req.messages)

        # 3. Append failure to scratchpad
        action_desc = f"Analyzing {failure_type.value} and retrying implementation"
        manager.scratchpad.add_recovery(
            attempt=current_attempt,
            failure=f"[{failure_type.value}] {failure_reason}",
            action=action_desc,
            resolved=False,
        )
        manager.scratchpad.fail_subtask(failure_reason, reason=error_details or "")

        # 4. Optional Rollback to checkpoint
        rollback_done = False
        target_checkpoint = checkpoint_id
        if not target_checkpoint and manager.workspace_manager:
            cps = getattr(manager.workspace_manager, "checkpoints", None)
            if cps:
                target_checkpoint = cps[-1].checkpoint_id

        if target_checkpoint and manager.workspace_manager:
            rollback_done = manager.rollback(target_checkpoint)

        # 5. Formulate recovery context and prompt
        rec_context = RecoveryContext(
            failure_reason=failure_reason,
            failure_type=failure_type,
            error_details=error_details or "",
            history_messages=conv_messages,
            checkpoint_id=target_checkpoint if rollback_done else None,
            attempt_number=current_attempt,
        )

        recovery_prompt = cls.formulate_recovery_prompt(
            objective=manager.task.objective,
            context=rec_context,
        )

        # Record events and state change
        manager.emit_event(
            EventType.RECOVERY_STARTED,
            source="recovery_engine",
            payload={
                "attempt": current_attempt,
                "failure_type": failure_type.value,
                "failure_reason": failure_reason,
                "rollback_performed": rollback_done,
                "checkpoint_id": target_checkpoint if rollback_done else None,
            },
        )

        manager.state_machine.transition_to(
            ExecutionState.RECOVERY,
            reason=f"Recovery attempt {current_attempt}: {failure_type.value}",
        )

        return RecoveryResult(
            attempt=current_attempt,
            success=True,
            recovery_prompt=recovery_prompt,
            action_taken=action_desc,
            rollback_performed=rollback_done,
            details={
                "failure_type": failure_type.value,
                "checkpoint_id": target_checkpoint if rollback_done else None,
            },
        )
