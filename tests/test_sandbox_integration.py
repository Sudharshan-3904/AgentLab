"""Integration test verifying Phase 6 Exit Criteria:
Generated code can execute inside a controlled sandbox environment.
"""

from pathlib import Path
import pytest

from harness.core.config import HarnessConfig
from harness.core.harness import Harness
from harness.sandbox.factory import SandboxFactory
from harness.tasks.task import Task
from harness.tools.fs import WriteFileTool


def test_phase6_exit_criteria_sandbox_execution(tmp_path: Path):
    """
    Exit Criteria:
    Generated code can execute inside a controlled environment.
    """
    workspace = tmp_path / "sandbox_workspace"
    workspace.mkdir()

    # 1. Generate code to be executed inside sandbox
    code = (
        "import json, sys\n"
        "data = {'status': 'processed', 'items': [1, 2, 3, 4, 5]}\n"
        "result = {'sum': sum(data['items']), 'count': len(data['items'])}\n"
        "with open('output.json', 'w') as f:\n"
        "    json.dump(result, f)\n"
        "print(f\"SUCCESS: Computed sum={result['sum']}\")\n"
    )
    (workspace / "data_pipeline.py").write_text(code, encoding="utf-8")

    # 2. Instantiate controlled sandbox using factory
    sandbox = SandboxFactory.create("local")
    execution_id = "exec-phase6-controlled"

    # Start sandbox with mounted workspace
    start_status = sandbox.start(
        execution_id=execution_id,
        workspace_path=str(workspace),
        network_enabled=False,
    )
    assert start_status.running is True
    assert start_status.health == "healthy"

    # 3. Execute the generated code inside the controlled sandbox
    exec_result = sandbox.execute_command(
        execution_id=execution_id,
        command="python data_pipeline.py",
        timeout_seconds=30,
    )

    # 4. Verify successful execution output and generated artifacts
    assert exec_result.exit_code == 0
    assert "SUCCESS: Computed sum=15" in exec_result.stdout
    assert exec_result.duration_ms > 0

    output_file = workspace / "output.json"
    assert output_file.exists()
    assert '"sum": 15' in output_file.read_text(encoding="utf-8")

    # 5. Cleanly stop sandbox environment
    sandbox.stop(execution_id)
    final_status = sandbox.get_status(execution_id)
    assert final_status.running is False
