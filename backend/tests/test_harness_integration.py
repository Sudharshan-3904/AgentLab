"""Integration test verifying Phase 1 Exit Criteria:
The harness can create and persist an execution from task intake through completion
using mocked model/tool calls into a persistent SQLite ledger.
"""

from pathlib import Path
import pytest
import sqlite3

from harness.core.config import HarnessConfig
from harness.core.events import EventType
from harness.core.harness import Harness
from harness.core.interfaces import (
    ChatMessage,
    DerivedMetrics,
    EvaluationSummary,
    IEvaluationEngine,
    IMonitoringManager,
    IModelProvider,
    IPolicyEngine,
    ISkillSuite,
    ITool,
    ModelCallRecord,
    ModelChunk,
    ModelHealth,
    ModelMetadata,
    ModelRequest,
    ModelResponse,
    PolicyDecision,
    PolicyEvaluationContext,
    PolicyEvaluationResult,
    RawMetrics,
    ResourceSample,
    SkillContext,
    SkillTransitionSummary,
    ToolDefinition,
    ToolRequest,
    ToolResponse,
    ToolStatus,
)
from harness.core.state import ExecutionState
from harness.tasks.task import Task


class IntegrationMockModel(IModelProvider):
    def generate(self, request: ModelRequest) -> ModelResponse:
        record = ModelCallRecord(
            call_id="call-int-001",
            execution_id=request.execution_id,
            provider="ollama",
            model="llama3.2:latest",
            temperature=request.temperature,
            top_p=request.top_p,
            started_at="2026-10-03T20:00:00Z",
            completed_at="2026-10-03T20:00:01Z",
            prompt_tokens=120,
            output_tokens=60,
            duration_ms=450.0,
            success=True,
        )
        return ModelResponse(
            call_id="call-int-001",
            message=ChatMessage(role="assistant", content="Step 1: scaffold project\nStep 2: add endpoints"),
            record=record,
        )

    def stream(self, request: ModelRequest):
        yield ModelChunk(delta="response")

    def health(self) -> ModelHealth:
        return ModelHealth(available=True)

    def metadata(self, model_name=None) -> ModelMetadata:
        return ModelMetadata(name="llama3.2:latest", provider="ollama")


class IntegrationMockTool(ITool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="file_system_tool",
            description="Performs filesystem operations",
            parameters={"path": "string", "operation": "string"},
            danger_level="normal",
        )

    def execute(self, request: ToolRequest) -> ToolResponse:
        return ToolResponse(
            tool_request_id=request.tool_request_id,
            execution_id=request.execution_id,
            tool_name=self.name,
            status=ToolStatus.SUCCESS,
            output={"bytes_written": 256, "file": request.arguments.get("path")},
            duration_ms=12.0,
        )


class IntegrationMockSkill(ISkillSuite):
    def __init__(self, name: str, next_skill: str = ""):
        self._name = name
        self._next_skill = next_skill

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"{self._name} skill suite"

    @property
    def system_prompt(self) -> str:
        return f"System instructions for {self._name}"

    @property
    def tools(self):
        return []

    def on_load(self, context: SkillContext) -> None:
        self.context = context

    def on_unload(self) -> SkillTransitionSummary:
        return SkillTransitionSummary(
            source_skill=self._name,
            target_skill=self._next_skill,
            objective="Integration task",
            completed_work=[f"Completed phase {self._name}"],
            pending_work=["Proceeding to next step"],
            next_verification_step="Check test results",
        )


class IntegrationEvaluationEngine(IEvaluationEngine):
    def evaluate(self, execution_id, events, resource_samples=None, model_calls=None, tool_responses=None):
        return EvaluationSummary(
            execution_id=execution_id,
            status="COMPLETED",
            raw_metrics=RawMetrics(
                total_duration_s=3.0,
                model_calls_count=len(model_calls or []),
                tool_calls_count=len(tool_responses or []),
                prompt_tokens=120,
                output_tokens=60,
                total_tokens=180,
            ),
            derived_metrics=DerivedMetrics(
                task_success=True,
                tool_success_rate=1.0,
                model_success_rate=1.0,
            ),
        )


