"""Monitoring Manager orchestrating periodic system and process telemetry collection."""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional

from harness.monitoring.interface import IMonitoringManager, ResourceSample
from harness.monitoring.sampler import SystemResourceSampler


class MonitoringManager(IMonitoringManager):
    """Manages periodic resource sampling threads and historical telemetry."""

    def __init__(
        self,
        sampler: Optional[SystemResourceSampler] = None,
        on_sample: Optional[Callable[[ResourceSample], None]] = None,
    ):
        self.sampler = sampler or SystemResourceSampler()
        self._on_sample = on_sample
        self._samples: Dict[str, List[ResourceSample]] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def sample(self, execution_id: str) -> ResourceSample:
        """Collect and record single point-in-time sample."""
        s = self.sampler.sample(execution_id)
        with self._lock:
            if execution_id not in self._samples:
                self._samples[execution_id] = []
            self._samples[execution_id].append(s)

        if self._on_sample:
            self._on_sample(s)
        return s

    def start_monitoring(self, execution_id: str, interval_ms: int = 500) -> None:
        """Start background daemon thread collecting periodic resource telemetry."""
        with self._lock:
            if execution_id in self._threads and self._threads[execution_id].is_alive():
                return
            if execution_id not in self._samples:
                self._samples[execution_id] = []

            stop_event = threading.Event()
            self._stop_events[execution_id] = stop_event

        def _monitor_loop():
            sleep_sec = max(interval_ms / 1000.0, 0.05)
            while not stop_event.is_set():
                try:
                    self.sample(execution_id)
                except Exception:
                    pass
                stop_event.wait(timeout=sleep_sec)

        thread = threading.Thread(
            target=_monitor_loop,
            name=f"MonitorThread-{execution_id}",
            daemon=True,
        )
        with self._lock:
            self._threads[execution_id] = thread
        thread.start()

    def stop_monitoring(self, execution_id: str) -> List[ResourceSample]:
        """Signal background sampling thread to stop and return all collected samples."""
        with self._lock:
            stop_event = self._stop_events.pop(execution_id, None)
            thread = self._threads.pop(execution_id, None)

        if stop_event:
            stop_event.set()
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

        with self._lock:
            return list(self._samples.get(execution_id, []))

    def get_samples(self, execution_id: str) -> List[ResourceSample]:
        """Retrieve historical telemetry samples for an execution."""
        with self._lock:
            return list(self._samples.get(execution_id, []))
