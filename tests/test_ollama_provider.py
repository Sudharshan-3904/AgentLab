"""Tests for Ollama model provider adapter."""

import json
from unittest.mock import MagicMock
import pytest
import requests

from harness.models.interface import ChatMessage, ModelRequest
from harness.models.ollama import OllamaProvider


def test_ollama_health_success():
    session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"version": "0.5.7"}
    session.get.return_value = mock_resp

    provider = OllamaProvider(session=session)
    health = provider.health()

    assert health.available is True
    assert "0.5.7" in health.message
    assert health.latency_ms is not None
    session.get.assert_called_with("http://localhost:11434/api/version", timeout=5.0)


def test_ollama_health_failure():
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = requests.ConnectionError("Connection refused")

    provider = OllamaProvider(session=session)
    health = provider.health()

    assert health.available is False
    assert "Connection refused" in health.message


def test_ollama_metadata():
    session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "details": {
            "format": "gguf",
            "quantization_level": "Q4_K_M",
        }
    }
    session.post.return_value = mock_resp

    provider = OllamaProvider(session=session)
    meta = provider.metadata("llama3.2")

    assert meta.name == "llama3.2"
    assert meta.provider == "ollama"
    assert meta.quantization == "Q4_K_M"
    assert meta.version == "gguf"


def test_ollama_generate_success():
    session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {"role": "assistant", "content": "def add(a, b): return a + b"},
        "prompt_eval_count": 45,
        "eval_count": 22,
        "done": True,
    }
    session.post.return_value = mock_resp

    provider = OllamaProvider(session=session)
    req = ModelRequest(
        execution_id="exec-ollama-1",
        messages=[ChatMessage(role="user", content="Write an add function")],
        model="llama3.2",
        temperature=0.3,
        top_p=0.85,
        seed=123,
    )
    res = provider.generate(req)

    assert res.message.content == "def add(a, b): return a + b"
    assert res.record.prompt_tokens == 45
    assert res.record.output_tokens == 22
    assert res.record.success is True
    assert res.record.seed == 123
    assert res.record.duration_ms >= 0


def test_ollama_generate_error():
    session = MagicMock(spec=requests.Session)
    session.post.side_effect = requests.Timeout("Model generation timed out")

    provider = OllamaProvider(session=session)
    req = ModelRequest(
        execution_id="exec-ollama-err",
        messages=[ChatMessage(role="user", content="Test timeout")],
    )
    res = provider.generate(req)

    assert res.record.success is False
    assert "timed out" in res.record.error
    assert "Error:" in res.message.content


def test_ollama_streaming():
    session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    chunk1 = json.dumps({"message": {"content": "Hello"}, "done": False}).encode("utf-8")
    chunk2 = json.dumps({"message": {"content": " world"}, "done": True}).encode("utf-8")
    mock_resp.iter_lines.return_value = [chunk1, chunk2]
    session.post.return_value = mock_resp

    provider = OllamaProvider(session=session)
    req = ModelRequest(
        execution_id="exec-ollama-stream",
        messages=[ChatMessage(role="user", content="Stream test")],
    )
    chunks = list(provider.stream(req))

    assert len(chunks) == 2
    assert chunks[0].delta == "Hello"
    assert chunks[0].finish_reason is None
    assert chunks[1].delta == " world"
    assert chunks[1].finish_reason == "stop"
