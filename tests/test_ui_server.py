"""Unit tests for HarnessAPIServer and REST endpoints."""

import json
import urllib.request
import urllib.error
import pytest

from harness.core.config import HarnessConfig
from harness.core.harness import Harness
from harness.ui.server import APIServerManager
from tests.test_interfaces import MockPolicyEngine


def test_ui_api_server_endpoints():
    config = HarnessConfig()
    harness = Harness(config=config, policy_engine=MockPolicyEngine())

    server_mgr = APIServerManager(harness, host="127.0.0.1", port=0)
    base_url = server_mgr.start()

    try:
        # 1. Test POST /executions
        req_data = json.dumps({"objective": "Create fibonacci function", "constraints": ["pure python"]}).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/executions",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 201
            res = json.loads(resp.read().decode("utf-8"))
            exec_id = res["execution_id"]
            assert exec_id.startswith("exec-")
            assert res["created"] is True

        # 2. Test GET /executions
        with urllib.request.urlopen(f"{base_url}/executions") as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["count"] >= 1
            assert any(e["execution_id"] == exec_id for e in data["executions"])

        # 3. Test GET /executions/{id}
        with urllib.request.urlopen(f"{base_url}/executions/{exec_id}") as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["execution_id"] == exec_id
            assert data["objective"] == "Create fibonacci function"
            assert data["state"] == "INTAKE"

        # 4. Test GET /executions/{id}/events
        with urllib.request.urlopen(f"{base_url}/executions/{exec_id}/events") as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["count"] >= 1
            assert data["events"][0]["type"] == "TASK_RECEIVED"

        # 5. Test GET /executions/{id}/metrics
        with urllib.request.urlopen(f"{base_url}/executions/{exec_id}/metrics") as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "metrics" in data

        # 6. Test POST /executions/{id}/feedback
        fb_data = json.dumps({"feedback": "Code looks good", "passed": True, "rating": 5}).encode("utf-8")
        fb_req = urllib.request.Request(
            f"{base_url}/executions/{exec_id}/feedback",
            data=fb_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(fb_req) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            assert res["success"] is True

        # 7. Test GET /executions/{id}/export (JSONL)
        with urllib.request.urlopen(f"{base_url}/executions/{exec_id}/export") as resp:
            assert resp.status == 200
            assert "jsonlines" in resp.headers.get("Content-Type", "")
            lines = resp.read().decode("utf-8").strip().split("\n")
            assert len(lines) >= 1
            first_event = json.loads(lines[0])
            assert first_event["execution_id"] == exec_id

        # 8. Test POST /benchmarks and GET /benchmarks/{id}
        b_data = json.dumps({"suite": "standard_eval"}).encode("utf-8")
        b_req = urllib.request.Request(
            f"{base_url}/benchmarks",
            data=b_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(b_req) as resp:
            assert resp.status == 201
            b_res = json.loads(resp.read().decode("utf-8"))
            b_id = b_res["benchmark_id"]

        with urllib.request.urlopen(f"{base_url}/benchmarks/{b_id}") as resp:
            assert resp.status == 200
            b_detail = json.loads(resp.read().decode("utf-8"))
            assert b_detail["benchmark_id"] == b_id

        # 9. Test POST /executions/{id}/cancel
        c_req = urllib.request.Request(
            f"{base_url}/executions/{exec_id}/cancel",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(c_req) as resp:
            assert resp.status == 200
            c_res = json.loads(resp.read().decode("utf-8"))
            assert c_res["state"] == "CANCELLED"

        # 10. Test static UI dashboard GET /
        with urllib.request.urlopen(f"{base_url}/") as resp:
            assert resp.status == 200
            assert "text/html" in resp.headers.get("Content-Type", "")
            html = resp.read().decode("utf-8")
            assert "AgentLab — Local AI Coding Harness" in html
            assert "Task Entry" in html
            assert "Execution" in html

    finally:
        server_mgr.stop()
        harness.close()
