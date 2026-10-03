"""Mock execution pipeline proving architecture contracts and exit criteria for Phase 0."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import uuid

from harness.core.config import AutonomyLevel, HarnessConfig
from harness.core.events import Event, EventType
from harness.core.interfaces import (
    ChatMessage,
    EvaluationSummary,
    IEvaluationEngine,
    IMonitoringManager,
    IModelProvider,
    IPolicyEngine,
    ISkillSuite,
    ITool,
    ModelCallRecord,
    ModelRequest,
    ModelResponse,
    PolicyDecision,
    PolicyEvaluationContext,
    ResourceSample,
    SkillContext,
    SkillTransitionSummary,
    ToolRequest,
    ToolResponse,
    ToolStatus,
)
from harness.core.state import ExecutionState, ExecutionStateMachine


class MockTask:
    """Task representation for mock intake."""
    def __init__(self, task_id: str, objective: str, constraints: Optional[List[str]] = None):
        self.task_id = task_id
        self.objective = objective
        self.constraints = constraints or []


class MockScratchpad:
    """Structured execution scratchpad."""
    def __init__(self, objective: str):
        self.objective = objective
        self.constraints: List[str] = []
        self.subtasks: List[str] = []
        self.verification: List[str] = []
        self.completed: List[str] = []
        self.failed: List[str] = []
        self.pending: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective": self.objective,
            "constraints": self.constraints,
            "subtasks": self.subtasks,
            "verification": self.verification,
            "completed": self.completed,
            "failed": self.failed,
            "pending": self.pending,
        }


class MockExecutionPipeline:
    """Mock execution orchestrator proving Phase 0 architecture flow."""

    def __init__(
        self,
        config: HarnessConfig,
        model_provider: IModelProvider,
        skills: Dict[str, ISkillSuite],
        tools: Dict[str, ITool],
        policy_engine: IPolicyEngine,
        monitoring_manager: IMonitoringManager,
        evaluation_engine: IEvaluationEngine,
    ):
        self.config = config
        self.model_provider = model_provider
        self.skills = skills
        self.tools = tools
        self.policy_engine = policy_engine
        self.monitoring_manager = monitoring_manager
        self.evaluation_engine = evaluation_engine

        self.execution_id = f"exec-{uuid.uuid4().hex[:8]}"
        self.events: List[Event] = []
        self.model_records: List[ModelCallRecord] = []
        self.tool_responses: List[ToolResponse] = []
        self.resource_samples: List[ResourceSample] = []
        self.state_machine = ExecutionStateMachine(
            on_transition=self._on_state_transition
        )

        self.active_skill: Optional[ISkillSuite] = None
        self.continuity_summary: Optional[SkillTransitionSummary] = None
        self.scratchpad: Optional[MockScratchpad] = None

    def _record_event(
        self,
        event_type: EventType,
        source: str,
        payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Event:
        event = Event.create(
            execution_id=self.execution_id,
            type=event_type,
            source=source,
            payload=payload or {},
            correlation_id=correlation_id,
        )
        self.events.append(event)
        return event

    def _on_state_transition(self, record) -> None:
        self._record_event(
            EventType.EXECUTION_STATE_CHANGED,
            source="state_machine",
            payload=record.to_dict(),
        )

    def switch_skill(self, target_skill_name: str) -> None:
        """Switch active skill suite preserving continuity summary."""
        old_skill_name = self.active_skill.name if self.active_skill else None
        if self.active_skill:
            self.continuity_summary = self.active_skill.on_unload()
            self._record_event(
                EventType.SKILL_UNLOADED,
                source="skill_manager",
                payload={"skill": old_skill_name, "summary": self.continuity_summary.model_dump()},
            )

        new_skill = self.skills[target_skill_name]
        context = SkillContext(
            execution_id=self.execution_id,
            skill_name=target_skill_name,
            continuity_summary=self.continuity_summary,
            scratchpad_data=self.scratchpad.to_dict() if self.scratchpad else {},
        )
        new_skill.on_load(context)
        self.active_skill = new_skill

        self._record_event(
            EventType.SKILL_LOADED,
            source="skill_manager",
            payload={"skill": target_skill_name},
        )

    def execute_tool_with_policy(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> ToolResponse:
        """Execute tool going through request -> policy evaluation -> tool execution -> ledger."""
        tool = self.tools[tool_name]
        req = ToolRequest(
            execution_id=self.execution_id,
            tool_name=tool_name,
            arguments=arguments,
            source_skill=self.active_skill.name if self.active_skill else None,
        )

        self._record_event(
            EventType.TOOL_REQUEST,
            source="tool_manager",
            payload={"tool": tool_name, "arguments": arguments},
            correlation_id=req.tool_request_id,
        )

        policy_ctx = PolicyEvaluationContext(
            execution_id=self.execution_id,
            autonomy_level=self.config.execution.autonomy,
            tool_request=req,
            workspace_root=self.config.workspace.root,
        )
        policy_res = self.policy_engine.evaluate(policy_ctx)

        self._record_event(
            EventType.TOOL_POLICY_DECISION,
            source="policy_engine",
            payload={"decision": policy_res.decision.value, "reason": policy_res.reason},
            correlation_id=req.tool_request_id,
        )

        if policy_res.decision == PolicyDecision.DENY:
            res = ToolResponse(
                tool_request_id=req.tool_request_id,
                execution_id=self.execution_id,
                tool_name=tool_name,
                status=ToolStatus.DENIED,
                error=f"Denied by policy: {policy_res.reason}",
            )
        else:
            res = tool.execute(req)

        self.tool_responses.append(res)
        self._record_event(
            EventType.TOOL_RESPONSE,
            source="tool_manager",
            payload={"status": res.status.value, "output": res.output, "error": res.error},
            correlation_id=req.tool_request_id,
        )
        return res

    def run_pipeline(
        self,
        task: MockTask,
        simulate_verification_failure_once: bool = False,
    ) -> EvaluationSummary:
        """Run the complete mock execution lifecycle."""
        # 1. Intake
        self.state_machine.transition_to(ExecutionState.INTAKE, reason="Task intake received")
        self.scratchpad = MockScratchpad(objective=task.objective)
        self.scratchpad.constraints = task.constraints
        self._record_event(
            EventType.TASK_RECEIVED,
            source="task_intake",
            payload={"task_id": task.task_id, "objective": task.objective},
        )

        # 2. Planning
        self.state_machine.transition_to(ExecutionState.PLANNING, reason="Begin planning phase")
        self.switch_skill("planning")

        # Ask model to decompose
        plan_req = ModelRequest(
            execution_id=self.execution_id,
            messages=[ChatMessage(role="user", content=f"Plan: {task.objective}")],
            model=self.config.model.default_model,
        )
        plan_res = self.model_provider.generate(plan_req)
        self.model_records.append(plan_res.record)
        self._record_event(
            EventType.MODEL_RESPONSE,
            source="model_provider",
            payload={"call_id": plan_res.call_id, "content": plan_res.message.content},
            correlation_id=plan_res.call_id,
        )

        self.scratchpad.subtasks = ["subtask-1: scaffold", "subtask-2: write logic"]
        self.scratchpad.pending = list(self.scratchpad.subtasks)
        self._record_event(
            EventType.TASK_DECOMPOSED,
            source="planner",
            payload={"subtasks": self.scratchpad.subtasks},
        )

        # 3. Executing (Coding)
        self.state_machine.transition_to(ExecutionState.EXECUTING, reason="Start coding subtasks")
        self.switch_skill("coding")

        # Code execution: use tool to write code
        tool_res = self.execute_tool_with_policy(
            tool_name="file_writer",
            arguments={"path": "main.py", "content": "print('hello world')"},
        )
        self.scratchpad.completed.append("subtask-1: scaffold")
        self.scratchpad.pending.remove("subtask-1: scaffold")

        # Sample monitoring during execution
        sample = self.monitoring_manager.sample(self.execution_id)
        self.resource_samples.append(sample)
        self._record_event(
            EventType.RESOURCE_SAMPLE,
            source="monitoring_manager",
            payload={"cpu": sample.cpu.utilization_pct, "ram": sample.ram.used_mb},
        )

        # 4. Verifying
        self.state_machine.transition_to(ExecutionState.VERIFYING, reason="Verify coded modifications")
        self.switch_skill("testing")

        if simulate_verification_failure_once:
            # Recovery flow
            self._record_event(
                EventType.ERROR,
                source="verification",
                payload={"error": "AssertionError: expected 'hello world'"},
            )
            self.state_machine.transition_to(ExecutionState.RECOVERY, reason="Verification error encountered")
            self._record_event(
                EventType.RECOVERY_STARTED,
                source="recovery_manager",
                payload={"attempt": 1, "max_attempts": self.config.execution.max_recovery_attempts},
            )

            # Re-execute code fix
            self.state_machine.transition_to(ExecutionState.EXECUTING, reason="Executing fix after recovery")
            self.switch_skill("coding")
            self.execute_tool_with_policy(
                tool_name="file_writer",
                arguments={"path": "main.py", "content": "print('hello world fixed')"},
            )

            self._record_event(
                EventType.RECOVERY_COMPLETED,
                source="recovery_manager",
                payload={"attempt": 1, "status": "resolved"},
            )

            # Re-verify
            self.state_machine.transition_to(ExecutionState.VERIFYING, reason="Re-verifying after fix")

        self._record_event(
            EventType.TEST_RESULT,
            source="verification",
            payload={"passed": True, "tests_run": 1},
        )

        # 5. Testing (Application preview / interaction)
        self.state_machine.transition_to(ExecutionState.TESTING, reason="Run application interaction test")
        self._record_event(
            EventType.USER_FEEDBACK,
            source="application_tester",
            payload={"feedback": "approved", "rating": 5},
        )

        # 6. Completed
        self.state_machine.transition_to(ExecutionState.COMPLETED, reason="All stages passed successfully")
        self._record_event(
            EventType.EXECUTION_COMPLETED,
            source="execution_manager",
            payload={"status": "COMPLETED"},
        )

        # 7. Evaluation
        summary = self.evaluation_engine.evaluate(
            execution_id=self.execution_id,
            events=self.events,
            resource_samples=self.resource_samples,
            model_calls=self.model_records,
            tool_responses=self.tool_responses,
        )
        return summary
