"""Unit tests for EvaluationEngine and metric calculations."""

from datetime import datetime, timezone
import pytest

from harness.core.events import Event, EventType
from harness.evaluation.engine import EvaluationEngine
from harness.models.interface import ModelCallRecord
from harness.monitoring.interface import CpuMetrics, GpuMetrics, RamMetrics, ResourceSample
from harness.tools.interface import ToolResponse, ToolStatus


def test_evaluation_engine_metrics_calculation():
    engine = EvaluationEngine()
    exec_id = "exec-test-001"

    t1 = "2026-10-03T20:00:00+00:00"
    t2 = "2026-10-03T20:00:05+00:00"

    events = [
        Event(execution_id=exec_id, timestamp=t1, type=EventType.TASK_RECEIVED, source="intake", payload={"task_id": "task-1", "objective": "Write quicksort"}),
        Event(execution_id=exec_id, timestamp=t1, type=EventType.SKILL_LOADED, source="skill", payload={"skill": "Planning"}),
        Event(execution_id=exec_id, timestamp=t1, type=EventType.SKILL_LOADED, source="skill", payload={"skill": "Coding"}),
        Event(execution_id=exec_id, timestamp=t1, type=EventType.MODEL_SELECTED, source="router", payload={"model": "llama3.2"}),
        Event(execution_id=exec_id, timestamp=t1, type=EventType.TOOL_REQUEST, source="tool", payload={"tool": "write_file"}),
        Event(execution_id=exec_id, timestamp=t1, type=EventType.RECOVERY_STARTED, source="recovery", payload={"attempt": 1}),
        Event(execution_id=exec_id, timestamp=t2, type=EventType.RECOVERY_COMPLETED, source="recovery", payload={"attempt": 1}),
        Event(execution_id=exec_id, timestamp=t2, type=EventType.EXECUTION_COMPLETED, source="manager", payload={"status": "COMPLETED"}),
    ]

    model_calls = [
        ModelCallRecord(
            call_id="call-1",
            execution_id=exec_id,
            provider="ollama",
            model="llama3.2",
            temperature=0.2,
            top_p=0.9,
            started_at=t1,
            completed_at=t2,
            prompt_tokens=100,
            output_tokens=50,
            duration_ms=2000.0,
            success=True,
        )
    ]

    tool_responses = [
        ToolResponse(
            tool_request_id="tr-1",
            execution_id=exec_id,
            tool_name="write_file",
            status=ToolStatus.SUCCESS,
            output="Written",
            duration_ms=150.0,
        )
    ]

    resource_samples = [
        ResourceSample(
            sample_id="s1",
            execution_id=exec_id,
            timestamp=t1,
            cpu=CpuMetrics(utilization_pct=25.0, user_time_s=1.0, system_time_s=0.5),
            ram=RamMetrics(total_mb=16000.0, used_mb=8000.0, percent=50.0),
            gpu=GpuMetrics(available=True, utilization_pct=30.0, vram_used_mb=4000.0, power_watts=75.0),
        ),
        ResourceSample(
            sample_id="s2",
            execution_id=exec_id,
            timestamp=t2,
            cpu=CpuMetrics(utilization_pct=45.0, user_time_s=2.0, system_time_s=1.0),
            ram=RamMetrics(total_mb=16000.0, used_mb=8200.0, percent=51.25),
            gpu=GpuMetrics(available=True, utilization_pct=50.0, vram_used_mb=4200.0, power_watts=95.0),
        ),
    ]

    summary = engine.evaluate(
        execution_id=exec_id,
        events=events,
        resource_samples=resource_samples,
        model_calls=model_calls,
        tool_responses=tool_responses,
    )

    assert summary.execution_id == exec_id
    assert summary.task_objective == "Write quicksort"
    assert summary.status == "COMPLETED"

    # Raw metrics checks
    raw = summary.raw_metrics
    assert raw.total_duration_s == 5.0
    assert raw.skill_transitions_count == 2
    assert raw.model_transitions_count == 1
    assert raw.recovery_attempts_count == 1
    assert raw.tool_calls_count == 1
    assert raw.prompt_tokens == 100
    assert raw.output_tokens == 50
    assert raw.total_tokens == 150
    assert raw.peak_cpu_percent == 45.0
    assert raw.avg_cpu_percent == 35.0
    assert raw.peak_ram_mb == 8200.0
    assert raw.peak_vram_mb == 4200.0
    assert raw.avg_gpu_percent == 40.0
    assert raw.avg_power_watts == 85.0

    # Derived metrics checks
    derived = summary.derived_metrics
    assert derived.task_success is True
    assert derived.tool_success_rate == 1.0
    assert derived.model_success_rate == 1.0
    assert derived.recovery_success_rate == 1.0
    assert derived.tokens_per_second == 30.0  # 150 tokens / 5 seconds
    assert derived.execution_efficiency_score == 100.0  # 60 + 20 + 20
