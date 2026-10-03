"""Tests for ModelRouter and dynamic phase routing."""

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
from harness.models.router import ModelRouter
from harness.skills.suites import CodingSkillSuite, PlanningSkillSuite, TestingSkillSuite
from harness.tasks.task import Task


class DynamicModelProvider(IModelProvider):
    def __init__(self):
        self.invocations = []

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.invocations.append(request.model)
        record = ModelCallRecord(
            call_id="call-router-1",
            execution_id=request.execution_id,
            provider="mock",
            model=request.model,
            temperature=0.2,
            top_p=0.9,
            started_at="2026-10-03T20:00:00Z",
            completed_at="2026-10-03T20:00:01Z",
            prompt_tokens=50,
            output_tokens=25,
            duration_ms=100.0,
            success=True,
        )
        return ModelResponse(
            call_id="call-router-1",
            message=ChatMessage(role="assistant", content=f"Output from {request.model}"),
            record=record,
        )

    def stream(self, request: ModelRequest):
        return iter([])

    def health(self) -> ModelHealth:
        return ModelHealth(available=True)

    def metadata(self, model_name=None) -> ModelMetadata:
        return ModelMetadata(name=model_name or "default", provider="mock")


def test_model_router_rules():
    router = ModelRouter(
        default_model="llama3.2",
        rules={
            "planning": "deepseek-r1",
            "coding": "qwen2.5-coder",
            "testing": "llama3.2-fast",
        },
    )

    assert router.resolve_model("planning") == "deepseek-r1"
    assert router.resolve_model("coding") == "qwen2.5-coder"
    assert router.resolve_model("testing") == "llama3.2-fast"
    assert router.resolve_model("unknown_skill") == "llama3.2"


def test_model_router_disabled():
    router = ModelRouter(
        default_model="llama3.2",
        rules={"coding": "qwen2.5-coder"},
        enabled=False,
    )
    assert router.resolve_model("coding") == "llama3.2"


def test_execution_manager_automatic_model_routing():
    config = HarnessConfig()
    config.routing.enabled = True
    config.routing.rules = {
        "planning": "reasoning-model-r1",
        "coding": "coding-model-qwen",
    }
    config.model.default_model = "default-llama"

    provider = DynamicModelProvider()
    harness = Harness(config=config)
    harness.register_model_provider("ollama", provider)

    planning_skill = PlanningSkillSuite()
    coding_skill = CodingSkillSuite()
    harness.register_skill(planning_skill)
    harness.register_skill(coding_skill)

    exec_mgr = harness.create_execution(Task(objective="Route models dynamically"))
    assert exec_mgr.active_model_name == "default-llama"

    # 1. Switch to planning -> automatically routes to reasoning-model-r1
    exec_mgr.switch_skill("planning")
    assert exec_mgr.active_model_name == "reasoning-model-r1"

    # Call model in planning
    plan_resp = exec_mgr.call_model([ChatMessage(role="user", content="Plan")])
    assert "reasoning-model-r1" in plan_resp.message.content

    # 2. Switch to coding -> automatically routes to coding-model-qwen
    exec_mgr.switch_skill("coding")
    assert exec_mgr.active_model_name == "coding-model-qwen"

    # Call model in coding
    code_resp = exec_mgr.call_model([ChatMessage(role="user", content="Code")])
    assert "coding-model-qwen" in code_resp.message.content

    # 3. Verify MODEL_SELECTED events in ledger
    events = harness.get_events(exec_mgr.execution_id)
    model_selected_events = [e for e in events if e.type == EventType.MODEL_SELECTED]
    assert len(model_selected_events) >= 2
    assert model_selected_events[0].payload["selected_model"] == "reasoning-model-r1"
    assert model_selected_events[1].payload["selected_model"] == "coding-model-qwen"

    harness.close()
