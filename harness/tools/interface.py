"""Tool interface and contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field


class ToolStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    DENIED = "denied"
    CANCELLED = "cancelled"


class ToolParameter(BaseModel):
    """Definition of a single parameter for a tool."""
    name: str
    type: str
    description: str
    required: bool = True
    default: Optional[Any] = None


class ToolDefinition(BaseModel):
    """Specification of a tool exposed to models and agents."""
    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    danger_level: str = Field(default="normal", description="Safety tier: read_only, normal, high_risk")


class ToolRequest(BaseModel):
    """Invocation request for a tool."""
    tool_request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    execution_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    source_skill: Optional[str] = None


class ToolResponse(BaseModel):
    """Result of a tool execution."""
    tool_request_id: str
    execution_id: str
    tool_name: str
    status: ToolStatus
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0


class ITool(ABC):
    """Abstract interface for all executable tools in the harness."""

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return the specification definition of this tool."""
        pass

    @property
    def name(self) -> str:
        return self.definition.name

    @abstractmethod
    def execute(self, request: ToolRequest) -> ToolResponse:
        """Execute the tool request and return a response."""
        pass
