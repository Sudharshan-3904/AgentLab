"""Benchmark suite and automated benchmark runner for Local AI Harness."""

from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from harness.core.harness import Harness
from harness.core.state import ExecutionState
from harness.evaluation.engine import EvaluationEngine
from harness.evaluation.interface import EvaluationSummary
from harness.tasks.task import Task

logger = logging.getLogger("agentlab.benchmark")


class BenchmarkTask(BaseModel):
    """Specification for a reproducible coding benchmark task."""

    #TODO - EXP-008: Add task category and complexity metadata for the full coding-agent scaling suite.
    task_id: str
    name: str
    objective: str
    constraints: List[str] = Field(default_factory=list)
    initial_files: Dict[str, str] = Field(default_factory=dict, description="Relative path -> initial file content")
    verification_code: Optional[str] = None


class BenchmarkReport(BaseModel):
    """Aggregated benchmark report over multiple coding tasks."""

    suite_name: str
    total_tasks: int = 0
    passed_tasks: int = 0
    failed_tasks: int = 0
    success_rate: float = 0.0
    total_tokens: int = 0
    total_duration_s: float = 0.0
    avg_duration_s: float = 0.0
    avg_cpu_percent: float = 0.0
    avg_ram_mb: float = 0.0
    peak_ram_mb: float = 0.0
    task_summaries: List[EvaluationSummary] = Field(default_factory=list)


class StandardBenchmarkSuite:
    """Canonical fixed set of coding benchmark tasks."""

    @classmethod
    def get_mvp_tasks(cls) -> List[BenchmarkTask]:
        return [
            BenchmarkTask(
                task_id="task-001-fib",
                name="Fibonacci Generator",
                objective="Implement fibonacci(n) returning the n-th Fibonacci number in fib.py",
                constraints=["Pure Python", "n >= 0"],
                initial_files={"test_fib.py": "from fib import fibonacci\ndef test_fib():\n    assert fibonacci(7) == 13\n"},
            ),
            BenchmarkTask(
                task_id="task-002-rot13",
                name="ROT13 Cipher",
                objective="Implement rot13(text) cipher algorithm in cipher.py",
                constraints=["Preserve case", "Ignore non-alphabetic"],
                initial_files={"test_cipher.py": "from cipher import rot13\ndef test_rot13():\n    assert rot13('Hello') == 'Uryyb'\n"},
            ),
            BenchmarkTask(
                task_id="task-003-stats",
                name="Statistical Summary",
                objective="Implement mean and median in stats.py",
                constraints=["Return float for mean", "Handle even/odd lengths"],
                initial_files={"test_stats.py": "from stats import mean, median\ndef test_stats():\n    assert mean([1, 2, 3]) == 2.0\n    assert median([1, 2, 3]) == 2\n"},
            ),
        ]


