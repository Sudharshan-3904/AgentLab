"""Phase 12 Comprehensive MVP Validation Integration Test.

Validates all 11 MVP Completion Criteria from docs/MVP_Roadmap.md:
1. Accept a coding task
2. Plan it
3. Switch skill suites
4. Route models
5. Use tools
6. Modify files
7. Run tests
8. Recover once
9. Let the user interact with the application
10. Monitor resources
11. Preserve an execution ledger
"""

import json
from pathlib import Path
import sys
import urllib.request
import pytest

from harness.core.config import HarnessConfig
from harness.core.events import EventType
from harness.core.harness import Harness
from harness.core.interfaces import (
    ChatMessage,
    ModelCallRecord,
    ModelRequest,
    ModelResponse,
    ToolRequest,
    ToolStatus,
)
from harness.core.state import ExecutionState
from harness.evaluation.engine import EvaluationEngine
from harness.models.interface import IModelProvider, ModelHealth, ModelMetadata
from harness.skills.suites import CodingSkillSuite, PlanningSkillSuite, TestingSkillSuite
from harness.tasks.task import Task
from harness.tools.fs import ReadFileTool, WriteFileTool
from harness.tools.testing import TestRunnerTool
from tests.test_interfaces import MockModelProvider, MockPolicyEngine


class ComprehensiveMVPModelProvider(MockModelProvider):
    """Provides adaptive responses for planning, buggy coding, and recovery."""

    def __init__(self):
        self.call_count = 0

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.call_count += 1
        prompt = " ".join(m.content for m in request.messages)

        if "TEST_FAILURE" in prompt or "AssertionError" in prompt or "failure" in prompt:
            # Recovery response: correct code
            code = (
                "import http.server\n"
                "import json\n"
                "import os\n"
                "import sys\n\n"
                "PORT = int(os.environ.get('PORT', sys.argv[1] if len(sys.argv) > 1 else 8080))\n\n"
                "class Handler(http.server.BaseHTTPRequestHandler):\n"
                "    def do_GET(self):\n"
                "        self.send_response(200)\n"
                "        self.send_header('Content-Type', 'application/json')\n"
                "        self.end_headers()\n"
                "        self.wfile.write(json.dumps({'status': 'healthy', 'result': 42}).encode('utf-8'))\n\n"
                "    def log_message(self, *args):\n"
                "        pass\n\n"
                "if __name__ == '__main__':\n"
                "    with http.server.HTTPServer(('127.0.0.1', PORT), Handler) as s:\n"
                "        s.serve_forever()\n"
            )
            text = f"Corrected application code:\n```python\n{code}\n```"
        elif "plan" in prompt.lower():
            code = ""
            text = "Plan:\n1. Create server\n2. Run tests\n3. Launch preview"
        else:
            # Buggy initial code (missing json module or deliberate failure)
            code = (
                "import http.server\n"
                "import sys\n\n"
                "class Handler(http.server.BaseHTTPRequestHandler):\n"
                "    def do_GET(self):\n"
                "        raise RuntimeError('Deliberate bug in initial code')\n"
            )
            text = f"Initial code with deliberate bug:\n```python\n{code}\n```"

        record = ModelCallRecord(
            call_id=f"call-{self.call_count}",
            execution_id=request.execution_id,
            provider="mock-llm",
            model=request.model or "mock-model",
            temperature=request.temperature,
            top_p=request.top_p,
            started_at="2026-10-03T21:00:00Z",
            completed_at="2026-10-03T21:00:01Z",
            prompt_tokens=80,
            output_tokens=40,
            duration_ms=120.0,
            success=True,
        )

        return ModelResponse(
            call_id=f"call-{self.call_count}",
            message=ChatMessage(role="assistant", content=text),
            record=record,
            raw_response={"code": code},
        )


