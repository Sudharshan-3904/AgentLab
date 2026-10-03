"""Unit tests for Application Testing Manager and Application Detection."""

import sys
import tempfile
import time
from pathlib import Path
import pytest

from harness.execution.app_tester import AppDetector, AppTestingManager, LaunchedApp


def test_app_detector_python_http():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        app_py = ws / "app.py"
        app_py.write_text("print('hello')", encoding="utf-8")

        detected = AppDetector.detect(ws)
        assert detected is not None
        assert detected.app_type == "python_http"
        assert detected.entry_point == "app.py"


def test_app_detector_fastapi():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        main_py = ws / "main.py"
        main_py.write_text("from fastapi import FastAPI\napp = FastAPI()", encoding="utf-8")

        detected = AppDetector.detect(ws)
        assert detected is not None
        assert detected.app_type == "python_fastapi"
        assert detected.entry_point == "main.py"
        assert any("uvicorn" in part for part in detected.suggested_command)


def test_app_detector_static_html():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        index_html = ws / "index.html"
        index_html.write_text("<h1>AgentLab Preview</h1>", encoding="utf-8")

        detected = AppDetector.detect(ws)
        assert detected is not None
        assert detected.app_type == "static_html"
        assert detected.entry_point == "index.html"


def test_app_tester_find_available_port():
    port1 = AppTestingManager.find_available_port()
    port2 = AppTestingManager.find_available_port()
    assert port1 > 0
    assert port2 > 0


def test_app_tester_build():
    manager = AppTestingManager()
    with tempfile.TemporaryDirectory() as tmpdir:
        res = manager.build([sys.executable, "-c", "print('Build complete')"], cwd=tmpdir)
        assert res["success"] is True
        assert res["exit_code"] == 0
        assert "Build complete" in res["stdout"]


def test_app_tester_launch_and_health_check():
    events = []
    manager = AppTestingManager(on_event=lambda ev_type, src, payload: events.append((ev_type, payload)))

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        # Create a simple python script running an HTTP server
        server_script = ws / "server.py"
        server_script.write_text(
            """
import http.server
import socketserver
import os
import sys

port = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 8080))
class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok", "app": "test_app"}')

with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
    httpd.serve_forever()
""",
            encoding="utf-8",
        )

        app = manager.launch(
            workspace_path=ws,
            command=[sys.executable, "server.py", "{port}"],
        )

        try:
            assert app.is_alive()
            assert app.port > 0

            # Health check probe
            healthy = manager.health_check(app, timeout=8.0, retry_interval=0.3)
            assert healthy is True
            assert app.status == "healthy"

            # Check logs
            time.sleep(0.5)
            # Collect feedback
            fb = manager.collect_feedback(
                execution_id="exec-123",
                feedback_text="Application loaded and responded with status ok.",
                passed=True,
                rating=5,
            )
            assert fb["passed"] is True
            assert fb["rating"] == 5

            # Verify emitted events
            event_types = [e[0] for e in events]
            assert "APPLICATION_LAUNCHED" in event_types
            assert "APPLICATION_HEALTH_CHECK" in event_types
            assert "USER_FEEDBACK" in event_types
        finally:
            manager.stop_all()
            assert not app.is_alive()
