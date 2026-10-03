"""Unit tests for sandbox runtimes and SandboxFactory."""

from pathlib import Path
from unittest.mock import patch
import pytest

from harness.sandbox.docker import DockerSandboxRuntime
from harness.sandbox.factory import SandboxFactory
from harness.sandbox.local import LocalProcessSandboxRuntime


def test_local_sandbox_lifecycle_and_execution(tmp_path: Path):
    workspace = tmp_path / "sandbox_ws"
    workspace.mkdir()

    # Create a small script in the workspace
    script = workspace / "hello.py"
    script.write_text("print('hello from sandbox')", encoding="utf-8")

    sandbox = LocalProcessSandboxRuntime()
    status = sandbox.start("exec-sb-1", str(workspace), network_enabled=False)

    assert status.running is True
    assert status.health == "healthy"

    # Execute script inside sandbox
    res = sandbox.execute_command("exec-sb-1", "python hello.py")
    assert res.exit_code == 0
    assert "hello from sandbox" in res.stdout
    assert res.duration_ms >= 0

    # Stop sandbox
    sandbox.stop("exec-sb-1")
    post_status = sandbox.get_status("exec-sb-1")
    assert post_status.running is False


def test_local_sandbox_timeout(tmp_path: Path):
    workspace = tmp_path / "timeout_ws"
    workspace.mkdir()

    sandbox = LocalProcessSandboxRuntime()
    sandbox.start("exec-sb-timeout", str(workspace))

    # Command that exceeds 1s timeout
    res = sandbox.execute_command(
        "exec-sb-timeout",
        "python -c \"import time; time.sleep(2)\"",
        timeout_seconds=1,
    )
    assert res.exit_code == -1
    assert "timeout limit" in res.stderr

    sandbox.stop("exec-sb-timeout")


def test_sandbox_factory_fallback():
    # When docker is not available, factory cleanly falls back to local sandbox
    with patch.object(DockerSandboxRuntime, "is_docker_available", return_value=False):
        sandbox = SandboxFactory.create("docker", fallback_to_local=True)
        assert isinstance(sandbox, LocalProcessSandboxRuntime)

        # When fallback is disabled, raises RuntimeError
        with pytest.raises(RuntimeError):
            SandboxFactory.create("docker", fallback_to_local=False)


def test_sandbox_factory_local_selection():
    sandbox = SandboxFactory.create("local")
    assert isinstance(sandbox, LocalProcessSandboxRuntime)


def test_sandbox_factory_invalid():
    with pytest.raises(ValueError):
        SandboxFactory.create("unsupported_runtime")
