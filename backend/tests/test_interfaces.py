"""Tests verifying Phase 0 interfaces and contract implementations."""

import pytest
from harness.core.config import AutonomyLevel
from harness.core.interfaces import (
    ChatMessage,
    IModelProvider,
    ModelCallRecord,
    ModelChunk,
    ModelHealth,
    ModelMetadata,
    ModelRequest,
    ModelResponse,
    ITool,
    ToolDefinition,
    ToolRequest,
    ToolResponse,
    ToolStatus,
    IPolicyEngine,
    PolicyDecision,
    PolicyEvaluationContext,
    PolicyEvaluationResult,
    ISkillSuite,
    SkillContext,
    SkillTransitionSummary,
    SkillType,
    IMonitoringManager,
    ResourceSample,
    CpuMetrics,
    RamMetrics,
    ProcessMetrics,
    IEvaluationEngine,
    EvaluationSummary,
    RawMetrics,
    DerivedMetrics,
    IWorkspaceManager,
    CheckpointRecord,
    WorkspaceStatus,
    ISandboxRuntime,
    SandboxExecutionResult,
    SandboxStatus,
)


class MockModelProvider(IModelProvider):
    def generate(self, request: ModelRequest) -> ModelResponse:
        record = ModelCallRecord(
            call_id="call-001",
            execution_id=request.execution_id,
            provider="mock-ollama",
            model=request.model or "llama3.2",
            temperature=request.temperature,
            top_p=request.top_p,
            started_at="2026-10-03T20:00:00Z",
            completed_at="2026-10-03T20:00:01Z",
            prompt_tokens=100,
            output_tokens=50,
            duration_ms=1000.0,
            success=True,
        )
        return ModelResponse(
            call_id="call-001",
            message=ChatMessage(role="assistant", content="Mock model output"),
            record=record,
        )

    def stream(self, request: ModelRequest):
        yield ModelChunk(delta="Hello ")
        yield ModelChunk(delta="World", finish_reason="stop")

    def health(self) -> ModelHealth:
        return ModelHealth(available=True, latency_ms=12.5)

    def metadata(self, model_name=None) -> ModelMetadata:
        return ModelMetadata(name=model_name or "mock-model", provider="mock")


class MockTool(ITool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="mock_write",
            description="Writes text to a mock file",
            parameters={"path": "string", "content": "string"},
            danger_level="normal",
        )

    def execute(self, request: ToolRequest) -> ToolResponse:
        return ToolResponse(
            tool_request_id=request.tool_request_id,
            execution_id=request.execution_id,
            tool_name=self.name,
            status=ToolStatus.SUCCESS,
            output=f"Wrote {len(request.arguments.get('content', ''))} bytes",
            duration_ms=25.0,
        )


class MockPolicyEngine(IPolicyEngine):
    def evaluate(self, context: PolicyEvaluationContext) -> PolicyEvaluationResult:
        if context.autonomy_level == AutonomyLevel.RESTRICTED:
            return PolicyEvaluationResult(
                decision=PolicyDecision.CONFIRM,
                reason="Restricted mode requires confirmation",
            )
        return PolicyEvaluationResult(
            decision=PolicyDecision.ALLOW,
            reason="Operation allowed under balanced/autonomous mode",
        )


class MockSkillSuite(ISkillSuite):
    @property
    def name(self) -> str:
        return "planning"

    @property
    def description(self) -> str:
        return "Decomposes user objectives into plans"

    @property
    def system_prompt(self) -> str:
        return "You are an expert system planner."

    @property
    def tools(self):
        return [MockTool()]

    def on_load(self, context: SkillContext) -> None:
        self.context = context

    def on_unload(self) -> SkillTransitionSummary:
        return SkillTransitionSummary(
            source_skill=self.name,
            target_skill="coding",
            objective="Build app",
            completed_work=["Task decomposed"],
            pending_work=["Implement code"],
            next_verification_step="Run pytest",
        )


class MockMonitoringManager(IMonitoringManager):
    def __init__(self):
        self.samples = []

    def sample(self, execution_id: str) -> ResourceSample:
        sample = ResourceSample(
            sample_id="samp-001",
            execution_id=execution_id,
            cpu=CpuMetrics(utilization_pct=15.0),
            ram=RamMetrics(used_mb=2048.0, total_mb=16384.0, available_mb=14336.0, percent=12.5),
            process=ProcessMetrics(pid=1234, cpu_percent=2.5, rss_memory_mb=120.0),
        )
        self.samples.append(sample)
        return sample

    def start_monitoring(self, execution_id: str, interval_ms: int = 500) -> None:
        pass

    def stop_monitoring(self, execution_id: str):
        return self.samples

    def get_samples(self, execution_id: str):
        return self.samples


