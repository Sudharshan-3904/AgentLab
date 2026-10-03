"""Tests for PolicyEngine and ToolManager correlation and events."""

from pathlib import Path
import pytest

from harness.core.config import AutonomyLevel
from harness.core.events import EventType
from harness.security.interface import PolicyDecision
from harness.security.policy import PolicyEngine
from harness.tools.fs import ReadFileTool, WriteFileTool
from harness.tools.interface import ToolRequest, ToolStatus
from harness.tools.manager import ToolManager
from harness.tools.shell import ShellTool


def test_policy_engine_path_traversal_denial(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    engine = PolicyEngine()
    req = ToolRequest(
        execution_id="exec-p1",
        tool_name="read_file",
        arguments={"path": "../../../etc/passwd"},
    )
    from harness.security.interface import PolicyEvaluationContext
    ctx = PolicyEvaluationContext(
        execution_id="exec-p1",
        autonomy_level=AutonomyLevel.AUTONOMOUS,  # Even in autonomous, path traversal is DENIED
        tool_request=req,
        workspace_root=str(workspace),
    )
    result = engine.evaluate(ctx)
    assert result.decision == PolicyDecision.DENY
    assert "escapes workspace boundary" in result.reason


def test_policy_engine_dangerous_command_denial(tmp_path: Path):
    engine = PolicyEngine()
    req = ToolRequest(
        execution_id="exec-p2",
        tool_name="shell",
        arguments={"command": "rm -rf /"},
    )
    from harness.security.interface import PolicyEvaluationContext
    ctx = PolicyEvaluationContext(
        execution_id="exec-p2",
        autonomy_level=AutonomyLevel.AUTONOMOUS,
        tool_request=req,
        workspace_root=str(tmp_path),
    )
    result = engine.evaluate(ctx)
    assert result.decision == PolicyDecision.DENY
    assert "blacklisted dangerous" in result.reason


def test_policy_engine_autonomy_levels(tmp_path: Path):
    engine = PolicyEngine()
    shell_req = ToolRequest(
        execution_id="exec-p3",
        tool_name="shell",
        arguments={"command": "pytest"},
    )
    write_req = ToolRequest(
        execution_id="exec-p3",
        tool_name="write_file",
        arguments={"path": "app.py", "content": "pass"},
    )

    from harness.security.interface import PolicyEvaluationContext

    # Balanced mode: write is allowed, shell requires confirmation
    ctx_balanced_write = PolicyEvaluationContext(
        execution_id="exec-p3",
        autonomy_level=AutonomyLevel.BALANCED,
        tool_request=write_req,
        workspace_root=str(tmp_path),
    )
    assert engine.evaluate(ctx_balanced_write).decision == PolicyDecision.ALLOW

    ctx_balanced_shell = PolicyEvaluationContext(
        execution_id="exec-p3",
        autonomy_level=AutonomyLevel.BALANCED,
        tool_request=shell_req,
        workspace_root=str(tmp_path),
    )
    assert engine.evaluate(ctx_balanced_shell).decision == PolicyDecision.CONFIRM

    # Restricted mode: write requires confirmation
    ctx_restricted_write = PolicyEvaluationContext(
        execution_id="exec-p3",
        autonomy_level=AutonomyLevel.RESTRICTED,
        tool_request=write_req,
        workspace_root=str(tmp_path),
    )
    assert engine.evaluate(ctx_restricted_write).decision == PolicyDecision.CONFIRM


def test_tool_manager_execution_and_correlation(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    events = []
    def record_event(ev_type, src, payload, corr_id):
        events.append((ev_type, payload, corr_id))

    policy = PolicyEngine()
    manager = ToolManager(
        execution_id="exec-tm-1",
        policy_engine=policy,
        workspace_root=str(workspace),
        autonomy_level=AutonomyLevel.AUTONOMOUS,
        on_event=record_event,
    )

    write_tool = WriteFileTool(workspace_root=str(workspace))
    read_tool = ReadFileTool(workspace_root=str(workspace))
    manager.register_tool(write_tool)
    manager.register_tool(read_tool)

    # 1. Execute write
    w_resp = manager.execute_tool("write_file", {"path": "main.py", "content": "x = 42"})
    assert w_resp.status == ToolStatus.SUCCESS

    # Verify correlated events
    assert len(events) == 3  # TOOL_REQUEST, TOOL_POLICY_DECISION, TOOL_RESPONSE
    req_ev, pol_ev, resp_ev = events[0], events[1], events[2]

    assert req_ev[0] == EventType.TOOL_REQUEST
    assert pol_ev[0] == EventType.TOOL_POLICY_DECISION
    assert resp_ev[0] == EventType.TOOL_RESPONSE

    # Same correlation ID across all 3
    assert req_ev[2] == w_resp.tool_request_id
    assert pol_ev[2] == w_resp.tool_request_id
    assert resp_ev[2] == w_resp.tool_request_id

    # 2. Execute read
    r_resp = manager.execute_tool("read_file", {"path": "main.py"})
    assert r_resp.status == ToolStatus.SUCCESS
    assert r_resp.output == "x = 42"
