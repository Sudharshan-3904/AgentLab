"""Policy engine and security boundary interface and DTOs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from harness.core.config import AutonomyLevel
from harness.tools.interface import ToolRequest


class PolicyDecision(str, Enum):
    """Possible outcomes of a policy evaluation."""
    ALLOW = "ALLOW"
    DENY = "DENY"
    CONFIRM = "CONFIRM"


class PolicyEvaluationContext(BaseModel):
    """Contextual information provided to policy engine for evaluation."""
    execution_id: str
    autonomy_level: AutonomyLevel = AutonomyLevel.BALANCED
    tool_request: ToolRequest
    workspace_root: str
    is_network_requested: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PolicyEvaluationResult(BaseModel):
    """Decision made by the policy engine."""
    decision: PolicyDecision
    reason: str
    warnings: List[str] = Field(default_factory=list)
    requires_user_prompt: Optional[str] = None


class IPolicyEngine(ABC):
    """Abstract interface for evaluating security and autonomy policies."""

    @abstractmethod
    def evaluate(self, context: PolicyEvaluationContext) -> PolicyEvaluationResult:
        """Evaluate a tool invocation request against current autonomy policies."""
        pass