class BenchmarkRunner:
    """Executes benchmark suites and computes aggregate benchmark performance reports."""

    #TODO - EXP-000: Add manifest-driven seeds and repetitions, environment/model capture, and reproducibility-package export.
    def __init__(
        self,
        harness: Harness,
        suite: Optional[List[BenchmarkTask]] = None,
        suite_name: str = "mvp-coding-benchmark-v1",
    ):
        self.harness = harness
        self.suite = suite or StandardBenchmarkSuite.get_mvp_tasks()
        self.suite_name = suite_name
        self.evaluation_engine = EvaluationEngine()

    def run_task(
        self,
        task: BenchmarkTask,
        executor_fn: Optional[Callable[[Any, BenchmarkTask], bool]] = None,
    ) -> EvaluationSummary:
        """Execute a single benchmark task in its own isolated execution context."""
        #TODO - EXP-000: Add a direct-provider control path and collect comparable call, token, latency, and resource telemetry.
        task_obj = Task(
            task_id=task.task_id,
            objective=task.objective,
            constraints=task.constraints,
        )

        exec_mgr = self.harness.create_execution(task_obj)
        ws_path = Path(exec_mgr.config.workspace.root).resolve()

        # Write starter files
        for rel_path, content in task.initial_files.items():
            fpath = ws_path / rel_path
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")

        # Execute
        exec_mgr.transition_to(ExecutionState.PLANNING, reason="Benchmark: plan task")
        exec_mgr.transition_to(ExecutionState.EXECUTING, reason="Benchmark: execute coding")

        success = True
        if executor_fn:
            try:
                success = executor_fn(exec_mgr, task)
            except Exception as e:
                logger.error("Benchmark task executor failed: %s", e)
                success = False

        if success:
            exec_mgr.transition_to(ExecutionState.VERIFYING, reason="Benchmark: verify tests")
            exec_mgr.complete(reason="Benchmark task passed verification")
        else:
            exec_mgr.fail(error_message="Benchmark task failed verification")

        events = self.harness.ledger.get_events(exec_mgr.execution_id)
        samples = exec_mgr.resource_samples
        if not samples and self.harness.monitoring_manager:
            samples = self.harness.monitoring_manager.get_samples(exec_mgr.execution_id)

        summary = self.evaluation_engine.evaluate(
            execution_id=exec_mgr.execution_id,
            events=events,
            resource_samples=samples,
            model_calls=exec_mgr.model_call_records,
            tool_responses=exec_mgr.tool_responses,
        )
        return summary

    def run_suite(
        self,
        executor_fn: Optional[Callable[[Any, BenchmarkTask], bool]] = None,
    ) -> BenchmarkReport:
        """Run all tasks in the suite and aggregate results."""
        #TODO - EXP-001: Compare generic-skill and skill-switched conditions, including skill transition overhead.
        #TODO - EXP-002: Compare single-model and phase-routed conditions, including model-switch overhead.
        #TODO - EXP-005: Add model-only through monitored-ledger execution tiers and capture disk-write overhead.
        #TODO - EXP-007: Run coarse, fine-grained, and combined tool profiles with per-profile efficiency metrics.
        #TODO - EXP-014: Run named harness configurations against identical tasks and produce statistical comparisons.
        #TODO - EXP-000: Persist raw telemetry, summaries, analysis, technical reports, and public/reproduction artifacts.
        summaries: List[EvaluationSummary] = []
        total_p = 0
        total_f = 0
        all_tokens = 0
        all_duration = 0.0
        cpu_percents: List[float] = []
        ram_mbs: List[float] = []
        peak_ram = 0.0

        for task in self.suite:
            summary = self.run_task(task, executor_fn=executor_fn)
            summaries.append(summary)

            if summary.derived_metrics.task_success:
                total_p += 1
            else:
                total_f += 1

            all_tokens += summary.raw_metrics.total_tokens or 0
            all_duration += summary.raw_metrics.total_duration_s

            if summary.raw_metrics.avg_cpu_percent > 0:
                cpu_percents.append(summary.raw_metrics.avg_cpu_percent)
            if summary.raw_metrics.avg_ram_mb > 0:
                ram_mbs.append(summary.raw_metrics.avg_ram_mb)
            if summary.raw_metrics.peak_ram_mb > peak_ram:
                peak_ram = summary.raw_metrics.peak_ram_mb

        total_tasks = len(self.suite)
        success_rate = (total_p / total_tasks) if total_tasks > 0 else 0.0
        avg_dur = (all_duration / total_tasks) if total_tasks > 0 else 0.0
        avg_cpu = (sum(cpu_percents) / len(cpu_percents)) if cpu_percents else 0.0
        avg_ram = (sum(ram_mbs) / len(ram_mbs)) if ram_mbs else 0.0

        return BenchmarkReport(
            suite_name=self.suite_name,
            total_tasks=total_tasks,
            passed_tasks=total_p,
            failed_tasks=total_f,
            success_rate=round(success_rate, 4),
            total_tokens=all_tokens,
            total_duration_s=round(all_duration, 4),
            avg_duration_s=round(avg_dur, 4),
            avg_cpu_percent=round(avg_cpu, 2),
            avg_ram_mb=round(avg_ram, 2),
            peak_ram_mb=round(peak_ram, 2),
            task_summaries=summaries,
        )
