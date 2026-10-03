"""Unit tests for BenchmarkRunner and StandardBenchmarkSuite."""

from pathlib import Path
import pytest

from harness.core.config import HarnessConfig
from harness.core.harness import Harness
from harness.evaluation.benchmark import BenchmarkRunner, BenchmarkTask, StandardBenchmarkSuite
from tests.test_interfaces import MockPolicyEngine


def test_standard_benchmark_suite_tasks():
    tasks = StandardBenchmarkSuite.get_mvp_tasks()
    assert len(tasks) == 3
    assert all(isinstance(t, BenchmarkTask) for t in tasks)
    assert any(t.name == "Fibonacci Generator" for t in tasks)


def test_benchmark_runner_suite_execution(tmp_path: Path):
    ws_dir = tmp_path / "bench_ws"
    ws_dir.mkdir()
    db_file = tmp_path / "bench.db"

    config = HarnessConfig()
    config.workspace.root = str(ws_dir)

    harness = Harness(config=config, db_path=str(db_file), policy_engine=MockPolicyEngine())

    # Create a custom small suite of 2 tasks
    tasks = [
        BenchmarkTask(task_id="t1", name="Task 1", objective="Do A"),
        BenchmarkTask(task_id="t2", name="Task 2", objective="Do B"),
    ]

    runner = BenchmarkRunner(harness, suite=tasks, suite_name="test-suite")

    # Define an executor where task 1 succeeds and task 2 fails
    def custom_executor(manager, task):
        if task.task_id == "t1":
            return True
        return False

    report = runner.run_suite(executor_fn=custom_executor)

    assert report.suite_name == "test-suite"
    assert report.total_tasks == 2
    assert report.passed_tasks == 1
    assert report.failed_tasks == 1
    assert report.success_rate == 0.5
    assert len(report.task_summaries) == 2
    assert report.task_summaries[0].derived_metrics.task_success is True
    assert report.task_summaries[1].derived_metrics.task_success is False

    harness.close()
