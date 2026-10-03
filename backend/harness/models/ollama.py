"""Ollama model provider adapter for Local AI Harness."""

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


class OllamaProvider(IModelProvider):
    """Adapter for running local models via Ollama API."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "llama3.2:latest",
        timeout: float = 60.0,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self.session = session or requests.Session()

    def health(self) -> ModelHealth:
        """Check Ollama service status via /api/version."""
        start_t = time.perf_counter()
        try:
            resp = self.session.get(f"{self.base_url}/api/version", timeout=5.0)
            latency = (time.perf_counter() - start_t) * 1000.0
            if resp.status_code == 200:
                data = resp.json()
                version = data.get("version", "unknown")
                return ModelHealth(available=True, latency_ms=latency, message=f"Ollama {version}")
            return ModelHealth(
                available=False,
                latency_ms=latency,
                message=f"HTTP {resp.status_code}: {resp.text[:100]}",
            )
        except Exception as ex:
            latency = (time.perf_counter() - start_t) * 1000.0
            return ModelHealth(available=False, latency_ms=latency, message=str(ex))

    def metadata(self, model_name: Optional[str] = None) -> ModelMetadata:
        """Inspect model capabilities and metadata via /api/show."""
        target_model = model_name or self.default_model
        try:
            resp = self.session.post(
                f"{self.base_url}/api/show",
                json={"name": target_model},
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                details = data.get("details", {})
                return ModelMetadata(
                    name=target_model,
                    provider="ollama",
                    version=details.get("format", "unknown"),
                    quantization=details.get("quantization_level", "unknown"),
                    context_length=8192,
                    supports_streaming=True,
                    supports_tools=True,
                )
        except Exception:
            pass

        return ModelMetadata(
            name=target_model,
            provider="ollama",
            version="unknown",
            quantization="unknown",
            context_length=8192,
            supports_streaming=True,
            supports_tools=True,
        )

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Execute blocking inference request to Ollama /api/chat."""
        target_model = request.model or self.default_model
        call_id = f"ollama-{uuid.uuid4().hex[:8]}"
        start_iso = datetime.now(timezone.utc).isoformat()
        start_t = time.perf_counter()

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "top_p": request.top_p,
            },
        }
        if request.seed is not None:
            payload["options"]["seed"] = request.seed
        if request.stop:
            payload["options"]["stop"] = request.stop
        if request.tools:
            payload["tools"] = request.tools

        try:
            resp = self.session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            duration_ms = (time.perf_counter() - start_t) * 1000.0
            end_iso = datetime.now(timezone.utc).isoformat()

            raw_msg = data.get("message", {})
            chat_msg = ChatMessage(
                role=raw_msg.get("role", "assistant"),
                content=raw_msg.get("content", ""),
                tool_calls=raw_msg.get("tool_calls"),
            )

            prompt_tokens = data.get("prompt_eval_count")
            output_tokens = data.get("eval_count")

            record = ModelCallRecord(
                call_id=call_id,
                execution_id=request.execution_id,
                provider="ollama",
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
                message=chat_msg,
                record=record,
                raw_response=data,
            )

        except Exception as ex:
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            end_iso = datetime.now(timezone.utc).isoformat()
            record = ModelCallRecord(
                call_id=call_id,
                execution_id=request.execution_id,
                provider="ollama",
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
        """Stream response tokens from Ollama /api/chat."""
        target_model = request.model or self.default_model
        payload = {
            "model": target_model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "top_p": request.top_p,
            },
        }
        if request.seed is not None:
            payload["options"]["seed"] = request.seed

        resp = self.session.post(
            f"{self.base_url}/api/chat",
            json=payload,
            stream=True,
            timeout=self.timeout,
        )
        resp.raise_for_status()

        for line in resp.iter_lines():
            if line:
                chunk_data = json.loads(line.decode("utf-8"))
                content = chunk_data.get("message", {}).get("content", "")
                done = chunk_data.get("done", False)
                finish_reason = "stop" if done else None
                yield ModelChunk(delta=content, finish_reason=finish_reason)
