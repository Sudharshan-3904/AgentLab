"""Phase 9 Integration Test: Application Testing Exit Criteria.

Exit Criteria:
The user can interact with a generated local web application and return feedback to the execution.
"""

import json
from pathlib import Path
import sys
import tempfile
import urllib.request
import pytest

from harness.core.config import HarnessConfig
from harness.core.events import EventType
from harness.core.harness import Harness
from harness.core.state import ExecutionState
from harness.tasks.task import Task
from tests.test_interfaces import MockPolicyEngine


def test_phase9_exit_criteria_interact_with_generated_app_and_feedback(tmp_path: Path):
    """Verify that a generated local web application can be launched, probed,

    interacted with over HTTP, and receive user feedback recorded in ledger & scratchpad.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db_file = tmp_path / "phase9_ledger.db"

    # 1. Agent generates a local web application in workspace
    app_file = workspace / "main.py"
    app_code = """
import http.server
import json
import os
import sys

PORT = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 8000))

class AgentLabTestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"status": "ok", "app": "AgentLab Microservice", "version": "1.0.0"}
            self.wfile.write(json.dumps(response).encode("utf-8"))
        elif self.path == "/data":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"items": ["item1", "item2", "item3"], "count": 3}
            self.wfile.write(json.dumps(response).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    with http.server.HTTPServer(("127.0.0.1", PORT), AgentLabTestHandler) as server:
        server.serve_forever()
"""
    app_file.write_text(app_code, encoding="utf-8")

    # 2. Configure and initialize Harness
    config = HarnessConfig()
    config.workspace.root = str(workspace)
    config.workspace.git_enabled = False

    harness = Harness(
        config=config,
        db_path=str(db_file),
        policy_engine=MockPolicyEngine(),
    )

    # 3. Create execution
    execution = harness.create_execution("Create an HTTP microservice with health and data endpoints")
    assert execution.current_state == ExecutionState.INTAKE

    # Advance execution through planning and executing
    execution.transition_to(ExecutionState.PLANNING, reason="Decompose requirements")
    execution.transition_to(ExecutionState.EXECUTING, reason="Code microservice")

    # 4. Auto-detect application in workspace
    detected = execution.app_tester.detect(workspace)
    assert detected is not None
    assert detected.entry_point == "main.py"

    # 5. Launch application on ephemeral local port
    launched_app = execution.launch_application(
        workspace_path=str(workspace),
        command=[sys.executable, "main.py", "{port}"],
    )

    try:
        # Execution transitions to TESTING state
        assert execution.current_state == ExecutionState.TESTING
        assert launched_app.is_alive()
        assert launched_app.port > 0
        base_url = launched_app.url

        # 6. Verify health check probe passes
        is_healthy = execution.check_application_health(launched_app, path="/health", timeout=8.0, retry_interval=0.3)
        assert is_healthy is True

        # 7. User interacts with the generated web application over HTTP
        # Check root health endpoint
        with urllib.request.urlopen(f"{base_url}/health", timeout=2.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "ok"
            assert data["app"] == "AgentLab Microservice"

        # Check /data endpoint
        with urllib.request.urlopen(f"{base_url}/data", timeout=2.0) as resp:
            assert resp.status == 200
            data_resp = json.loads(resp.read().decode("utf-8"))
            assert data_resp["count"] == 3
            assert "item1" in data_resp["items"]

        # 8. User submits feedback on the running application
        feedback_result = execution.submit_user_feedback(
            feedback_text="Interactive testing verified: /health and /data endpoints returned 200 OK with expected JSON payloads.",
            passed=True,
            rating=5,
            metadata={"tested_endpoints": ["/health", "/data"], "latency_ms": 12},
        )

        assert feedback_result["passed"] is True
        assert feedback_result["rating"] == 5

        # 9. Verify scratchpad updated with feedback note
        assert any("User Feedback: Interactive testing verified" in note for note in execution.scratchpad.notes)

        # 10. Verify ledger persisted all application events
        events = harness.ledger.get_events(execution.execution_id)
        event_types = [e.type for e in events]
        assert EventType.APPLICATION_LAUNCHED in event_types
        assert EventType.APPLICATION_HEALTH_CHECK in event_types
        assert EventType.USER_FEEDBACK in event_types

        # Complete execution successfully
        execution.transition_to(ExecutionState.COMPLETED, reason="Application tested and accepted by user feedback")
        assert execution.current_state == ExecutionState.COMPLETED

    finally:
        # 11. Clean shutdown of application
        execution.stop_application()
        assert not launched_app.is_alive()

        # Check APPLICATION_STOPPED event is present in ledger
        events = harness.ledger.get_events(execution.execution_id)
        assert any(e.type == EventType.APPLICATION_STOPPED for e in events)
