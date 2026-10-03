"""Unit tests for SystemResourceSampler and MonitoringManager."""

import time
import pytest

from harness.monitoring.interface import TelemetryAvailability
from harness.monitoring.manager import MonitoringManager
from harness.monitoring.sampler import SystemResourceSampler


def test_system_resource_sampler():
    sampler = SystemResourceSampler()
    sample = sampler.sample("exec-mon-1")

    assert sample.execution_id == "exec-mon-1"
    assert sample.sample_id.startswith("samp-")

    # CPU metrics validation
    assert sample.cpu.utilization_pct >= 0.0
    assert sample.cpu.user_time_s is not None

    # RAM metrics validation
    assert sample.ram.total_mb > 0.0
    assert sample.ram.used_mb > 0.0
    assert sample.ram.percent >= 0.0

    # Process metrics validation
    assert sample.process.pid > 0
    assert sample.process.rss_memory_mb > 0.0

    # GPU fallback validation (doesn't raise even if no GPU present)
    assert sample.gpu is not None
    assert sample.gpu.availability in [
        TelemetryAvailability.AVAILABLE,
        TelemetryAvailability.UNSUPPORTED,
    ]


def test_monitoring_manager_lifecycle():
    recorded_samples = []
    manager = MonitoringManager(on_sample=lambda s: recorded_samples.append(s))

    # Single point sample
    s1 = manager.sample("exec-mon-2")
    assert len(recorded_samples) == 1
    assert s1.execution_id == "exec-mon-2"

    # Background monitoring thread test
    manager.start_monitoring("exec-mon-2", interval_ms=100)
    time.sleep(0.35)

    all_samples = manager.stop_monitoring("exec-mon-2")
    assert len(all_samples) >= 3
    assert len(manager.get_samples("exec-mon-2")) >= 3
