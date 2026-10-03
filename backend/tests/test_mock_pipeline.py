"""Tests for Phase 0 exit criteria: complete mock execution flow without real model."""

import pytest
from harness.core.config import AutonomyLevel, HarnessConfig
from harness.core.events import EventType
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
from harness.core.mock_pipeline import MockExecutionPipeline, MockTask
from harness.core.state import ExecutionState


class PipelineMockModel(IModelProvider):
    def generate(self, request: ModelRequest) -> ModelResponse:
        record = ModelCallRecord(
            call_id="call-plan-1",
            execution_id=request.execution_id,
            provider="mock-ollama",
            model=request.model or "llama3.2",
            temperature=request.temperature,
            top_p=request.top_p,
            started_at="2026-10-03T20:00:00Z",
            completed_at="2026-10-03T20:00:01Z",
            prompt_tokens=150,
            output_tokens=75,
            duration_ms=500.0,
            success=True,
        )
        return ModelResponse(
            call_id="call-plan-1",
            message=ChatMessage(role="assistant", content="Decomposed plan:\n1. scaffold\n2. code"),
            record=record,
        )

    def stream(self, request: ModelRequest):
        yield ModelChunk(delta="plan chunk")

    def health(self) -> ModelHealth:
        return ModelHealth(available=True)

    def metadata(self, model_name=None) -> ModelMetadata:
        return ModelMetadata(name=model_name or "llama3.2", provider="mock")


class PipelineMockTool(ITool):
    def __init__(self, name: str = "file_writer", danger: str = "normal"):
        self._name = name
        self._danger = danger

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name,
            description="Mock file writer tool",
            parameters={"path": "str", "content": "str"},
            danger_level=self._danger,
        )

    def execute(self, request: ToolRequest) -> ToolResponse:
        return ToolResponse(
            tool_request_id=request.tool_request_id,
            execution_id=request.execution_id,
            tool_name=self._name,
            status=ToolStatus.SUCCESS,
            output=f"Wrote to {request.arguments.get('path')}",
            duration_ms=15.0,
        )


class PipelineMockSkill(ISkillSuite):
    def __init__(self, name: str, next_skill: str = ""):
        self._name = name
        self._next_skill = next_skill
        self.loaded_with_summary = None

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
        self.loaded_with_summary = context.continuity_summary

    def on_unload(self) -> SkillTransitionSummary:
        return SkillTransitionSummary(
            source_skill=self._name,
            target_skill=self._next_skill,
            objective="Build sample feature",
            completed_work=[f"Finished work in {self._name}"],
            pending_work=["Next subtask"],
            next_verification_step="Run test suite",
        )


class PipelineMockPolicy(IPolicyEngine):
    def __init__(self, deny_tools: bool = False):
        self.deny_tools = deny_tools

    def evaluate(self, context: PolicyEvaluationContext) -> PolicyEvaluationResult:
        if self.deny_tools:
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                reason="Policy prohibits writing outside sandbox",
            )
        return PolicyEvaluationResult(
            decision=PolicyDecision.ALLOW,
            reason="Permitted operation",
        )


class PipelineMockMonitoring(IMonitoringManager):
    def sample(self, execution_id: str) -> ResourceSample:
        return ResourceSample(
            sample_id="samp-01",
            execution_id=execution_id,
        )

    def start_monitoring(self, execution_id: str, interval_ms: int = 500) -> None:
        pass

    def stop_monitoring(self, execution_id: str):
        return []

    def get_samples(self, execution_id: str):
        return []


class PipelineMockEvaluation(IEvaluationEngine):
    def evaluate(self, execution_id, events, resource_samples=None, model_calls=None, tool_responses=None):
        return EvaluationSummary(
            execution_id=execution_id,
            status="COMPLETED",
            raw_metrics=RawMetrics(
                total_duration_s=2.5,
                model_calls_count=len(model_calls or []),
                tool_calls_count=len(tool_responses or []),
                skill_transitions_count=3,
            ),
            derived_metrics=DerivedMetrics(
                task_success=True,
                tool_success_rate=1.0,
                model_success_rate=1.0,
            ),
        )


