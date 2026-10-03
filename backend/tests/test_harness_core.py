"""Tests for ExecutionManager and Harness facade object."""

import pytest
from harness.core.config import HarnessConfig
from harness.core.events import EventType
from harness.core.harness import Harness
from harness.core.interfaces import (
    ChatMessage,
    IModelProvider,
    ModelCallRecord,
    ModelHealth,
    ModelMetadata,
    ModelRequest,
    ModelResponse,
    ISkillSuite,
    SkillContext,
    SkillTransitionSummary,
    ITool,
    ToolDefinition,
    ToolRequest,
    ToolResponse,
    ToolStatus,
)
from harness.core.state import ExecutionState
from harness.ledger.sqlite import SQLiteEventLedger
from harness.tasks.task import Task


class StubModel(IModelProvider):
    def generate(self, request: ModelRequest) -> ModelResponse:
        record = ModelCallRecord(
            call_id="call-stub-1",
            execution_id=request.execution_id,
            provider="ollama",
            model=request.model or "llama3.2:latest",
            temperature=request.temperature,
            top_p=request.top_p,
            started_at="2026-10-03T20:00:00Z",
            completed_at="2026-10-03T20:00:01Z",
            prompt_tokens=40,
            output_tokens=20,
            duration_ms=100.0,
        )
        return ModelResponse(
            call_id="call-stub-1",
            message=ChatMessage(role="assistant", content="Plan created"),
            record=record,
        )

    def stream(self, request: ModelRequest):
        return iter([])

    def health(self) -> ModelHealth:
        return ModelHealth(available=True)

    def metadata(self, model_name=None) -> ModelMetadata:
        return ModelMetadata(name="llama3.2:latest", provider="ollama")


class StubTool(ITool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(name="echo_tool", description="Echoes text")

    def execute(self, request: ToolRequest) -> ToolResponse:
        return ToolResponse(
            tool_request_id=request.tool_request_id,
            execution_id=request.execution_id,
            tool_name=self.name,
            status=ToolStatus.SUCCESS,
            output=request.arguments.get("text", ""),
        )


class StubSkill(ISkillSuite):
    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"{self._name} skill"

    @property
    def system_prompt(self) -> str:
        return "Prompt"

    @property
    def tools(self):
        return []

    def on_load(self, context: SkillContext) -> None:
        pass

    def on_unload(self) -> SkillTransitionSummary:
        return SkillTransitionSummary(
            source_skill=self._name,
            objective="test",
            completed_work=["done"],
        )


def test_harness_instantiation_and_execution_creation():
    harness = Harness()
    harness.register_model_provider("ollama", StubModel())
    harness.register_tool(StubTool())
    harness.register_skill(StubSkill("planning"))

    task = Task.from_prompt("Create user login system")
    exec_mgr = harness.create_execution(task)

    assert exec_mgr.execution_id in harness.list_executions()
    assert exec_mgr.current_state == ExecutionState.INTAKE
    assert exec_mgr.task.objective == "Create user login system"

    # Events recorded to SQLite ledger automatically
    events = harness.get_events(exec_mgr.execution_id)
    assert len(events) >= 2  # TASK_RECEIVED, EXECUTION_STATE_CHANGED
    assert events[0].type == EventType.TASK_RECEIVED

    harness.close()


def test_execution_manager_model_and_tool_workflow():
    harness = Harness()
    harness.register_model_provider("ollama", StubModel())
    tool = StubTool()
    harness.register_tool(tool)
    skill = StubSkill("planning")

    exec_mgr = harness.create_execution("Build unit tests")
    exec_mgr.switch_skill(skill)
    assert exec_mgr.active_skill.name == "planning"

    # Model call
    res = exec_mgr.call_model([ChatMessage(role="user", content="Plan task")])
    assert res.message.content == "Plan created"
    assert len(exec_mgr.model_call_records) == 1

    # Tool call
    resp = exec_mgr.execute_tool(tool, {"text": "hello test"})
    assert resp.status == ToolStatus.SUCCESS
    assert resp.output == "hello test"
    assert len(exec_mgr.tool_responses) == 1

    # Lifecycle transitions
    exec_mgr.transition_to(ExecutionState.PLANNING, reason="Decompose")
    exec_mgr.transition_to(ExecutionState.EXECUTING, reason="Code")
    exec_mgr.transition_to(ExecutionState.VERIFYING, reason="Test")
    exec_mgr.complete()

    assert exec_mgr.current_state == ExecutionState.COMPLETED
    assert exec_mgr.is_finished is True

    # Check all events in SQLite ledger
    events = harness.get_events(exec_mgr.execution_id)
    event_types = [e.type for e in events]
    assert EventType.TASK_RECEIVED in event_types
    assert EventType.SKILL_LOADED in event_types
    assert EventType.MODEL_REQUEST in event_types
    assert EventType.MODEL_RESPONSE in event_types
    assert EventType.TOOL_REQUEST in event_types
    assert EventType.TOOL_POLICY_DECISION in event_types
    assert EventType.TOOL_RESPONSE in event_types
    assert EventType.EXECUTION_COMPLETED in event_types

    harness.close()


def test_execution_manager_recovery():
    harness = Harness()
    exec_mgr = harness.create_execution("Recovery task")
    exec_mgr.transition_to(ExecutionState.PLANNING)
    exec_mgr.transition_to(ExecutionState.EXECUTING)
    exec_mgr.transition_to(ExecutionState.VERIFYING)

    # First recovery attempt (limit is 1 in default config)
    recovered = exec_mgr.trigger_recovery("Assertion failed in test")
    assert recovered is True
    assert exec_mgr.current_state == ExecutionState.RECOVERY
    assert exec_mgr.recovery_attempts == 1

    # Second recovery attempt should fail since max_recovery_attempts = 1
    recovered_second = exec_mgr.trigger_recovery("Assertion failed again")
    assert recovered_second is False
    assert exec_mgr.current_state == ExecutionState.FAILED

    harness.close()