class MockEvaluationEngine(IEvaluationEngine):
    def evaluate(self, execution_id, events, resource_samples=None, model_calls=None, tool_responses=None):
        return EvaluationSummary(
            execution_id=execution_id,
            task_objective="Mock execution objective",
            status="COMPLETED",
            raw_metrics=RawMetrics(
                total_duration_s=5.0,
                model_duration_s=1.0,
                tool_duration_s=0.5,
                model_calls_count=len(model_calls or []),
                tool_calls_count=len(tool_responses or []),
                prompt_tokens=100,
                output_tokens=50,
                total_tokens=150,
                peak_cpu_percent=15.0,
                avg_cpu_percent=10.0,
            ),
            derived_metrics=DerivedMetrics(
                task_success=True,
                tokens_per_second=30.0,
                tool_success_rate=1.0,
                model_success_rate=1.0,
                execution_efficiency_score=0.95,
            ),
        )


def test_mock_model_provider_contract():
    provider = MockModelProvider()
    health = provider.health()
    assert health.available is True

    meta = provider.metadata("llama3.2")
    assert meta.name == "llama3.2"

    req = ModelRequest(
        execution_id="exec-contract-1",
        messages=[ChatMessage(role="user", content="Hello")],
    )
    res = provider.generate(req)
    assert res.call_id == "call-001"
    assert res.message.content == "Mock model output"
    assert res.record.prompt_tokens == 100

    chunks = list(provider.stream(req))
    assert len(chunks) == 2
    assert chunks[0].delta == "Hello "


def test_mock_tool_and_policy_engine_contract():
    tool = MockTool()
    assert tool.name == "mock_write"
    assert tool.definition.danger_level == "normal"

    req = ToolRequest(
        execution_id="exec-tool-1",
        tool_name="mock_write",
        arguments={"path": "test.txt", "content": "hello world"},
    )
    res = tool.execute(req)
    assert res.status == ToolStatus.SUCCESS
    assert "Wrote 11 bytes" in res.output

    policy = MockPolicyEngine()
    ctx_balanced = PolicyEvaluationContext(
        execution_id="exec-tool-1",
        autonomy_level=AutonomyLevel.BALANCED,
        tool_request=req,
        workspace_root="./workspace",
    )
    decision_balanced = policy.evaluate(ctx_balanced)
    assert decision_balanced.decision == PolicyDecision.ALLOW

    ctx_restricted = PolicyEvaluationContext(
        execution_id="exec-tool-1",
        autonomy_level=AutonomyLevel.RESTRICTED,
        tool_request=req,
        workspace_root="./workspace",
    )
    decision_restricted = policy.evaluate(ctx_restricted)
    assert decision_restricted.decision == PolicyDecision.CONFIRM


def test_mock_skill_lifecycle_contract():
    skill = MockSkillSuite()
    assert skill.name == "planning"
    assert len(skill.tools) == 1

    ctx = SkillContext(execution_id="exec-skill-1", skill_name="planning")
    skill.on_load(ctx)
    assert skill.context.execution_id == "exec-skill-1"

    summary = skill.on_unload()
    assert summary.source_skill == "planning"
    assert summary.target_skill == "coding"
    assert "Task decomposed" in summary.completed_work
    assert summary.next_verification_step == "Run pytest"


def test_mock_monitoring_and_evaluation_contract():
    monitor = MockMonitoringManager()
    sample = monitor.sample("exec-eval-1")
    assert sample.cpu.utilization_pct == 15.0
    assert sample.ram.used_mb == 2048.0

    eval_engine = MockEvaluationEngine()
    summary = eval_engine.evaluate(
        execution_id="exec-eval-1",
        events=[],
        resource_samples=[sample],
        model_calls=[ModelCallRecord(
            call_id="c1", execution_id="exec-eval-1", provider="mock",
            model="m", temperature=0.2, top_p=0.9, started_at="",
            completed_at="", duration_ms=100.0
        )],
        tool_responses=[ToolResponse(
            tool_request_id="t1", execution_id="exec-eval-1",
            tool_name="mock_write", status=ToolStatus.SUCCESS
        )],
    )

    assert summary.raw_metrics.model_calls_count == 1
    assert summary.raw_metrics.tool_calls_count == 1
    assert summary.derived_metrics.task_success is True
    assert summary.derived_metrics.tokens_per_second == 30.0