def test_phase1_exit_criteria_persistence_and_lifecycle(tmp_path: Path):
    """
    Exit Criteria:
    The harness can create and persist an execution from task intake through
    completion using mocked model/tool calls.
    """
    config_yaml = """
harness:
  name: local-coding-harness
  version: "0.1"
execution:
  autonomy: balanced
  max_duration_seconds: 1800
  max_recovery_attempts: 1
model:
  default_provider: ollama
  default_model: llama3.2
sampling:
  temperature: 0.2
  top_p: 0.9
  seed: 42
workspace:
  root: ./workspace
  git_enabled: true
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_yaml, encoding="utf-8")

    db_file = tmp_path / "harness_ledger.db"

    # Instantiate harness from YAML with disk SQLite database
    harness = Harness.from_yaml_file(
        config_file,
        db_path=str(db_file),
        evaluation_engine=IntegrationEvaluationEngine(),
    )

    # Register mock components
    model_provider = IntegrationMockModel()
    harness.register_model_provider("ollama", model_provider)

    planning_skill = IntegrationMockSkill("planning", "coding")
    coding_skill = IntegrationMockSkill("coding", "testing")
    testing_skill = IntegrationMockSkill("testing", "")
    harness.register_skill(planning_skill)
    harness.register_skill(coding_skill)
    harness.register_skill(testing_skill)

    fs_tool = IntegrationMockTool()
    harness.register_tool(fs_tool)

    # 1. Task Intake
    task = Task(
        objective="Create REST endpoint for inventory items",
        constraints=["Follow PEP 8", "Use Pydantic v2"],
    )
    exec_mgr = harness.create_execution(task)
    execution_id = exec_mgr.execution_id
    assert exec_mgr.current_state == ExecutionState.INTAKE

    # 2. Planning Phase
    exec_mgr.transition_to(ExecutionState.PLANNING, reason="Start decomposition")
    exec_mgr.switch_skill(planning_skill)
    plan_resp = exec_mgr.call_model([ChatMessage(role="user", content=task.objective)])
    assert "Step 1" in plan_resp.message.content

    exec_mgr.scratchpad.set_subtasks(["scaffold project", "add inventory endpoints"])
    exec_mgr.emit_event(
        EventType.TASK_DECOMPOSED,
        source="planner",
        payload={"subtasks": exec_mgr.scratchpad.subtasks},
    )

    # 3. Execution Phase (Coding)
    exec_mgr.transition_to(ExecutionState.EXECUTING, reason="Start implementation")
    exec_mgr.switch_skill(coding_skill)

    tool_res = exec_mgr.execute_tool(
        fs_tool,
        {"path": "inventory/router.py", "operation": "write"},
    )
    assert tool_res.status == ToolStatus.SUCCESS
    exec_mgr.scratchpad.complete_subtask("scaffold project")

    # 4. Verification Phase
    exec_mgr.transition_to(ExecutionState.VERIFYING, reason="Run automated tests")
    exec_mgr.switch_skill(testing_skill)
    exec_mgr.emit_event(
        EventType.TEST_RESULT,
        source="verification",
        payload={"passed": True, "count": 5},
    )
    exec_mgr.scratchpad.complete_subtask("add inventory endpoints")

    # 5. Testing Phase (Application Preview)
    exec_mgr.transition_to(ExecutionState.TESTING, reason="Launch app preview")
    exec_mgr.emit_event(
        EventType.USER_FEEDBACK,
        source="application_tester",
        payload={"approved": True},
    )

    # 6. Completion
    exec_mgr.complete(reason="Inventory endpoint created and tested")
    assert exec_mgr.current_state == ExecutionState.COMPLETED
    assert exec_mgr.is_finished is True

    # 7. Evaluate Execution
    summary = harness.evaluate_execution(execution_id)
    assert summary is not None
    assert summary.derived_metrics.task_success is True
    assert summary.raw_metrics.model_calls_count == 1
    assert summary.raw_metrics.tool_calls_count == 1

    # 8. Export to JSONL stream
    jsonl_export = tmp_path / "execution_events.jsonl"
    exported_count = harness.export_execution_jsonl(execution_id, jsonl_export)
    assert exported_count > 0
    assert jsonl_export.exists()

    # Close harness connection
    harness.close()

    # 9. Verify persistent SQLite database on disk directly
    assert db_file.exists()
    disk_conn = sqlite3.connect(str(db_file))
    cursor = disk_conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM events WHERE execution_id = ?", (execution_id,))
    total_events = cursor.fetchone()[0]
    assert total_events >= 10

    # Verify event types persisted in SQLite
    cursor.execute("SELECT DISTINCT type FROM events WHERE execution_id = ?", (execution_id,))
    persisted_types = {row[0] for row in cursor.fetchall()}
    assert "TASK_RECEIVED" in persisted_types
    assert "EXECUTION_STATE_CHANGED" in persisted_types
    assert "SKILL_LOADED" in persisted_types
    assert "MODEL_REQUEST" in persisted_types
    assert "MODEL_RESPONSE" in persisted_types
    assert "TOOL_REQUEST" in persisted_types
    assert "TOOL_POLICY_DECISION" in persisted_types
    assert "TOOL_RESPONSE" in persisted_types
    assert "TEST_RESULT" in persisted_types
    assert "USER_FEEDBACK" in persisted_types
    assert "EXECUTION_COMPLETED" in persisted_types

    disk_conn.close()
