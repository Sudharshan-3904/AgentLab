"""Integration test verifying Phase 7 Exit Criteria:
The user can see live system resource usage during an execution.
"""

from pathlib import Path
import time
import pytest

from harness.core.config import HarnessConfig
from harness.core.events import EventType
from harness.core.harness import Harness
from harness.monitoring.interface import ResourceSample
from harness.tasks.task import Task


def test_phase7_exit_criteria_live_monitoring(tmp_path: Path):
    """
    Exit Criteria:
    The user can see live system resource usage during an execution.
    """
    db_file = tmp_path / "live_monitoring.db"
    config = HarnessConfig()
    config.monitoring.interval_ms = 100

    harness = Harness(config=config, db_path=str(db_file))
    exec_mgr = harness.create_execution(Task(objective="Compute prime numbers with live monitoring"))
    execution_id = exec_mgr.execution_id

    # 1. Start live monitoring sampling
    harness.monitoring_manager.start_monitoring(execution_id, interval_ms=100)

    # 2. Simulate active computational workload
    total = sum(i * i for i in range(500000))
    time.sleep(0.35)

    # 3. User queries live resource metrics during active execution
    live_sample = harness.get_live_resource_metrics(execution_id)
    assert live_sample is not None
    assert isinstance(live_sample, ResourceSample)
    assert live_sample.execution_id == execution_id

    # Check live CPU & RAM readings
    assert live_sample.cpu.utilization_pct >= 0.0
    assert live_sample.ram.used_mb > 0.0
    assert live_sample.ram.total_mb > 0.0
    assert live_sample.process.rss_memory_mb > 0.0

    # 4. Stop monitoring and check samples
    collected = harness.monitoring_manager.stop_monitoring(execution_id)
    assert len(collected) >= 3

    # 5. Verify RESOURCE_SAMPLE events persisted in SQLite ledger
    events = harness.get_events(execution_id)
    resource_events = [e for e in events if e.type == EventType.RESOURCE_SAMPLE]
    assert len(resource_events) >= 3

    # Verify event structure
    first_res_event = resource_events[0]
    assert "cpu" in first_res_event.payload
    assert "ram" in first_res_event.payload
    assert "process" in first_res_event.payload

    harness.close()
