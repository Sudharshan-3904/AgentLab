"""Unit tests for root main.py CLI parsing and harness initialization."""

import sys
from pathlib import Path
import pytest

# Ensure root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import build_parser, create_harness_config, initialize_harness
from harness.core.config import AutonomyLevel


def test_build_parser_defaults():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.provider == "ollama"
    assert args.model == "llama3.2:latest"
    assert args.autonomy == "balanced"
    assert args.routing is True
    assert args.open_browser is False


def test_build_parser_custom_args():
    parser = build_parser()
    args = parser.parse_args([
        "--host", "0.0.0.0",
        "--port", "9090",
        "--provider", "lmstudio",
        "--model", "qwen2.5:1.5b",
        "--autonomy", "autonomous",
        "--planning-model", "llama3.2:latest",
        "--coding-model", "qwen2.5:1.5b",
        "--temperature", "0.7",
        "--max-recovery", "3",
        "--open-browser",
    ])
    assert args.host == "0.0.0.0"
    assert args.port == 9090
    assert args.provider == "lmstudio"
    assert args.model == "qwen2.5:1.5b"
    assert args.autonomy == "autonomous"
    assert args.planning_model == "llama3.2:latest"
    assert args.coding_model == "qwen2.5:1.5b"
    assert args.temperature == 0.7
    assert args.max_recovery == 3
    assert args.open_browser is True


def test_create_harness_config():
    parser = build_parser()
    args = parser.parse_args([
        "--model", "llama3.2:latest",
        "--autonomy", "restricted",
        "--planning-model", "llama3.2:latest",
        "--coding-model", "qwen2.5:1.5b",
    ])
    config = create_harness_config(args)

    assert config.model.default_model == "llama3.2:latest"
    assert config.execution.autonomy == AutonomyLevel.RESTRICTED
    assert config.routing.enabled is True
    assert config.routing.rules.get("planning") == "llama3.2:latest"
    assert config.routing.rules.get("coding") == "qwen2.5:1.5b"


def test_initialize_harness(tmp_path):
    parser = build_parser()
    db_file = tmp_path / "test_ledger.db"
    workspace_dir = tmp_path / "test_workspace"
    args = parser.parse_args([
        "--workspace", str(workspace_dir),
        "--db", str(db_file),
    ])
    config = create_harness_config(args)
    harness = initialize_harness(config, str(db_file))

    assert "planning" in harness.skills
    assert "coding" in harness.skills
    assert "testing" in harness.skills
    assert "debugging" in harness.skills
    assert Path(config.workspace.root).exists()


def test_autonomous_execution_run(tmp_path):
    from tests.test_interfaces import MockModelProvider
    workspace = tmp_path / "workspace"
    db_file = tmp_path / "ledger.db"
    parser = build_parser()
    args = parser.parse_args(["--workspace", str(workspace), "--db", str(db_file)])
    config = create_harness_config(args)
    harness = initialize_harness(config, str(db_file))
    harness.register_model_provider("ollama", MockModelProvider())

    manager = harness.create_execution("Build a REST API with FastAPI and SQLite")
    assert manager.current_state.value == "INTAKE"

    manager.run_autonomous()

    assert manager.current_state.value == "COMPLETED"
    assert (workspace / "server.py").exists()
    assert len(manager.scratchpad.completed) >= 1


def test_ui_server_start_endpoint(tmp_path):
    import json
    import urllib.request
    from harness.ui.server import APIServerManager
    from tests.test_interfaces import MockModelProvider

    workspace = tmp_path / "workspace"
    db_file = tmp_path / "ledger.db"
    parser = build_parser()
    args = parser.parse_args(["--workspace", str(workspace), "--db", str(db_file)])
    config = create_harness_config(args)
    harness = initialize_harness(config, str(db_file))
    harness.register_model_provider("ollama", MockModelProvider())

    server_mgr = APIServerManager(harness, host="127.0.0.1", port=0)
    base_url = server_mgr.start()

    try:
        # Create execution without auto_run
        req_data = json.dumps({"objective": "Generate helper module", "constraints": []}).encode("utf-8")
        req = urllib.request.Request(f"{base_url}/executions", data=req_data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            exec_id = data["execution_id"]
            assert data["state"] == "INTAKE"

        # Trigger /start
        start_req = urllib.request.Request(f"{base_url}/executions/{exec_id}/start", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(start_req) as resp:
            start_data = json.loads(resp.read().decode("utf-8"))
            assert start_data["success"] is True

        import time
        # Wait up to 5s for autonomous background run to finish
        for _ in range(50):
            time.sleep(0.1)
            mgr = harness.get_execution(exec_id)
            if mgr and mgr.is_finished:
                break

        assert mgr.current_state.value == "COMPLETED"
    finally:
        server_mgr.stop()

