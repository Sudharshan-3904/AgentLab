"""Phase 11 Integration Test: Lightweight UI Exit Criteria.

Exit Criteria:
A user can execute a coding task without interacting directly with the Python runtime.
"""

import json
from pathlib import Path
import urllib.request
import pytest

from harness.core.config import HarnessConfig
from harness.core.harness import Harness
from harness.core.state import ExecutionState
from harness.ui.server import APIServerManager
from tests.test_interfaces import MockPolicyEngine


def test_phase11_exit_criteria_execute_task_via_http_api(tmp_path: Path):
    """Verify that an end-user can execute and observe a coding task entirely

    through the HTTP REST API and UI server without touching the Python runtime.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db_file = tmp_path / "ui_integration.db"

    config = HarnessConfig()
    config.workspace.root = str(workspace)

    harness = Harness(
        config=config,
        db_path=str(db_file),
        policy_engine=MockPolicyEngine(),
    )

    server = APIServerManager(harness, host="127.0.0.1", port=0)
    base_url = server.start()

    try:
        # Step 1: User accesses the Dashboard UI
        with urllib.request.urlopen(f"{base_url}/") as response:
            assert response.status == 200
            assert "text/html" in response.headers.get("Content-Type", "")
            html_content = response.read().decode("utf-8")
            assert "AgentLab" in html_content
            assert "Task Entry" in html_content

        # Step 2: User initiates a coding task via POST /executions
        task_payload = json.dumps({
            "objective": "Build a currency converter REST API in python",
            "constraints": ["Return JSON", "Include error handling"],
        }).encode("utf-8")

        post_req = urllib.request.Request(
            f"{base_url}/executions",
            data=task_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(post_req) as response:
            assert response.status == 201
            data = json.loads(response.read().decode("utf-8"))
            execution_id = data["execution_id"]
            assert execution_id.startswith("exec-")
            assert data["state"] == "INTAKE"

        # Step 3: User polls execution status via GET /executions/{id}
        with urllib.request.urlopen(f"{base_url}/executions/{execution_id}") as response:
            assert response.status == 200
            status_data = json.loads(response.read().decode("utf-8"))
            assert status_data["execution_id"] == execution_id
            assert status_data["objective"] == "Build a currency converter REST API in python"
            assert "scratchpad" in status_data

        # Simulate autonomous engine progressing state in background
        exec_mgr = harness.get_execution(execution_id)
        assert exec_mgr is not None
        exec_mgr.transition_to(ExecutionState.PLANNING, reason="Decompose currency converter")
        exec_mgr.transition_to(ExecutionState.EXECUTING, reason="Implement converter endpoints")

        # Step 4: User inspects live events stream via GET /executions/{id}/events
        with urllib.request.urlopen(f"{base_url}/executions/{execution_id}/events") as response:
            assert response.status == 200
            events_data = json.loads(response.read().decode("utf-8"))
            assert events_data["count"] >= 3
            types = [e["type"] for e in events_data["events"]]
            assert "TASK_RECEIVED" in types
            assert "EXECUTION_STATE_CHANGED" in types

        # Step 5: User monitors resource telemetry via GET /executions/{id}/metrics
        with urllib.request.urlopen(f"{base_url}/executions/{execution_id}/metrics") as response:
            assert response.status == 200
            metrics_data = json.loads(response.read().decode("utf-8"))
            assert metrics_data["execution_id"] == execution_id

        # Step 6: User returns preview feedback via POST /executions/{id}/feedback
        feedback_payload = json.dumps({
            "feedback": "Currency conversion rates return accurately for USD/EUR/GBP.",
            "passed": True,
            "rating": 5,
        }).encode("utf-8")

        fb_req = urllib.request.Request(
            f"{base_url}/executions/{execution_id}/feedback",
            data=feedback_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(fb_req) as response:
            assert response.status == 200
            fb_res = json.loads(response.read().decode("utf-8"))
            assert fb_res["success"] is True

        # Complete execution
        exec_mgr.transition_to(ExecutionState.VERIFYING, reason="Verification")
        exec_mgr.complete("Task finished and verified by user")

        # Step 7: User downloads audit trail via GET /executions/{id}/export
        with urllib.request.urlopen(f"{base_url}/executions/{execution_id}/export") as response:
            assert response.status == 200
            content = response.read().decode("utf-8").strip()
            lines = content.split("\n")
            assert len(lines) >= 4
            event_types = [json.loads(line)["type"] for line in lines]
            assert "USER_FEEDBACK" in event_types

        # Step 8: User views execution in historical executions list
        with urllib.request.urlopen(f"{base_url}/executions") as response:
            assert response.status == 200
            history_data = json.loads(response.read().decode("utf-8"))
            assert any(item["execution_id"] == execution_id and item["state"] == "COMPLETED" for item in history_data["executions"])

    finally:
        server.stop()
        harness.close()
