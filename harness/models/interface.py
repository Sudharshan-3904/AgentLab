"""Model provider interface and DTO contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional
from pydantic import BaseModel, Field


class ModelMetadata(BaseModel):
    """Metadata describing a model and its capabilities."""
    name: str
    provider: str
    version: Optional[str] = "unknown"
    quantization: Optional[str] = "unknown"
    context_length: Optional[int] = 8192
    supports_streaming: bool = True
    supports_tools: bool = True


class ModelHealth(BaseModel):
    """Health status of a model provider backend."""
    available: bool
    latency_ms: Optional[float] = None
    message: Optional[str] = None


class ChatMessage(BaseModel):
    """Message in a model conversation."""
    role: str = Field(..., description="Role: system, user, assistant, tool")
    content: str = Field(default="", description="Text content")
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class ModelRequest(BaseModel):
    """Standardized model inference request."""
    execution_id: str
    messages: List[ChatMessage]
    model: Optional[str] = None
    temperature: float = 0.2
    top_p: float = 0.9
    seed: Optional[int] = 42
    tools: Optional[List[Dict[str, Any]]] = None
    stop: Optional[List[str]] = None


class ModelCallRecord(BaseModel):
    """Record of a model invocation for telemetry and audit."""
    call_id: str
    execution_id: str
    provider: str
    model: str
    temperature: float
    top_p: float
    seed: Optional[int] = None
    started_at: str
    completed_at: str
    prompt_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    duration_ms: float
    success: bool = True
    error: Optional[str] = None


class ModelResponse(BaseModel):
    """Standardized model inference response."""
    call_id: str
    message: ChatMessage
    record: ModelCallRecord
    raw_response: Optional[Dict[str, Any]] = None


class ModelChunk(BaseModel):
    """A streaming chunk from a model provider."""
    delta: str
    finish_reason: Optional[str] = None


class IModelProvider(ABC):
    """Abstract interface for local and remote model providers."""

    @abstractmethod
    def generate(self, request: ModelRequest) -> ModelResponse:
        """Execute a blocking inference request."""
        pass

    @abstractmethod
    def stream(self, request: ModelRequest) -> Iterator[ModelChunk]:
        """Stream response chunks from the model."""
        pass

    @abstractmethod
    def health(self) -> ModelHealth:
        """Check provider connectivity and readiness."""
        pass

    @abstractmethod
    def metadata(self, model_name: Optional[str] = None) -> ModelMetadata:
        """Retrieve model metadata."""
        pass
