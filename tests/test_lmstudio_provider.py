"""Tests for LM Studio model provider adapter."""

import json
from unittest.mock import MagicMock
import pytest
import requests

from harness.models.interface import ChatMessage, ModelRequest
from harness.models.lmstudio import LMStudioProvider


def test_lmstudio_health_success():
    session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [{"id": "qwen2.5-coder-7b", "object": "model"}]
    }
    session.get.return_value = mock_resp

    provider = LMStudioProvider(session=session)
    health = provider.health()

    assert health.available is True
    assert "1 model(s)" in health.message
    session.get.assert_called_with("http://localhost:1234/v1/models", timeout=5.0)


def test_lmstudio_health_failure():
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = requests.ConnectionError("LM Studio not running")

    provider = LMStudioProvider(session=session)
    health = provider.health()

    assert health.available is False
    assert "not running" in health.message


def test_lmstudio_metadata():
    session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"id": "qwen2.5-coder-7b", "object": "model", "max_model_len": 16384}
        ]
    }
    session.get.return_value = mock_resp

    provider = LMStudioProvider(session=session, default_model="qwen2.5-coder-7b")
    meta = provider.metadata("qwen2.5-coder-7b")

    assert meta.name == "qwen2.5-coder-7b"
    assert meta.provider == "lmstudio"
    assert meta.context_length == 16384


def test_lmstudio_generate_success():
    session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "class Calculator:\n    pass",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 55,
            "completion_tokens": 15,
            "total_tokens": 70,
        },
    }
    session.post.return_value = mock_resp

    provider = LMStudioProvider(session=session)
    req = ModelRequest(
        execution_id="exec-lm-1",
        messages=[ChatMessage(role="user", content="Scaffold Calculator class")],
        model="qwen2.5-coder-7b",
        temperature=0.2,
        top_p=0.9,
    )
    res = provider.generate(req)

    assert "Calculator" in res.message.content
    assert res.record.prompt_tokens == 55
    assert res.record.output_tokens == 15
    assert res.record.success is True
    assert res.record.provider == "lmstudio"
    assert res.record.model == "qwen2.5-coder-7b"


def test_lmstudio_generate_error():
    session = MagicMock(spec=requests.Session)
    session.post.side_effect = requests.HTTPError("500 Server Error")

    provider = LMStudioProvider(session=session)
    req = ModelRequest(
        execution_id="exec-lm-err",
        messages=[ChatMessage(role="user", content="Trigger error")],
    )
    res = provider.generate(req)

    assert res.record.success is False
    assert "500 Server Error" in res.record.error
    assert "Error:" in res.message.content


def test_lmstudio_streaming_sse():
    session = MagicMock(spec=requests.Session)
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    chunk1 = b'data: {"choices": [{"delta": {"content": "def "}}]}'
    chunk2 = b'data: {"choices": [{"delta": {"content": "main(): pass"}, "finish_reason": "stop"}]}'
    chunk3 = b'data: [DONE]'
    mock_resp.iter_lines.return_value = [chunk1, chunk2, chunk3]
    session.post.return_value = mock_resp

    provider = LMStudioProvider(session=session)
    req = ModelRequest(
        execution_id="exec-lm-stream",
        messages=[ChatMessage(role="user", content="Stream function")],
    )
    chunks = list(provider.stream(req))

    assert len(chunks) == 2
    assert chunks[0].delta == "def "
    assert chunks[0].finish_reason is None
    assert chunks[1].delta == "main(): pass"
    assert chunks[1].finish_reason == "stop"
