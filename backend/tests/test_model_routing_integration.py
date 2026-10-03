"""Integration test verifying Phase 8 Exit Criteria:
A single execution can switch models without creating a new logical execution.
"""

from pathlib import Path
import pytest

from harness.core.config import HarnessConfig
from harness.core.events import EventType
from harness.core.harness import Harness
from harness.models.interface import (
    ChatMessage,
    IModelProvider,
    ModelCallRecord,
    ModelHealth,
    ModelMetadata,
    ModelRequest,
    ModelResponse,
)
from harness.skills.suites import (
    CodingSkillSuite,
    PlanningSkillSuite,
    TestingSkillSuite,
)
from harness.tasks.task import Task


class MultiModelDispatcher(IModelProvider):
    """Mock provider recording which model was invoked for each call."""

    def __init__(self):
        self.call_log = []

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.call_log.append({
            "execution_id": request.execution_id,
            "model": request.model,
            "prompt": request.messages[-1].content,
        })
        record = ModelCallRecord(
            call_id=f"call-{len(self.call_log)}",
            execution_id=request.execution_id,
            provider="mock-provider",
            model=request.model,
            temperature=request.temperature,
            top_p=request.top_p,
            started_at="2026-10-03T20:00:00Z",
            completed_at="2026-10-03T20:00:01Z",
            prompt_tokens=40,
            output_tokens=20,
            duration_ms=80.0,
            success=True,
        )
        return ModelResponse(
            call_id=f"call-{len(self.call_log)}",
            message=ChatMessage(role="assistant", content=f"Response from {request.model}"),
            record=record,
        )

    def stream(self, request: ModelRequest):
        return iter([])

    def health(self) -> ModelHealth:
        return ModelHealth(available=True)

    def metadata(self, model_name=None) -> ModelMetadata:
        return ModelMetadata(name=model_name or "default", provider="mock")


def test_phase8_exit_criteria_single_execution_model_routing(tmp_path: Path):
    """
    Exit Criteria:
    A single execution can switch models without creating a new logical execution.
    """
    db_file = tmp_path / "model_routing_ledger.db"

    # Configure multi-model routing table
    config = HarnessConfig()
    config.routing.enabled = True
    config.routing.rules = {
        "planning": "reasoning-model-r1",
        "coding": "coding-model-qwen",
        "testing": "fast-eval-model",
    }
    config.model.default_provider = "mock"
    config.model.default_model = "base-model"

    dispatcher = MultiModelDispatcher()
    harness = Harness(config=config, db_path=str(db_file))
    harness.register_model_provider("mock", dispatcher)

    # Register skills
    harness.register_skill(PlanningSkillSuite())
    harness.register_skill(CodingSkillSuite())
    harness.register_skill(TestingSkillSuite())

    # Create exactly ONE logical execution
    task = Task(objective="Design, implement, and test an LRU cache")
    exec_mgr = harness.create_execution(task)
    original_execution_id = exec_mgr.execution_id

    # 1. Phase 1: Planning with reasoning model
    exec_mgr.switch_skill("planning")
    assert exec_mgr.execution_id == original_execution_id
    assert exec_mgr.active_model_name == "reasoning-model-r1"

    res_plan = exec_mgr.call_model([ChatMessage(role="user", content="Plan LRU cache")])
    assert res_plan.record.model == "reasoning-model-r1"
    assert "reasoning-model-r1" in res_plan.message.content

    # 2. Phase 2: Coding with coding model
    exec_mgr.switch_skill("coding")
    assert exec_mgr.execution_id == original_execution_id
    assert exec_mgr.active_model_name == "coding-model-qwen"

    res_code = exec_mgr.call_model([ChatMessage(role="user", content="Implement LRU cache")])
    assert res_code.record.model == "coding-model-qwen"
    assert "coding-model-qwen" in res_code.message.content

    # 3. Phase 3: Testing with fast eval model
    exec_mgr.switch_skill("testing")
    assert exec_mgr.execution_id == original_execution_id
    assert exec_mgr.active_model_name == "fast-eval-model"

    res_test = exec_mgr.call_model([ChatMessage(role="user", content="Verify LRU cache")])
    assert res_test.record.model == "fast-eval-model"
    assert "fast-eval-model" in res_test.message.content

    # 4. Verify that dispatcher received all 3 calls under the SAME execution_id
    assert len(dispatcher.call_log) == 3
    for entry in dispatcher.call_log:
        assert entry["execution_id"] == original_execution_id

    assert dispatcher.call_log[0]["model"] == "reasoning-model-r1"
    assert dispatcher.call_log[1]["model"] == "coding-model-qwen"
    assert dispatcher.call_log[2]["model"] == "fast-eval-model"

    # 5. Verify MODEL_SELECTED telemetry events in SQLite ledger
    events = harness.get_events(original_execution_id)
    model_selected_events = [e for e in events if e.type == EventType.MODEL_SELECTED]
    assert len(model_selected_events) >= 3

    selected_models = [e.payload["selected_model"] for e in model_selected_events]
    assert "reasoning-model-r1" in selected_models
    assert "coding-model-qwen" in selected_models
    assert "fast-eval-model" in selected_models

    harness.close()
