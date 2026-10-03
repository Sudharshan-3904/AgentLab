"""Evaluation interface and metric contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from harness.core.events import Event
from harness.monitoring.interface import ResourceSample
from harness.models.interface import ModelCallRecord
from harness.tools.interface import ToolResponse


class RawMetrics(BaseModel):
    """Raw measured metrics extracted directly from telemetry and ledger."""
    total_duration_s: float = 0.0
    model_duration_s: float = 0.0
    tool_duration_s: float = 0.0
    model_calls_count: int = 0
    tool_calls_count: int = 0
    prompt_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    skill_transitions_count: int = 0
    model_transitions_count: int = 0
    recovery_attempts_count: int = 0
    peak_cpu_percent: float = 0.0
    avg_cpu_percent: float = 0.0
    peak_ram_mb: float = 0.0
    avg_ram_mb: float = 0.0
    peak_vram_mb: Optional[float] = None
    avg_gpu_percent: Optional[float] = None
    avg_power_watts: Optional[float] = None


class DerivedMetrics(BaseModel):
    """Calculated metrics derived from raw metrics and execution events."""
    task_success: bool = False
    tokens_per_second: Optional[float] = None
    tool_success_rate: float = 1.0
    model_success_rate: float = 1.0
    recovery_success_rate: Optional[float] = None
    execution_efficiency_score: float = 0.0


class EvaluationSummary(BaseModel):
    """Complete evaluation report for an execution."""
    execution_id: str
    task_id: Optional[str] = None
    task_objective: str = ""
    status: str = "COMPLETED"
    raw_metrics: RawMetrics = Field(default_factory=RawMetrics)
    derived_metrics: DerivedMetrics = Field(default_factory=DerivedMetrics)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IEvaluationEngine(ABC):
    """Abstract interface for calculating deterministic evaluation metrics."""

    @abstractmethod
    def evaluate(
        self,
        execution_id: str,
        events: List[Event],
        resource_samples: Optional[List[ResourceSample]] = None,
        model_calls: Optional[List[ModelCallRecord]] = None,
        tool_responses: Optional[List[ToolResponse]] = None,
    ) -> EvaluationSummary:
        """Derive structured metrics from raw telemetry and execution events."""
        pass