def test_complete_mvp_validation_criteria(tmp_path: Path):
    """Verify all 11 MVP Completion Criteria systematically in an end-to-end run."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db_file = tmp_path / "mvp_validation.db"

    config = HarnessConfig()
    config.workspace.root = str(workspace)
    config.workspace.git_enabled = True
    config.execution.max_recovery_attempts = 1
    config.routing.enabled = True
    config.routing.rules = {
        "planning": "deepseek-r1",
        "coding": "qwen2.5-coder",
        "testing": "llama3.2",
    }

    model = ComprehensiveMVPModelProvider()

    harness = Harness(
        config=config,
        db_path=str(db_file),
        model_providers={"ollama": model, "mock": model},
        policy_engine=MockPolicyEngine(),
    )
    harness.register_skill(PlanningSkillSuite())
    harness.register_skill(CodingSkillSuite())
    harness.register_skill(TestingSkillSuite())
    harness.register_tool(WriteFileTool(str(workspace)))
    harness.register_tool(ReadFileTool(str(workspace)))
    harness.register_tool(TestRunnerTool(str(workspace)))

    # -------------------------------------------------------------
    # CRITERION 1: Accept a coding task
    # -------------------------------------------------------------
    task = Task.from_prompt("Build an HTTP service returning status healthy and result 42")
    execution = harness.create_execution(task)
    assert execution.current_state == ExecutionState.INTAKE
    assert execution.task.objective == "Build an HTTP service returning status healthy and result 42"

    # -------------------------------------------------------------
    # CRITERION 2: Plan it
    # -------------------------------------------------------------
    execution.transition_to(ExecutionState.PLANNING, reason="Decompose architecture and steps")
    assert execution.current_state == ExecutionState.PLANNING

    execution.scratchpad.set_subtasks([
        "Define HTTP server",
        "Implement endpoint",
        "Verify with health check",
    ])
    assert len(execution.scratchpad.pending) == 3

    # -------------------------------------------------------------
    # CRITERION 3 & 4: Switch skill suites & Route models
    # -------------------------------------------------------------
    # Load Planning suite -> routes model to deepseek-r1
    execution.switch_skill(PlanningSkillSuite())
    assert execution.active_skill.name == "planning"
    assert execution.active_model_name == "deepseek-r1"

    # Switch to Coding suite -> routes model to qwen2.5-coder
    execution.switch_skill(CodingSkillSuite())
    assert execution.active_skill.name == "coding"
    assert execution.active_model_name == "qwen2.5-coder"

    # -------------------------------------------------------------
    # CRITERION 5 & 6: Use tools & Modify files
    # -------------------------------------------------------------
    execution.transition_to(ExecutionState.EXECUTING, reason="Write initial code")

    # Create git baseline checkpoint
    cp = execution.create_checkpoint("Clean baseline before generating code")
    assert cp is not None

    writer = WriteFileTool(str(workspace))
    # Write buggy initial server
    write_res = writer.execute(
        ToolRequest(
            execution_id=execution.execution_id,
            tool_name="write_file",
            arguments={"path": "server.py", "content": "import http.server\ndef broken(): raise RuntimeError('syntax bug')\n"},
        )
    )
    assert write_res.status == ToolStatus.SUCCESS
    assert (workspace / "server.py").exists()

    # -------------------------------------------------------------
    # CRITERION 7: Run tests
    # -------------------------------------------------------------
    execution.transition_to(ExecutionState.VERIFYING, reason="Run test check")
    test_runner = TestRunnerTool(str(workspace))
    # Create a quick test file
    (workspace / "test_app.py").write_text(
        "import server\ndef test_sanity():\n    server.broken()\n",
        encoding="utf-8",
    )
    test_res = test_runner.execute(
        ToolRequest(
            execution_id=execution.execution_id,
            tool_name="test_runner",
            arguments={"test_path": "test_app.py"},
        )
    )
    assert test_res.status == ToolStatus.ERROR

    # -------------------------------------------------------------
    # CRITERION 8: Recover once
    # -------------------------------------------------------------
    recovered = execution.trigger_recovery(
        failure_reason="Test failed: RuntimeError in server.broken",
        error_details=test_res.output["stdout"],
    )
    assert recovered is True
    assert execution.current_state == ExecutionState.RECOVERY
    assert execution.recovery_attempts == 1
    assert execution.last_recovery_result.rollback_performed is True

    # Model provides corrected code on recovery prompt
    rec_prompt = execution.last_recovery_result.recovery_prompt
    fixed_response = model.generate(
        ModelRequest(
            execution_id=execution.execution_id,
            messages=rec_prompt,
        )
    )
    fixed_code = fixed_response.raw_response["code"]
    (workspace / "server.py").write_text(fixed_code, encoding="utf-8")

    # Resolve recovery
    execution.resolve_recovery("Restored baseline and wrote working HTTP server")
    assert execution.current_state == ExecutionState.EXECUTING

    # -------------------------------------------------------------
    # CRITERION 9: Let user interact with the application
    # -------------------------------------------------------------
    launched = execution.launch_application(
        workspace_path=str(workspace),
        command=[sys.executable, "server.py", "{port}"],
    )
    try:
        assert execution.current_state == ExecutionState.TESTING
        assert launched.is_alive()

        # Health check
        healthy = execution.check_application_health(launched, timeout=8.0, retry_interval=0.3)
        assert healthy is True

        # HTTP interaction
        with urllib.request.urlopen(f"{launched.url}/", timeout=2.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "healthy"
            assert data["result"] == 42

        # User feedback
        fb = execution.submit_user_feedback(
            feedback_text="Application verified: status is healthy and result is 42.",
            passed=True,
            rating=5,
        )
        assert fb["passed"] is True

        # Complete execution
        execution.complete("All criteria met successfully")
        assert execution.current_state == ExecutionState.COMPLETED
    finally:
        execution.stop_application()
        assert not launched.is_alive()

    # -------------------------------------------------------------
    # CRITERION 10: Monitor resources
    # -------------------------------------------------------------
    metrics = harness.get_live_resource_metrics(execution.execution_id)
    assert metrics is not None
    assert metrics.cpu is not None
    assert metrics.ram is not None

    # -------------------------------------------------------------
    # CRITERION 11: Preserve an execution ledger
    # -------------------------------------------------------------
    events = harness.ledger.get_events(execution.execution_id)
    assert len(events) >= 10
    event_types = {e.type for e in events}

    expected_types = {
        EventType.TASK_RECEIVED,
        EventType.EXECUTION_STATE_CHANGED,
        EventType.SKILL_LOADED,
        EventType.MODEL_SELECTED,
        EventType.CHECKPOINT,
        EventType.RECOVERY_STARTED,
        EventType.ROLLBACK,
        EventType.RECOVERY_COMPLETED,
        EventType.APPLICATION_LAUNCHED,
        EventType.APPLICATION_HEALTH_CHECK,
        EventType.USER_FEEDBACK,
        EventType.APPLICATION_STOPPED,
        EventType.EXECUTION_COMPLETED,
    }
    for et in expected_types:
        assert et in event_types, f"Expected event type {et} not found in ledger"

    # Export to JSONL
    export_file = tmp_path / "final_audit.jsonl"
    harness.ledger.export_jsonl(execution.execution_id, str(export_file))
    assert export_file.exists()
    assert export_file.stat().st_size > 0

    # -------------------------------------------------------------
    # EVALUATION REPORT
    # -------------------------------------------------------------
    eval_engine = EvaluationEngine()
    summary = eval_engine.evaluate(
        execution_id=execution.execution_id,
        events=events,
        model_calls=[fixed_response.record],
        tool_responses=[write_res],
    )
    assert summary.derived_metrics.task_success is True
    assert summary.derived_metrics.execution_efficiency_score > 80.0
    assert summary.raw_metrics.skill_transitions_count >= 2
    assert summary.raw_metrics.model_transitions_count >= 1
    assert summary.raw_metrics.recovery_attempts_count == 1

    harness.close()
