"""LM Studio model provider adapter for Local AI Harness."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional
import requests

from harness.models.interface import (
    ChatMessage,
    IModelProvider,
    ModelCallRecord,
    ModelChunk,
    ModelHealth,
    ModelMetadata,
    ModelRequest,
    ModelResponse,
)


class LMStudioProvider(IModelProvider):
    """Adapter for running local models via LM Studio OpenAI-compatible API."""

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        default_model: str = "local-model",
        timeout: float = 60.0,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self.session = session or requests.Session()

    def health(self) -> ModelHealth:
        """Check LM Studio server connectivity via /models."""
        start_t = time.perf_counter()
        try:
            resp = self.session.get(f"{self.base_url}/models", timeout=5.0)
            latency = (time.perf_counter() - start_t) * 1000.0
            if resp.status_code == 200:
                data = resp.json()
                model_count = len(data.get("data", []))
                return ModelHealth(
                    available=True,
                    latency_ms=latency,
                    message=f"LM Studio active with {model_count} model(s)",
                )
            return ModelHealth(
                available=False,
                latency_ms=latency,
                message=f"HTTP {resp.status_code}: {resp.text[:100]}",
            )
        except Exception as ex:
            latency = (time.perf_counter() - start_t) * 1000.0
            return ModelHealth(available=False, latency_ms=latency, message=str(ex))

    def metadata(self, model_name: Optional[str] = None) -> ModelMetadata:
        """Query available model metadata from /models."""
        target_model = model_name or self.default_model
        try:
            resp = self.session.get(f"{self.base_url}/models", timeout=5.0)
            if resp.status_code == 200:
                models = resp.json().get("data", [])
                for m in models:
                    if m.get("id") == target_model:
                        return ModelMetadata(
                            name=target_model,
                            provider="lmstudio",
                            version=m.get("object", "model"),
                            quantization="unknown",
                            context_length=m.get("max_model_len", 8192),
                            supports_streaming=True,
                            supports_tools=True,
                        )
        except Exception:
            pass

        return ModelMetadata(
            name=target_model,
            provider="lmstudio",
            version="unknown",
            quantization="unknown",
            context_length=8192,
            supports_streaming=True,
            supports_tools=True,
        )

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Execute blocking inference request to /chat/completions."""
        target_model = request.model or self.default_model
        call_id = f"lmstudio-{uuid.uuid4().hex[:8]}"
        start_iso = datetime.now(timezone.utc).isoformat()
        start_t = time.perf_counter()

        formatted_messages = []
        for m in request.messages:
            msg_dict: Dict[str, Any] = {"role": m.role, "content": m.content}
            if m.tool_calls:
                msg_dict["tool_calls"] = m.tool_calls
            formatted_messages.append(msg_dict)

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": formatted_messages,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": False,
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        if request.stop:
            payload["stop"] = request.stop
        if request.tools:
            payload["tools"] = request.tools

        try:
            resp = self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            duration_ms = (time.perf_counter() - start_t) * 1000.0
            end_iso = datetime.now(timezone.utc).isoformat()

            choice = data.get("choices", [{}])[0]
            choice_msg = choice.get("message", {})
            content = choice_msg.get("content", "")
            tool_calls = choice_msg.get("tool_calls")

            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens")
            output_tokens = usage.get("completion_tokens")

            record = ModelCallRecord(
                call_id=call_id,
                execution_id=request.execution_id,
                provider="lmstudio",
                model=target_model,
                temperature=request.temperature,
                top_p=request.top_p,
                seed=request.seed,
                started_at=start_iso,
                completed_at=end_iso,
                prompt_tokens=prompt_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                success=True,
            )

            return ModelResponse(
                call_id=call_id,
                message=ChatMessage(
                    role=choice_msg.get("role", "assistant"),
                    content=content,
                    tool_calls=tool_calls,
                ),
                record=record,
                raw_response=data,
            )

        except Exception as ex:
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            end_iso = datetime.now(timezone.utc).isoformat()
            record = ModelCallRecord(
                call_id=call_id,
                execution_id=request.execution_id,
                provider="lmstudio",
                model=target_model,
                temperature=request.temperature,
                top_p=request.top_p,
                seed=request.seed,
                started_at=start_iso,
                completed_at=end_iso,
                duration_ms=duration_ms,
                success=False,
                error=str(ex),
            )
            return ModelResponse(
                call_id=call_id,
                message=ChatMessage(role="assistant", content=f"Error: {ex}"),
                record=record,
            )

    def stream(self, request: ModelRequest) -> Iterator[ModelChunk]:
        """Stream response tokens from LM Studio /chat/completions using SSE."""
        target_model = request.model or self.default_model
        payload = {
            "model": target_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": True,
        }
        if request.seed is not None:
            payload["seed"] = request.seed

        resp = self.session.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            stream=True,
            timeout=self.timeout,
        )
        resp.raise_for_status()

        for line in resp.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8").strip()
            if line_str.startswith("data: "):
                raw_json = line_str[6:].strip()
                if raw_json == "[DONE]":
                    break
                try:
                    chunk_data = json.loads(raw_json)
                    choice = chunk_data.get("choices", [{}])[0]
                    delta = choice.get("delta", {}).get("content", "")
                    finish_reason = choice.get("finish_reason")
                    if delta or finish_reason:
                        yield ModelChunk(delta=delta, finish_reason=finish_reason)
                except Exception:
                    continue
