"""Tests for event schema and event creation."""

from harness.core.events import Event, EventCategory, EventType


def test_event_creation_and_defaults():
    event = Event.create(
        execution_id="exec-001",
        type=EventType.TASK_RECEIVED,
        source="task_intake",
        payload={"objective": "Build calculator app"},
    )
    assert event.execution_id == "exec-001"
    assert event.type == EventType.TASK_RECEIVED
    assert event.source == "task_intake"
    assert event.payload["objective"] == "Build calculator app"
    assert event.event_id is not None
    assert event.timestamp is not None
    assert event.correlation_id is None


def test_event_with_correlation_id():
    event = Event.create(
        execution_id="exec-002",
        type=EventType.TOOL_REQUEST,
        source="coding_skill",
        payload={"tool": "shell", "command": "ls"},
        correlation_id="req-12345",
    )
    assert event.correlation_id == "req-12345"
    assert event.type == EventType.TOOL_REQUEST


def test_event_json_serialization():
    event = Event.create(
        execution_id="exec-003",
        type=EventType.MODEL_SELECTED,
        source="model_router",
        payload={"provider": "ollama", "model": "llama3.2"},
    )
    json_str = event.model_dump_json()
    assert "MODEL_SELECTED" in json_str
    assert "exec-003" in json_str
    assert "llama3.2" in json_str


def test_event_categories():
    assert EventCategory.TASK == "task"
    assert EventCategory.SKILL == "skill"
    assert EventCategory.MODEL == "model"
    assert EventCategory.TOOL == "tool"
    assert EventCategory.WORKSPACE == "workspace"
    assert EventCategory.TESTING == "testing"
    assert EventCategory.RECOVERY == "recovery"
    assert EventCategory.MONITORING == "monitoring"
    assert EventCategory.SECURITY == "security"
    assert EventCategory.LIFECYCLE == "lifecycle"
