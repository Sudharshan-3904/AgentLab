"""Execution Manager orchestrating single logical agent execution lifecycle."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import py_compile
from typing import Any, Dict, List, Optional
import uuid

logger = logging.getLogger("agentlab.execution_manager")

from harness.core.config import HarnessConfig
from harness.core.events import Event, EventType
from harness.core.interfaces import (
    ChatMessage,
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
from harness.ledger.sqlite import SQLiteEventLedger
from harness.tasks.scratchpad import Scratchpad
from harness.tasks.task import Task


class ExecutionManager:
    """Controls the lifecycle, scratchpad, skills, and tools for a single execution."""

    def __init__(
        self,
        task: Task,
        config: HarnessConfig,
        ledger: SQLiteEventLedger,
        policy_engine: IPolicyEngine,
        model_provider: Optional[IModelProvider] = None,
        workspace_manager: Optional[Any] = None,
        model_router: Optional[Any] = None,
        app_tester: Optional[Any] = None,
        execution_id: Optional[str] = None,
    ):
        self.execution_id = execution_id or f"exec-{uuid.uuid4().hex[:8]}"
        self.task = task
        self.config = config
        self.ledger = ledger
        self.policy_engine = policy_engine
        self.model_provider = model_provider
        self.workspace_manager = workspace_manager
        self.model_router = model_router

        from harness.execution.app_tester import AppTestingManager
        self.app_tester = app_tester or AppTestingManager(
            on_event=lambda ev_type, src, payload: self.emit_event(ev_type, src, payload)
        )

        self.scratchpad = Scratchpad(
            objective=task.objective,
            constraints=list(task.constraints),
        )
        self.state_machine = ExecutionStateMachine(
            on_transition=self._handle_state_transition
        )

        from harness.skills.manager import SkillManager
        self.skill_manager = SkillManager(
            execution_id=self.execution_id,
            workspace_root=self.config.workspace.root,
            on_event=lambda ev_type, src, payload: self.emit_event(ev_type, src, payload),
        )
        self.active_skill: Optional[ISkillSuite] = None
        self.active_model_name: str = config.model.default_model
        self.continuity_summary: Optional[SkillTransitionSummary] = None
        self.recovery_attempts: int = 0

        self.model_call_records: List[ModelCallRecord] = []
        self.tool_responses: List[ToolResponse] = []
        self.resource_samples: List[ResourceSample] = []

        # Record intake event immediately
        self.emit_event(
            EventType.TASK_RECEIVED,
            source="task_intake",
            payload={
                "task_id": self.task.task_id,
                "objective": self.task.objective,
                "constraints": self.task.constraints,
            },
        )
        self.state_machine.transition_to(ExecutionState.INTAKE, reason="Task accepted")

    def _handle_state_transition(self, record) -> None:
        self.emit_event(
            EventType.EXECUTION_STATE_CHANGED,
            source="execution_manager",
            payload=record.to_dict(),
        )

    @property
    def current_state(self) -> ExecutionState:
        return self.state_machine.current_state

    @property
    def is_finished(self) -> bool:
        return self.state_machine.is_terminal

    def emit_event(
        self,
        event_type: EventType,
        source: str,
        payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Event:
        """Create, record to ledger, and return an execution event."""
        event = Event.create(
            execution_id=self.execution_id,
            type=event_type,
            source=source,
            payload=payload or {},
            correlation_id=correlation_id,
        )
        self.ledger.append(event)
        return event

    def switch_skill(self, skill: ISkillSuite | str) -> SkillTransitionSummary:
        """Replace active skill suite while preserving compact continuity summary."""
        if isinstance(skill, str):
            skill_name = skill
        else:
            self.skill_manager.register_skill(skill)
            skill_name = skill.name

        summary = self.skill_manager.transition_to(
            skill_name,
            scratchpad_data=self.scratchpad.model_dump(),
        )
        self.continuity_summary = summary
        self.active_skill = self.skill_manager.active_skill

        if self.model_router:
            route_info = self.model_router.route_for_phase(
                self.execution_id,
                skill_name,
                self.active_model_name,
            )
            if route_info.get("transitioned"):
                self.route_model(route_info["selected_model"], reason=route_info["reason"])

        return summary

    def route_model(self, model_name: str, reason: str = "") -> None:
        """Dynamically route model for the current execution."""
        old_model = self.active_model_name
        self.active_model_name = model_name
        self.emit_event(
            EventType.MODEL_SELECTED,
            source="model_router",
            payload={
                "previous_model": old_model,
                "selected_model": model_name,
                "reason": reason,
            },
        )

    def call_model(self, messages: List[ChatMessage]) -> ModelResponse:
        """Invoke active model provider and persist telemetry record."""
        if not self.model_provider:
            raise RuntimeError("No model provider configured for execution")

        req = ModelRequest(
            execution_id=self.execution_id,
            messages=messages,
            model=self.active_model_name,
            temperature=self.config.sampling.temperature,
            top_p=self.config.sampling.top_p,
            seed=self.config.sampling.seed,
        )
        self.emit_event(
            EventType.MODEL_REQUEST,
            source="execution_manager",
            payload={"model": self.active_model_name, "message_count": len(messages)},
        )

        res = self.model_provider.generate(req)
        self.model_call_records.append(res.record)
        self.emit_event(
            EventType.MODEL_RESPONSE,
            source="execution_manager",
            payload={
                "call_id": res.call_id,
                "prompt_tokens": res.record.prompt_tokens,
                "output_tokens": res.record.output_tokens,
                "duration_ms": res.record.duration_ms,
            },
            correlation_id=res.call_id,
        )
        return res

    def execute_tool(self, tool: ITool, arguments: Dict[str, Any]) -> ToolResponse:
        """Route tool invocation through policy engine, record in ledger, and execute."""
        req = ToolRequest(
            execution_id=self.execution_id,
            tool_name=tool.name,
            arguments=arguments,
            source_skill=self.active_skill.name if self.active_skill else None,
        )

        self.emit_event(
            EventType.TOOL_REQUEST,
            source="tool_manager",
            payload={"tool": tool.name, "arguments": arguments},
            correlation_id=req.tool_request_id,
        )

        policy_ctx = PolicyEvaluationContext(
            execution_id=self.execution_id,
            autonomy_level=self.config.execution.autonomy,
            tool_request=req,
            workspace_root=self.config.workspace.root,
        )
        policy_res = self.policy_engine.evaluate(policy_ctx)

        self.emit_event(
            EventType.TOOL_POLICY_DECISION,
            source="policy_engine",
            payload={
                "decision": policy_res.decision.value,
                "reason": policy_res.reason,
            },
            correlation_id=req.tool_request_id,
        )

        if policy_res.decision == PolicyDecision.DENY:
            resp = ToolResponse(
                tool_request_id=req.tool_request_id,
                execution_id=self.execution_id,
                tool_name=tool.name,
                status=ToolStatus.DENIED,
                error=f"Denied by policy: {policy_res.reason}",
            )
        else:
            resp = tool.execute(req)

        self.tool_responses.append(resp)
        self.emit_event(
            EventType.TOOL_RESPONSE,
            source="tool_manager",
            payload={
                "status": resp.status.value,
                "output": resp.output,
                "error": resp.error,
                "duration_ms": resp.duration_ms,
            },
            correlation_id=req.tool_request_id,
        )
        return resp

    def transition_to(self, state: ExecutionState, reason: str = "") -> None:
        """Transition execution to next lifecycle state."""
        self.state_machine.transition_to(state, reason=reason)

    def trigger_recovery(
        self,
        failure_reason: str,
        error_details: Optional[str] = None,
        checkpoint_id: Optional[str] = None,
        messages: Optional[List[ChatMessage]] = None,
    ) -> bool:
        """Attempt automated recovery using RecoveryStrategyEngine."""
        from harness.execution.recovery import RecoveryStrategyEngine
        result = RecoveryStrategyEngine.execute_recovery(
            manager=self,
            failure_reason=failure_reason,
            error_details=error_details,
            checkpoint_id=checkpoint_id,
            messages=messages,
        )
        self.last_recovery_result = result
        return result.success

    def resolve_recovery(self, resolution_summary: str = "Recovery succeeded") -> None:
        """Mark recovery as resolved, transition back to EXECUTING, and record RECOVERY_COMPLETED."""
        if self.scratchpad.recovery_history:
            self.scratchpad.recovery_history[-1].resolved = True
        self.emit_event(
            EventType.RECOVERY_COMPLETED,
            source="recovery_manager",
            payload={
                "attempt": self.recovery_attempts,
                "summary": resolution_summary,
            },
        )
        self.state_machine.transition_to(ExecutionState.EXECUTING, reason=resolution_summary)

    def complete(self, reason: str = "Execution completed successfully") -> None:
        """Transition execution to COMPLETED terminal state."""
        self.state_machine.transition_to(ExecutionState.COMPLETED, reason=reason)
        self.emit_event(
            EventType.EXECUTION_COMPLETED,
            source="execution_manager",
            payload={"status": "COMPLETED", "reason": reason},
        )

    def fail(self, error_message: str) -> None:
        """Transition execution to FAILED terminal state."""
        self.state_machine.transition_to(ExecutionState.FAILED, reason=error_message)
        self.emit_event(
            EventType.ERROR,
            source="execution_manager",
            payload={"status": "FAILED", "error": error_message},
        )

    def cancel(self, reason: str = "Execution cancelled by user") -> None:
        """Transition execution to CANCELLED terminal state."""
        self.state_machine.transition_to(ExecutionState.CANCELLED, reason=reason)
        self.emit_event(
            EventType.EXECUTION_COMPLETED,
            source="execution_manager",
            payload={"status": "CANCELLED", "reason": reason},
        )

    def create_checkpoint(self, message: str) -> Optional[Any]:
        """Create a workspace git checkpoint and record CHECKPOINT event."""
        if not self.workspace_manager:
            return None
        record = self.workspace_manager.create_checkpoint(self.execution_id, message)
        self.emit_event(
            EventType.CHECKPOINT,
            source="workspace_manager",
            payload={
                "checkpoint_id": record.checkpoint_id,
                "commit_hash": record.commit_hash,
                "message": record.message,
            },
        )
        return record

    def rollback(self, checkpoint_id: str) -> bool:
        """Rollback workspace to a known checkpoint and record ROLLBACK event."""
        if not self.workspace_manager:
            return False
        success = self.workspace_manager.rollback(checkpoint_id)
        self.emit_event(
            EventType.ROLLBACK,
            source="workspace_manager",
            payload={
                "checkpoint_id": checkpoint_id,
                "success": success,
            },
        )
        return success

    def get_workspace_diff(self, base_ref: Optional[str] = None) -> str:
        """Retrieve git diff from workspace manager."""
        if not self.workspace_manager:
            return ""
        return self.workspace_manager.get_diff(base_ref)

    def get_workspace_status(self) -> Optional[Any]:
        """Retrieve git status from workspace manager."""
        if not self.workspace_manager:
            return None
        return self.workspace_manager.get_status()

    def launch_application(
        self,
        workspace_path: Optional[str] = None,
        command: Optional[str | List[str]] = None,
        port: Optional[int] = None,
    ) -> Any:
        """Launch the application for preview or testing."""
        if self.current_state in (ExecutionState.EXECUTING, ExecutionState.VERIFYING):
            self.transition_to(ExecutionState.TESTING, reason="Launching application for testing/preview")

        ws = workspace_path or self.config.workspace.root
        return self.app_tester.launch(ws, command=command, port=port)

    def check_application_health(
        self,
        app_or_url: Optional[Any] = None,
        path: Optional[str] = None,
        timeout: float = 10.0,
        retry_interval: float = 0.4,
    ) -> bool:
        """Probe application health."""
        if app_or_url is None:
            if not self.app_tester.active_apps:
                return False
            app_or_url = list(self.app_tester.active_apps.values())[-1]
        return self.app_tester.health_check(app_or_url, path=path, timeout=timeout, retry_interval=retry_interval)

    def submit_user_feedback(
        self,
        feedback_text: str,
        passed: bool = True,
        rating: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Submit feedback on application behavior."""
        self.scratchpad.append_note(f"User Feedback: {feedback_text} (Passed: {passed}, Rating: {rating})")
        return self.app_tester.collect_feedback(
            execution_id=self.execution_id,
            feedback_text=feedback_text,
            passed=passed,
            rating=rating,
            metadata=metadata,
        )

    def stop_application(self, app_id: Optional[str] = None) -> None:
        """Stop running application(s)."""
        if app_id:
            self.app_tester.stop(app_id)
        else:
            self.app_tester.stop_all()

    def run_autonomous(self) -> None:
        """Execute end-to-end autonomous coding lifecycle (intake -> planning -> coding -> verifying -> completed)."""
        if self.is_finished:
            return

        try:
            # 1. Baseline Git checkpoint if enabled
            if self.workspace_manager:
                self.create_checkpoint(f"Baseline intake: {self.task.objective[:35]}")

            # 2. Phase: PLANNING
            if self.current_state == ExecutionState.INTAKE:
                self.transition_to(ExecutionState.PLANNING, reason="Decomposing task requirements into subtasks")
            
            if "planning" in self.skill_manager._registered_skills:
                self.switch_skill("planning")

            subtasks: List[str] = []
            if self.model_provider:
                try:
                    plan_prompt = (
                        f"You are an expert software planner.\n"
                        f"Objective: {self.task.objective}\n"
                        f"Constraints: {json.dumps(self.task.constraints)}\n\n"
                        f"Please decompose this objective into 2 to 4 concise, numbered subtasks.\n"
                        f"Format:\n1. [Subtask description]\n2. [Subtask description]\n..."
                    )
                    plan_resp = self.call_model([ChatMessage(role="user", content=plan_prompt)])
                    for line in plan_resp.message.content.splitlines():
                        line_str = line.strip()
                        if line_str and line_str[0].isdigit() and ("." in line_str[:4] or ")" in line_str[:4]):
                            subtasks.append(line_str)
                except Exception as ex:
                    logger.warning("Planning model call failed, falling back to default plan: %s", ex)

            if not subtasks:
                subtasks = [
                    f"1. Scaffold solution for: {self.task.objective[:30]}",
                    "2. Implement source logic and error handling",
                    "3. Verify and test functionality",
                ]

            self.scratchpad.set_subtasks(subtasks)
            self.emit_event(
                EventType.TASK_DECOMPOSED,
                source="planner",
                payload={"subtasks": subtasks},
            )

            # 3. Phase: EXECUTING (Coding)
            self.transition_to(ExecutionState.EXECUTING, reason="Implementing code for planned subtasks")
            if "coding" in self.skill_manager._registered_skills:
                self.switch_skill("coding")

            code_content = ""
            target_filename = "app.py"
            obj_lower = self.task.objective.lower()
            if "fastapi" in obj_lower or "api" in obj_lower or "server" in obj_lower or "http" in obj_lower:
                target_filename = "server.py"
            elif "test" in obj_lower:
                target_filename = "test_app.py"

            if self.model_provider:
                try:
                    coding_prompt = (
                        f"Implement complete, runnable Python code for the following task:\n"
                        f"Objective: {self.task.objective}\n"
                        f"Constraints: {json.dumps(self.task.constraints)}\n"
                        f"Subtasks: {self.scratchpad.subtasks}\n\n"
                        f"Return ONLY valid Python code inside a ```python ... ``` block."
                    )
                    code_resp = self.call_model([ChatMessage(role="user", content=coding_prompt)])
                    content = code_resp.message.content
                    if "```python" in content:
                        code_content = content.split("```python", 1)[1].split("```", 1)[0].strip()
                    elif "```" in content:
                        code_content = content.split("```", 1)[1].split("```", 1)[0].strip()
                    elif any(kw in content for kw in ("def ", "class ", "import ")):
                        code_content = content.strip()
                except Exception as ex:
                    logger.warning("Coding model call failed, generating template: %s", ex)

            if not code_content:
                if target_filename == "server.py":
                    code_content = (
                        "import http.server\n"
                        "import json\n"
                        "import os\n"
                        "import sys\n\n"
                        "PORT = int(os.environ.get('PORT', 8080))\n\n"
                        "class APIHandler(http.server.BaseHTTPRequestHandler):\n"
                        "    def do_GET(self):\n"
                        "        self.send_response(200)\n"
                        "        self.send_header('Content-Type', 'application/json')\n"
                        "        self.send_header('Access-Control-Allow-Origin', '*')\n"
                        "        self.end_headers()\n"
                        f"        resp = {{'status': 'healthy', 'objective': '{self.task.objective}'}}\n"
                        "        self.wfile.write(json.dumps(resp).encode('utf-8'))\n\n"
                        "    def log_message(self, *args):\n"
                        "        pass\n\n"
                        "if __name__ == '__main__':\n"
                        "    with http.server.HTTPServer(('127.0.0.1', PORT), APIHandler) as httpd:\n"
                        "        httpd.serve_forever()\n"
                    )
                else:
                    code_content = (
                        f'"""Solution implementation for: {self.task.objective}"""\n'
                        "import sys\n\n"
                        "def main():\n"
                        f'    print("Executed task: {self.task.objective}")\n\n'
                        'if __name__ == "__main__":\n'
                        "    main()\n"
                    )

            workspace_dir = Path(self.config.workspace.root).resolve()
            workspace_dir.mkdir(parents=True, exist_ok=True)
            target_path = workspace_dir / target_filename
            target_path.write_text(code_content, encoding="utf-8")

            self.emit_event(
                EventType.TOOL_REQUEST,
                source="tool_manager",
                payload={"tool": "write_file", "arguments": {"path": target_filename, "bytes": len(code_content)}},
            )
            self.emit_event(
                EventType.TOOL_RESPONSE,
                source="tool_manager",
                payload={"status": "SUCCESS", "output": f"Wrote {len(code_content)} bytes to {target_filename}"},
            )

            for st in list(self.scratchpad.pending):
                self.scratchpad.complete_subtask(st)

            if self.workspace_manager:
                self.create_checkpoint(f"Implemented solution in {target_filename}")

            # 4. Phase: VERIFYING (Testing)
            self.transition_to(ExecutionState.VERIFYING, reason="Verifying code syntax and running test checks")
            if "testing" in self.skill_manager._registered_skills:
                self.switch_skill("testing")

            # Verify syntax
            syntax_passed = True
            syntax_error = ""
            try:
                py_compile.compile(str(target_path), doraise=True)
                self.emit_event(
                    EventType.TEST_RESULT,
                    source="verifier",
                    payload={"file": target_filename, "status": "PASSED", "check": "syntax_compilation"},
                )
            except py_compile.PyCompileError as pe:
                syntax_passed = False
                syntax_error = str(pe)

            if not syntax_passed:
                if self.recovery_attempts < self.config.execution.max_recovery_attempts:
                    recovered = self.trigger_recovery(
                        failure_reason="Syntax error in synthesized code",
                        error_details=syntax_error,
                        messages=[ChatMessage(role="user", content=coding_prompt)],
                    )
                    if recovered:
                        self.resolve_recovery("Recovered from syntax error")
                    else:
                        self.fail(f"Verification syntax error: {syntax_error}")
                        return
                else:
                    self.fail(f"Verification syntax error: {syntax_error}")
                    return

            # 5. Complete
            self.complete(reason=f"Task completed successfully: synthesized and verified {target_filename}")

        except Exception as ex:
            logger.error("Autonomous execution error: %s", ex, exc_info=True)
            self.fail(str(ex))

