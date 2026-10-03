"""Phase 10 Integration Test: Automated Recovery Exit Criteria.

Exit Criteria:
Basic failures can automatically recover.
"""

from pathlib import Path
import pytest

from harness.core.config import HarnessConfig
from harness.core.events import EventType
from harness.core.harness import Harness
from harness.core.interfaces import (
    ChatMessage,
    ModelHealth,
    ModelMetadata,
    ModelRequest,
    ModelResponse,
    ToolRequest,
    ToolResponse,
    ToolStatus,
)
from harness.core.state import ExecutionState
from harness.models.interface import IModelProvider
from harness.tasks.task import Task
from harness.tools.fs import ReadFileTool, WriteFileTool
from harness.tools.testing import TestRunnerTool
from tests.test_interfaces import MockModelProvider, MockPolicyEngine


class SelfCorrectingModelProvider(MockModelProvider):
    """Simulates a model that fails on the first attempt with a bug,

    but fixes the bug when presented with the recovery/error prompt.
    """

    def __init__(self):
        self.call_count = 0

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.call_count += 1
        prompt_texts = " ".join(m.content for m in request.messages)

        if "TEST_FAILURE" in prompt_texts or "AssertionError" in prompt_texts or "failed" in prompt_texts:
            # Corrected implementation on retry
            code = (
                "def solve(n: int) -> int:\n"
                "    return n * 2\n\n"
                "def test_solve():\n"
                "    assert solve(5) == 10\n"
            )
            explanation = "Fixed bug: now correctly returns n * 2."
        else:
            # Buggy initial implementation
            code = (
                "def solve(n: int) -> int:\n"
                "    return n + 1\n\n"
                "def test_solve():\n"
                "    assert solve(5) == 10\n"
            )
            explanation = "Initial implementation with deliberate bug."

        from harness.models.interface import ModelCallRecord
        record = ModelCallRecord(
            call_id=f"call-{self.call_count}",
            execution_id=request.execution_id,
            provider="mock",
            model="mock-self-correcting",
            temperature=request.temperature,
            top_p=request.top_p,
            started_at="2026-10-03T20:00:00Z",
            completed_at="2026-10-03T20:00:01Z",
            prompt_tokens=40,
            output_tokens=25,
            duration_ms=100.0,
            success=True,
        )
        return ModelResponse(
            call_id=f"call-{self.call_count}",
            message=ChatMessage(role="assistant", content=f"{explanation}\n```python\n{code}\n```"),
            record=record,
            raw_response={"code": code},
        )


def test_phase10_exit_criteria_automated_recovery(tmp_path: Path):
    """Verify that a task failure triggers automated diagnosis, rollback,

    scratchpad tracking, model re-prompting, and successful recovery.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db_file = tmp_path / "recovery_integration.db"

    config = HarnessConfig()
    config.workspace.root = str(workspace)
    config.workspace.git_enabled = True
    config.execution.max_recovery_attempts = 1

    model = SelfCorrectingModelProvider()
    harness = Harness(
        config=config,
        db_path=str(db_file),
        model_providers={"mock": model},
        policy_engine=MockPolicyEngine(),
    )
    harness.register_tool(WriteFileTool(str(workspace)))
    harness.register_tool(ReadFileTool(str(workspace)))
    harness.register_tool(TestRunnerTool(str(workspace)))

    execution = harness.create_execution("Implement solve(n) returning double n")
    assert execution.current_state == ExecutionState.INTAKE

    # Step 1: Planning and baseline checkpoint
    execution.transition_to(ExecutionState.PLANNING, reason="Decompose math problem")
    execution.transition_to(ExecutionState.EXECUTING, reason="Write implementation")

    initial_checkpoint = execution.create_checkpoint("Clean baseline before implementation")
    assert initial_checkpoint is not None

    # Step 2: First attempt (model produces buggy code)
    response_1 = model.generate(
        ModelRequest(
            execution_id=execution.execution_id,
            messages=[ChatMessage(role="user", content="Implement solve(n) returning double n")],
        )
    )
    buggy_code = response_1.raw_response["code"]
    solve_file = workspace / "solution.py"
    solve_file.write_text(buggy_code, encoding="utf-8")

    # Step 3: Run test verification
    execution.transition_to(ExecutionState.VERIFYING, reason="Verify solution with pytest")
    runner = TestRunnerTool(str(workspace))
    test_result = runner.execute(ToolRequest(execution_id=execution.execution_id, tool_name="test_runner", arguments={"test_path": "solution.py"}))
    assert test_result.status == ToolStatus.ERROR
    assert "FAILED" in test_result.output["stdout"] or "AssertionError" in test_result.output["stdout"]

    # Step 4: Autonomous recovery triggered by failure
    recovered = execution.trigger_recovery(
        failure_reason="AssertionError in test_solve: assert solve(5) == 10",
        error_details=test_result.output["stdout"],
    )
    assert recovered is True
    assert execution.current_state == ExecutionState.RECOVERY
    assert execution.recovery_attempts == 1
    assert execution.last_recovery_result is not None
    assert execution.last_recovery_result.rollback_performed is True

    # Scratchpad accurately reflects recovery state
    assert len(execution.scratchpad.recovery_history) == 1
    rec_entry = execution.scratchpad.recovery_history[0]
    assert rec_entry.attempt == 1
    assert "TEST_FAILURE" in rec_entry.failure_description
    assert rec_entry.resolved is False

    # Step 5: Model is re-sent the recovery prompt
    recovery_prompt = execution.last_recovery_result.recovery_prompt
    response_2 = model.generate(
        ModelRequest(
            execution_id=execution.execution_id,
            messages=recovery_prompt,
        )
    )

    # Step 6: Apply corrected code
    fixed_code = response_2.raw_response["code"]
    solve_file.write_text(fixed_code, encoding="utf-8")

    # Step 7: Resolve recovery and re-verify
    execution.resolve_recovery("Fixed assertion bug in solution.py")
    assert execution.current_state == ExecutionState.EXECUTING

    execution.transition_to(ExecutionState.VERIFYING, reason="Re-verify fixed solution")
    second_test_result = runner.execute(ToolRequest(execution_id=execution.execution_id, tool_name="test_runner", arguments={"test_path": "solution.py"}))
    assert second_test_result.status == ToolStatus.SUCCESS

    # Complete execution
    execution.complete("Task solved with automated recovery")
    assert execution.current_state == ExecutionState.COMPLETED
    assert execution.scratchpad.recovery_history[0].resolved is True

    # Step 8: Verify all required ledger events
    events = harness.ledger.get_events(execution.execution_id)
    event_types = [e.type for e in events]

    assert EventType.CHECKPOINT in event_types
    assert EventType.ROLLBACK in event_types
    assert EventType.RECOVERY_STARTED in event_types
    assert EventType.RECOVERY_COMPLETED in event_types
    assert EventType.EXECUTION_COMPLETED in event_types
