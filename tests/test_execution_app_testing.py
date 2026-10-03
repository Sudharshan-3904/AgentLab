"""Unit tests for ExecutionManager integration with Application Testing."""

import sys
import tempfile
from pathlib import Path
import pytest

from harness.core.config import HarnessConfig
from harness.core.events import EventType
from harness.core.state import ExecutionState
from harness.execution.manager import ExecutionManager
from harness.execution.app_tester import AppTestingManager
from harness.ledger.sqlite import SQLiteEventLedger
from harness.tasks.task import Task
from tests.test_interfaces import MockPolicyEngine


def test_execution_manager_application_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        # Create a mock web server
        server_py = ws / "server.py"
        server_py.write_text(
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
        self.wfile.write(b'{"status": "ready", "version": "1.0"}')

with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
    httpd.serve_forever()
""",
            encoding="utf-8",
        )

        task = Task.from_prompt("Build and preview web application")
        config = HarnessConfig()
        config.workspace.root = str(ws)
        ledger = SQLiteEventLedger(":memory:")
        policy = MockPolicyEngine()

        manager = ExecutionManager(
            task=task,
            config=config,
            ledger=ledger,
            policy_engine=policy,
        )

        # Progress to EXECUTING
        manager.transition_to(ExecutionState.PLANNING, reason="Start planning")
        manager.transition_to(ExecutionState.EXECUTING, reason="Start execution")
        assert manager.current_state == ExecutionState.EXECUTING

        # Launch application
        app = manager.launch_application(
            workspace_path=str(ws),
            command=[sys.executable, "server.py", "{port}"],
        )

        try:
            assert manager.current_state == ExecutionState.TESTING
            assert app.is_alive()

            # Health check probe
            healthy = manager.check_application_health(app, timeout=8.0, retry_interval=0.3)
            assert healthy is True

            # Submit user feedback
            fb = manager.submit_user_feedback(
                feedback_text="Web API responded with status ready",
                passed=True,
                rating=5,
            )
            assert fb["passed"] is True
            assert any("User Feedback: Web API responded with status ready" in note for note in manager.scratchpad.notes)

            # Query ledger events
            events = ledger.get_events(manager.execution_id)
            event_types = [e.type for e in events]
            assert EventType.APPLICATION_LAUNCHED in event_types
            assert EventType.APPLICATION_HEALTH_CHECK in event_types
            assert EventType.USER_FEEDBACK in event_types
        finally:
            manager.stop_application()
            assert not app.is_alive()
            # Check stopped event
            events = ledger.get_events(manager.execution_id)
            assert any(e.type == EventType.APPLICATION_STOPPED for e in events)