def test_complete_mock_execution_flow():
    """Verify Phase 0 Exit Criterion: Complete mock execution flow without real model."""
    config = HarnessConfig()
    pipeline = MockExecutionPipeline(
        config=config,
        model_provider=PipelineMockModel(),
        skills={
            "planning": PipelineMockSkill("planning", "coding"),
            "coding": PipelineMockSkill("coding", "testing"),
            "testing": PipelineMockSkill("testing", ""),
        },
        tools={"file_writer": PipelineMockTool()},
        policy_engine=PipelineMockPolicy(),
        monitoring_manager=PipelineMockMonitoring(),
        evaluation_engine=PipelineMockEvaluation(),
    )

    task = MockTask(task_id="task-1", objective="Create user registration module")
    summary = pipeline.run_pipeline(task)

    # 1. State machine reached terminal COMPLETED state
    assert pipeline.state_machine.current_state == ExecutionState.COMPLETED
    assert pipeline.state_machine.is_terminal is True

    # 2. Check full state history progression
    history_states = [h.to_state for h in pipeline.state_machine.history]
    assert history_states == [
        ExecutionState.INTAKE,
        ExecutionState.PLANNING,
        ExecutionState.EXECUTING,
        ExecutionState.VERIFYING,
        ExecutionState.TESTING,
        ExecutionState.COMPLETED,
    ]

    # 3. Check skill continuity transitions
    coding_skill = pipeline.skills["coding"]
    assert coding_skill.loaded_with_summary is not None
    assert coding_skill.loaded_with_summary.source_skill == "planning"

    # 4. Check events recorded in the ledger
    event_types = [e.type for e in pipeline.events]
    assert EventType.TASK_RECEIVED in event_types
    assert EventType.SKILL_LOADED in event_types
    assert EventType.MODEL_RESPONSE in event_types
    assert EventType.TOOL_REQUEST in event_types
    assert EventType.TOOL_POLICY_DECISION in event_types
    assert EventType.TOOL_RESPONSE in event_types
    assert EventType.RESOURCE_SAMPLE in event_types
    assert EventType.TEST_RESULT in event_types
    assert EventType.USER_FEEDBACK in event_types
    assert EventType.EXECUTION_COMPLETED in event_types

    # 5. Check tool correlation IDs
    tool_req_events = [e for e in pipeline.events if e.type == EventType.TOOL_REQUEST]
    tool_resp_events = [e for e in pipeline.events if e.type == EventType.TOOL_RESPONSE]
    assert len(tool_req_events) == 1
    assert len(tool_resp_events) == 1
    assert tool_req_events[0].correlation_id == tool_resp_events[0].correlation_id

    # 6. Evaluation produced valid report
    assert summary.status == "COMPLETED"
    assert summary.derived_metrics.task_success is True


def test_mock_execution_recovery_flow():
    """Verify recovery loop: VERIFYING -> RECOVERY -> EXECUTING -> VERIFYING -> TESTING -> COMPLETED."""
    config = HarnessConfig()
    pipeline = MockExecutionPipeline(
        config=config,
        model_provider=PipelineMockModel(),
        skills={
            "planning": PipelineMockSkill("planning", "coding"),
            "coding": PipelineMockSkill("coding", "testing"),
            "testing": PipelineMockSkill("testing", ""),
        },
        tools={"file_writer": PipelineMockTool()},
        policy_engine=PipelineMockPolicy(),
        monitoring_manager=PipelineMockMonitoring(),
        evaluation_engine=PipelineMockEvaluation(),
    )

    task = MockTask(task_id="task-recovery", objective="Fix failing test case")
    summary = pipeline.run_pipeline(task, simulate_verification_failure_once=True)

    assert pipeline.state_machine.current_state == ExecutionState.COMPLETED
    history_states = [h.to_state for h in pipeline.state_machine.history]
    assert ExecutionState.RECOVERY in history_states

    # Verify recovery events
    event_types = [e.type for e in pipeline.events]
    assert EventType.RECOVERY_STARTED in event_types
    assert EventType.RECOVERY_COMPLETED in event_types


def test_mock_tool_denied_by_policy():
    """Verify policy denial triggers TOOL_POLICY_DECISION and DENIED status."""
    config = HarnessConfig()
    pipeline = MockExecutionPipeline(
        config=config,
        model_provider=PipelineMockModel(),
        skills={"coding": PipelineMockSkill("coding")},
        tools={"file_writer": PipelineMockTool()},
        policy_engine=PipelineMockPolicy(deny_tools=True),
        monitoring_manager=PipelineMockMonitoring(),
        evaluation_engine=PipelineMockEvaluation(),
    )

    res = pipeline.execute_tool_with_policy("file_writer", {"path": "/etc/shadow", "content": "bad"})
    assert res.status == ToolStatus.DENIED
    assert "Denied by policy" in res.error
