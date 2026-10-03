"""Evaluation Engine calculating deterministic raw and derived metrics."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

from harness.core.events import Event, EventType
from harness.evaluation.interface import (
    DerivedMetrics,
    EvaluationSummary,
    IEvaluationEngine,
    RawMetrics,
)
from harness.models.interface import ModelCallRecord
from harness.monitoring.interface import ResourceSample
from harness.tools.interface import ToolResponse, ToolStatus

logger = logging.getLogger("agentlab.evaluation")


class EvaluationEngine(IEvaluationEngine):
    """Computes deterministic execution telemetry and performance summaries."""

    def evaluate(
        self,
        execution_id: str,
        events: List[Event],
        resource_samples: Optional[List[ResourceSample]] = None,
        model_calls: Optional[List[ModelCallRecord]] = None,
        tool_responses: Optional[List[ToolResponse]] = None,
    ) -> EvaluationSummary:
        """Derive structured metrics from events, telemetry, model calls, and tools."""
        raw = RawMetrics()
        derived = DerivedMetrics()

        task_id = None
        task_objective = ""
        status = "UNKNOWN"

        # 1. Process ledger events
        timestamps: List[datetime] = []
        recovered_count = 0
        recovery_completed_count = 0

        for ev in events:
            # Parse timestamp for duration
            try:
                # Handle ISO timestamps with or without Z
                ts_str = ev.timestamp.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts_str)
                timestamps.append(dt)
            except Exception:
                pass

            if ev.type == EventType.TASK_RECEIVED:
                task_id = ev.payload.get("task_id")
                task_objective = ev.payload.get("objective", "")

            elif ev.type == EventType.SKILL_LOADED:
                raw.skill_transitions_count += 1

            elif ev.type == EventType.MODEL_SELECTED:
                raw.model_transitions_count += 1

            elif ev.type == EventType.TOOL_REQUEST:
                raw.tool_calls_count += 1

            elif ev.type == EventType.RECOVERY_STARTED:
                raw.recovery_attempts_count += 1

            elif ev.type == EventType.RECOVERY_COMPLETED:
                recovery_completed_count += 1

            elif ev.type == EventType.EXECUTION_COMPLETED:
                status = ev.payload.get("status", "COMPLETED")
                if status == "COMPLETED":
                    derived.task_success = True

            elif ev.type == EventType.ERROR:
                if status == "UNKNOWN":
                    status = "FAILED"

        # Calculate execution duration
        if timestamps:
            duration = (max(timestamps) - min(timestamps)).total_seconds()
            raw.total_duration_s = max(duration, 0.001)

        # 2. Process Model Calls & Tokens
        calls = list(model_calls or [])
        raw.model_calls_count = len(calls)
        total_p_tokens = 0
        total_o_tokens = 0
        total_m_duration = 0.0
        success_models = 0

        for call in calls:
            total_p_tokens += call.prompt_tokens or 0
            total_o_tokens += call.output_tokens or 0
            total_m_duration += (call.duration_ms / 1000.0) if call.duration_ms else 0.0
            if call.success:
                success_models += 1

        raw.prompt_tokens = total_p_tokens if total_p_tokens > 0 else None
        raw.output_tokens = total_o_tokens if total_o_tokens > 0 else None
        if raw.prompt_tokens is not None or raw.output_tokens is not None:
            raw.total_tokens = (raw.prompt_tokens or 0) + (raw.output_tokens or 0)
        raw.model_duration_s = total_m_duration

        if raw.model_calls_count > 0:
            derived.model_success_rate = success_models / raw.model_calls_count

        # 3. Process Tool Responses
        tools = list(tool_responses or [])
        if not raw.tool_calls_count and tools:
            raw.tool_calls_count = len(tools)

        total_t_duration = 0.0
        success_tools = 0
        for tool in tools:
            total_t_duration += (tool.duration_ms / 1000.0) if tool.duration_ms else 0.0
            if tool.status == ToolStatus.SUCCESS:
                success_tools += 1

        raw.tool_duration_s = total_t_duration
        if tools:
            derived.tool_success_rate = success_tools / len(tools)

        # 4. Process Resource Telemetry
        samples = list(resource_samples or [])
        # Also check if any samples were logged in events
        for ev in events:
            if ev.type == EventType.RESOURCE_SAMPLE and isinstance(ev.payload, dict):
                try:
                    samples.append(ResourceSample.model_validate(ev.payload))
                except Exception:
                    pass

        if samples:
            cpus = [s.cpu.utilization_pct for s in samples if s.cpu and s.cpu.utilization_pct is not None]
            if cpus:
                raw.peak_cpu_percent = max(cpus)
                raw.avg_cpu_percent = sum(cpus) / len(cpus)

            rams = [s.ram.used_mb for s in samples if s.ram and s.ram.used_mb is not None]
            if rams:
                raw.peak_ram_mb = max(rams)
                raw.avg_ram_mb = sum(rams) / len(rams)

            vrams = [s.gpu.vram_used_mb for s in samples if s.gpu and s.gpu.vram_used_mb is not None]
            if vrams:
                raw.peak_vram_mb = max(vrams)

            gpus = [s.gpu.utilization_pct for s in samples if s.gpu and s.gpu.utilization_pct is not None]
            if gpus:
                raw.avg_gpu_percent = sum(gpus) / len(gpus)

            powers = [s.gpu.power_watts for s in samples if s.gpu and s.gpu.power_watts is not None]
            if powers:
                raw.avg_power_watts = sum(powers) / len(powers)

        # 5. Calculate Derived Metrics
        if raw.total_tokens and raw.total_duration_s > 0:
            derived.tokens_per_second = raw.total_tokens / raw.total_duration_s

        if raw.recovery_attempts_count > 0:
            derived.recovery_success_rate = (
                min(recovery_completed_count / raw.recovery_attempts_count, 1.0)
            )

        # Efficiency score: 0 to 100
        score = 0.0
        if derived.task_success:
            score += 60.0
        score += derived.tool_success_rate * 20.0
        score += derived.model_success_rate * 20.0
        derived.execution_efficiency_score = round(score, 2)

        return EvaluationSummary(
            execution_id=execution_id,
            task_id=task_id,
            task_objective=task_objective,
            status=status,
            raw_metrics=raw,
            derived_metrics=derived,
            metadata={
                "events_count": len(events),
                "samples_count": len(samples),
                "model_calls_count": len(calls),
            },
        )
