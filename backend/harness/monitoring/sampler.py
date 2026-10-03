"""System hardware and process resource sampler using psutil and NVML."""

from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Optional
import uuid
import psutil

from harness.monitoring.interface import (
    CpuMetrics,
    GpuMetrics,
    ProcessMetrics,
    RamMetrics,
    ResourceSample,
    TelemetryAvailability,
)


class SystemResourceSampler:
    """Collects hardware and process telemetry without inventing unsupported values."""

    def __init__(self):
        self._process = psutil.Process(os.getpid())
        # Prime cpu_percent
        self._process.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None)

    def sample_cpu(self) -> CpuMetrics:
        """Measure system CPU utilization and CPU times."""
        util = psutil.cpu_percent(interval=None)
        times = psutil.cpu_times()
        return CpuMetrics(
            utilization_pct=float(util),
            user_time_s=float(times.user),
            system_time_s=float(times.system),
        )

    def sample_ram(self) -> RamMetrics:
        """Measure system RAM utilization."""
        vm = psutil.virtual_memory()
        return RamMetrics(
            used_mb=round(vm.used / (1024 * 1024), 2),
            total_mb=round(vm.total / (1024 * 1024), 2),
            available_mb=round(vm.available / (1024 * 1024), 2),
            percent=float(vm.percent),
        )

    def sample_process(self) -> ProcessMetrics:
        """Measure current harness agent process resource footprint."""
        try:
            mem = self._process.memory_info()
            rss_mb = round(mem.rss / (1024 * 1024), 2)
            cpu = self._process.cpu_percent(interval=None)
            threads = self._process.num_threads()
            children = len(self._process.children(recursive=True))
            return ProcessMetrics(
                pid=self._process.pid,
                cpu_percent=float(cpu),
                rss_memory_mb=rss_mb,
                num_threads=threads,
                num_child_processes=children,
            )
        except Exception:
            return ProcessMetrics(pid=os.getpid())

    def sample_gpu(self) -> GpuMetrics:
        """Measure GPU telemetry if hardware support and NVML drivers exist."""
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8")

            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)

            try:
                power_mw = pynvml.nvmlDeviceGetPowerUsage(handle)
                power_watts = round(power_mw / 1000.0, 2)
            except Exception:
                power_watts = None

            return GpuMetrics(
                availability=TelemetryAvailability.AVAILABLE,
                device_name=name,
                utilization_pct=float(util.gpu),
                vram_used_mb=round(mem.used / (1024 * 1024), 2),
                vram_total_mb=round(mem.total / (1024 * 1024), 2),
                power_watts=power_watts,
                temperature_c=float(temp),
            )
        except Exception:
            return GpuMetrics(
                availability=TelemetryAvailability.UNSUPPORTED,
                device_name=None,
            )

    def sample(self, execution_id: str) -> ResourceSample:
        """Collect complete synchronized resource sample."""
        sample_id = f"samp-{uuid.uuid4().hex[:8]}"
        return ResourceSample(
            sample_id=sample_id,
            execution_id=execution_id,
            cpu=self.sample_cpu(),
            ram=self.sample_ram(),
            gpu=self.sample_gpu(),
            process=self.sample_process(),
        )
