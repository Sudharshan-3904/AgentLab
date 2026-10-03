"""Monitoring interface and telemetry sample contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class TelemetryAvailability(str, Enum):
    """Availability status of specific hardware telemetry."""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"


class CpuMetrics(BaseModel):
    utilization_pct: float = 0.0
    user_time_s: Optional[float] = None
    system_time_s: Optional[float] = None


class RamMetrics(BaseModel):
    used_mb: float = 0.0
    total_mb: float = 0.0
    available_mb: float = 0.0
    percent: float = 0.0


class GpuMetrics(BaseModel):
    availability: TelemetryAvailability = TelemetryAvailability.UNSUPPORTED
    device_name: Optional[str] = None
    utilization_pct: Optional[float] = None
    vram_used_mb: Optional[float] = None
    vram_total_mb: Optional[float] = None
    power_watts: Optional[float] = None
    temperature_c: Optional[float] = None


class ProcessMetrics(BaseModel):
    pid: int = 0
    cpu_percent: float = 0.0
    rss_memory_mb: float = 0.0
    num_threads: int = 1
    num_child_processes: int = 0


class ResourceSample(BaseModel):
    """A single periodic resource telemetry measurement."""
    sample_id: str
    execution_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cpu: CpuMetrics = Field(default_factory=CpuMetrics)
    ram: RamMetrics = Field(default_factory=RamMetrics)
    gpu: Optional[GpuMetrics] = None
    process: ProcessMetrics = Field(default_factory=ProcessMetrics)


class IMonitoringManager(ABC):
    """Abstract interface for system resource monitoring."""

    @abstractmethod
    def sample(self, execution_id: str) -> ResourceSample:
        """Collect and return a point-in-time resource measurement."""
        pass

    @abstractmethod
    def start_monitoring(self, execution_id: str, interval_ms: int = 500) -> None:
        """Start background sampling for an execution."""
        pass

    @abstractmethod
    def stop_monitoring(self, execution_id: str) -> List[ResourceSample]:
        """Stop background sampling and return collected samples."""
        pass

    @abstractmethod
    def get_samples(self, execution_id: str) -> List[ResourceSample]:
        """Retrieve all recorded samples for an execution."""
        pass
