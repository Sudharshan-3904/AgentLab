"""Event schema and event types for Local AI Harness ledger and telemetry."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
import uuid
from pydantic import BaseModel, Field


class EventCategory(str, Enum):
    """Broad categories for harness events."""
    TASK = "task"
    SKILL = "skill"
    MODEL = "model"
    TOOL = "tool"
    WORKSPACE = "workspace"
    TESTING = "testing"
    RECOVERY = "recovery"
    MONITORING = "monitoring"
    SECURITY = "security"
    LIFECYCLE = "lifecycle"


class EventType(str, Enum):
    """Specific event type identifiers matching Technical Details specification."""
    # Task events
    TASK_RECEIVED = "TASK_RECEIVED"
    TASK_DECOMPOSED = "TASK_DECOMPOSED"
    CLARIFICATION_REQUESTED = "CLARIFICATION_REQUESTED"

    # Skill events
    SKILL_LOADED = "SKILL_LOADED"
    SKILL_UNLOADED = "SKILL_UNLOADED"

    # Model events
    MODEL_SELECTED = "MODEL_SELECTED"
    MODEL_REQUEST = "MODEL_REQUEST"
    MODEL_RESPONSE = "MODEL_RESPONSE"

    # Tool events
    TOOL_REQUEST = "TOOL_REQUEST"
    TOOL_POLICY_DECISION = "TOOL_POLICY_DECISION"
    TOOL_RESPONSE = "TOOL_RESPONSE"

    # Workspace events
    FILE_CHANGE = "FILE_CHANGE"
    CHECKPOINT = "CHECKPOINT"
    ROLLBACK = "ROLLBACK"

    # Testing events
    TEST_STARTED = "TEST_STARTED"
    TEST_RESULT = "TEST_RESULT"
    USER_FEEDBACK = "USER_FEEDBACK"
    APPLICATION_LAUNCHED = "APPLICATION_LAUNCHED"
    APPLICATION_HEALTH_CHECK = "APPLICATION_HEALTH_CHECK"
    APPLICATION_STOPPED = "APPLICATION_STOPPED"

    # Recovery & error events
    ERROR = "ERROR"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"

    # Monitoring & security
    RESOURCE_SAMPLE = "RESOURCE_SAMPLE"
    SECURITY_EVENT = "SECURITY_EVENT"

    # Lifecycle events
    EXECUTION_STATE_CHANGED = "EXECUTION_STATE_CHANGED"
    EXECUTION_COMPLETED = "EXECUTION_COMPLETED"


class Event(BaseModel):
    """Standardized event record for the execution ledger."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    execution_id: str = Field(..., description="Unique execution instance identifier")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp"
    )
    type: EventType = Field(..., description="Type of event")
    source: str = Field(..., description="Component or subsystem that emitted the event")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Structured event payload data")
    correlation_id: Optional[str] = Field(
        default=None,
        description="Optional correlation identifier (e.g., tool_request_id, model_call_id)"
    )

    @classmethod
    def create(
        cls,
        execution_id: str,
        type: EventType,
        source: str,
        payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Event:
        """Convenience factory method to instantiate an Event."""
        return cls(
            execution_id=execution_id,
            type=type,
            source=source,
            payload=payload or {},
            correlation_id=correlation_id,
        )
