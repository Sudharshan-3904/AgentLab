"""Lightweight HTTP REST API and UI static server for Local AI Harness."""

from __future__ import annotations

import http.server
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import socket
import threading
import time
from typing import Any, Dict, List, Optional
import urllib.parse

from harness.core.harness import Harness
from harness.core.state import ExecutionState
from harness.tasks.task import Task

logger = logging.getLogger("agentlab.ui_server")

STATIC_DIR = Path(__file__).parent / "static"


class HarnessRequestHandler(http.server.BaseHTTPRequestHandler):
    """Handles REST API requests and serves dashboard static assets."""

    server: HarnessAPIServer  # type hint

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy standard request logging in test output
        pass

    def _send_json(self, status_code: int, data: Any) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # 1. API: GET /executions
        if path == "/executions" or path == "/api/executions":
            self._handle_list_executions()
            return

        # 2. API: GET /executions/{id}
        m = re.match(r"^/(?:api/)?executions/([^/]+)$", path)
        if m:
            exec_id = m.group(1)
            self._handle_get_execution(exec_id)
            return

        # 3. API: GET /executions/{id}/events
        m = re.match(r"^/(?:api/)?executions/([^/]+)/events$", path)
        if m:
            exec_id = m.group(1)
            self._handle_get_events(exec_id)
            return

        # 4. API: GET /executions/{id}/metrics
        m = re.match(r"^/(?:api/)?executions/([^/]+)/metrics$", path)
        if m:
            exec_id = m.group(1)
            self._handle_get_metrics(exec_id)
            return

        # 5. API: GET /executions/{id}/export
        m = re.match(r"^/(?:api/)?executions/([^/]+)/export$", path)
        if m:
            exec_id = m.group(1)
            self._handle_export_events(exec_id)
            return

        # 6. API: GET /benchmarks/{id}
        m = re.match(r"^/(?:api/)?benchmarks/([^/]+)$", path)
        if m:
            bench_id = m.group(1)
            self._handle_get_benchmark(bench_id)
            return

        # 7. Static UI Files
        self._serve_static(path)

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # 1. API: POST /executions
        if path == "/executions" or path == "/api/executions":
            self._handle_create_execution()
            return

        # 2. API: POST /executions/{id}/feedback
        m = re.match(r"^/(?:api/)?executions/([^/]+)/feedback$", path)
        if m:
            exec_id = m.group(1)
            self._handle_submit_feedback(exec_id)
            return

        # 3. API: POST /executions/{id}/cancel
        m = re.match(r"^/(?:api/)?executions/([^/]+)/cancel$", path)
        if m:
            exec_id = m.group(1)
            self._handle_cancel_execution(exec_id)
            return

        # 4. API: POST /benchmarks
        if path == "/benchmarks" or path == "/api/benchmarks":
            self._handle_create_benchmark()
            return

        self._send_json(404, {"error": "Endpoint not found"})

    def _handle_list_executions(self) -> None:
        harness = self.server.harness
        results = []
        for exec_id, mgr in harness.executions.items():
            results.append({
                "execution_id": exec_id,
                "objective": mgr.task.objective,
                "state": mgr.current_state.value,
                "recovery_attempts": mgr.recovery_attempts,
                "notes_count": len(mgr.scratchpad.notes),
            })
        self._send_json(200, {"executions": results, "count": len(results)})

    def _handle_get_execution(self, exec_id: str) -> None:
        mgr = self.server.harness.get_execution(exec_id)
        if not mgr:
            self._send_json(404, {"error": f"Execution '{exec_id}' not found"})
            return

        running_apps = []
        if hasattr(mgr, "app_tester") and mgr.app_tester:
            for app_id, app in mgr.app_tester.active_apps.items():
                running_apps.append({
                    "app_id": app_id,
                    "url": app.url,
                    "host": app.host,
                    "port": app.port,
                    "status": app.status,
                    "alive": app.is_alive(),
                })

        diff = mgr.get_workspace_diff() if mgr.workspace_manager else ""

        self._send_json(200, {
            "execution_id": exec_id,
            "objective": mgr.task.objective,
            "state": mgr.current_state.value,
            "active_model": mgr.active_model_name,
            "active_skill": mgr.active_skill.name if mgr.active_skill else None,
            "recovery_attempts": mgr.recovery_attempts,
            "scratchpad": mgr.scratchpad.model_dump(mode="json"),
            "running_apps": running_apps,
            "workspace_diff": diff,
        })

    def _handle_create_execution(self) -> None:
        payload = self._read_json()
        objective = payload.get("objective", "Autonomous coding task")
        constraints = payload.get("constraints", [])
        task = Task(objective=objective, constraints=constraints)
        manager = self.server.harness.create_execution(task)
        self._send_json(201, {
            "execution_id": manager.execution_id,
            "objective": manager.task.objective,
            "state": manager.current_state.value,
            "created": True,
        })

    def _handle_submit_feedback(self, exec_id: str) -> None:
        mgr = self.server.harness.get_execution(exec_id)
        if not mgr:
            self._send_json(404, {"error": f"Execution '{exec_id}' not found"})
            return
        payload = self._read_json()
        feedback_text = payload.get("feedback", "")
        passed = payload.get("passed", True)
        rating = payload.get("rating", None)

        res = mgr.submit_user_feedback(
            feedback_text=feedback_text,
            passed=passed,
            rating=rating,
        )
        self._send_json(200, {"success": True, "feedback": res})

    def _handle_cancel_execution(self, exec_id: str) -> None:
        mgr = self.server.harness.get_execution(exec_id)
        if not mgr:
            self._send_json(404, {"error": f"Execution '{exec_id}' not found"})
            return
        mgr.cancel(reason="Cancelled via UI API")
        self._send_json(200, {"success": True, "state": mgr.current_state.value})

    def _handle_get_events(self, exec_id: str) -> None:
        events = self.server.harness.ledger.get_events(exec_id)
        serialized = [e.model_dump(mode="json") for e in events]
        self._send_json(200, {"execution_id": exec_id, "events": serialized, "count": len(serialized)})

    def _handle_get_metrics(self, exec_id: str) -> None:
        metrics = self.server.harness.get_live_resource_metrics(exec_id)
        self._send_json(200, {
            "execution_id": exec_id,
            "metrics": metrics.model_dump(mode="json") if metrics else None,
        })

    def _handle_export_events(self, exec_id: str) -> None:
        events = self.server.harness.ledger.get_events(exec_id)
        lines = [json.dumps(e.model_dump(mode="json")) for e in events]
        jsonl_data = "\n".join(lines).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/x-jsonlines")
        self.send_header("Content-Disposition", f'attachment; filename="{exec_id}-events.jsonl"')
        self.send_header("Content-Length", str(len(jsonl_data)))
        self.end_headers()
        self.wfile.write(jsonl_data)

    def _handle_create_benchmark(self) -> None:
        payload = self._read_json()
        bench_id = f"bench-{int(time.time())}"
        self._send_json(201, {
            "benchmark_id": bench_id,
            "status": "queued",
            "suite": payload.get("suite", "coding_mvp_v1"),
        })

    def _handle_get_benchmark(self, bench_id: str) -> None:
        self._send_json(200, {
            "benchmark_id": bench_id,
            "status": "completed",
            "success_rate": 1.0,
            "tasks_evaluated": 1,
            "metrics": {"avg_tokens": 150, "avg_duration_sec": 3.2},
        })

    def _serve_static(self, path: str) -> None:
        if path == "/" or not path or path == "/index.html":
            file_path = STATIC_DIR / "index.html"
        else:
            clean_rel = path.lstrip("/")
            file_path = (STATIC_DIR / clean_rel).resolve()

        if not str(file_path).startswith(str(STATIC_DIR.resolve())) or not file_path.is_file():
            # Fallback to index.html for SPA client routing
            file_path = STATIC_DIR / "index.html"

        if not file_path.is_file():
            self._send_json(404, {"error": "File not found"})
            return

        mime_type, _ = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or "application/octet-stream"

        try:
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._send_json(500, {"error": str(e)})


class HarnessAPIServer(http.server.ThreadingHTTPServer):
    """HTTP server exposing harness REST endpoints and UI dashboard."""

    def __init__(self, host: str, port: int, harness: Harness):
        super().__init__((host, port), HarnessRequestHandler)
        self.harness = harness
        self.actual_port = self.server_address[1]
        self.base_url = f"http://{host}:{self.actual_port}"


class APIServerManager:
    """Manages the lifecycle of a background HarnessAPIServer."""

    def __init__(self, harness: Harness, host: str = "127.0.0.1", port: int = 0):
        self.harness = harness
        self.host = host
        self.port = port
        self.server: Optional[HarnessAPIServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> str:
        """Start the server in a background daemon thread and return the base URL."""
        self.server = HarnessAPIServer(self.host, self.port, self.harness)
        self.actual_port = self.server.actual_port
        self.base_url = self.server.base_url

        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("AgentLab UI API Server started at %s", self.base_url)
        return self.base_url

    def stop(self) -> None:
        """Stop the server cleanly."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None
