"""Integration test verifying Phase 2 Exit Criteria:
A user can run a local model through the harness with streaming, health checks,
metadata, and telemetry recording.
"""

from unittest.mock import MagicMock
import pytest
import requests

from harness.core.config import HarnessConfig
from harness.core.events import EventType
from harness.core.harness import Harness
from harness.models.factory import ModelProviderRegistry
from harness.models.interface import ChatMessage
from harness.models.lmstudio import LMStudioProvider
from harness.models.ollama import OllamaProvider


def test_model_provider_registry():
    ollama = ModelProviderRegistry.create("ollama", base_url="http://localhost:11434")
    assert isinstance(ollama, OllamaProvider)

    lmstudio = ModelProviderRegistry.create("lmstudio", base_url="http://localhost:1234/v1")
    assert isinstance(lmstudio, LMStudioProvider)

    with pytest.raises(ValueError):
        ModelProviderRegistry.create("non_existent_provider")


def test_phase2_exit_criteria_model_runtime_workflow():
    """
    Exit Criteria:
    A user can run a local model through the harness, with health checks,
    metadata, and complete model call recording in the event ledger.
    """
    # 1. Setup mock HTTP session simulating active Ollama runtime
    session = MagicMock(spec=requests.Session)

    # Mock health endpoint
    health_resp = MagicMock()
    health_resp.status_code = 200
    health_resp.json.return_value = {"version": "0.5.8"}

    # Mock metadata endpoint
    show_resp = MagicMock()
    show_resp.status_code = 200
    show_resp.json.return_value = {
        "details": {"format": "gguf", "quantization_level": "Q4_K_M"}
    }

    # Mock chat endpoint
    chat_resp = MagicMock()
    chat_resp.status_code = 200
    chat_resp.json.return_value = {
        "message": {
            "role": "assistant",
            "content": "Plan: 1. Setup models. 2. Run unit tests.",
        },
        "prompt_eval_count": 80,
        "eval_count": 35,
        "done": True,
    }

    session.get.return_value = health_resp
    def post_dispatcher(url, *args, **kwargs):
        if "show" in url:
            return show_resp
        return chat_resp

    session.post.side_effect = post_dispatcher

    provider = OllamaProvider(
        base_url="http://localhost:11434",
        default_model="llama3.2:latest",
        session=session,
    )

    # Verify provider health and metadata
    health = provider.health()
    assert health.available is True
    assert "0.5.8" in health.message

    meta = provider.metadata("llama3.2:latest")
    assert meta.name == "llama3.2:latest"
    assert meta.quantization == "Q4_K_M"

    # 2. Setup Harness with the model provider
    config = HarnessConfig()
    config.model.default_provider = "ollama"
    config.model.default_model = "llama3.2:latest"

    harness = Harness(config=config)
    harness.register_model_provider("ollama", provider)

    # 3. Create execution and run model call
    exec_mgr = harness.create_execution("Create model runtime pipeline")
    messages = [ChatMessage(role="user", content="Generate implementation steps")]
    response = exec_mgr.call_model(messages)

    assert "Plan: 1. Setup models" in response.message.content
    assert response.record.prompt_tokens == 80
    assert response.record.output_tokens == 35
    assert response.record.provider == "ollama"
    assert response.record.model == "llama3.2:latest"
    assert response.record.duration_ms >= 0

    # 4. Verify telemetry events persisted in SQLite ledger
    events = harness.get_events(exec_mgr.execution_id)
    event_types = [e.type for e in events]
    assert EventType.MODEL_REQUEST in event_types
    assert EventType.MODEL_RESPONSE in event_types

    model_resp_event = next(e for e in events if e.type == EventType.MODEL_RESPONSE)
    assert model_resp_event.correlation_id == response.call_id
    assert model_resp_event.payload["prompt_tokens"] == 80
    assert model_resp_event.payload["output_tokens"] == 35

    harness.close()
