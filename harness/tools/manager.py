"""Tool Manager coordinating tool requests, policy evaluation, and event telemetry."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from harness.core.config import AutonomyLevel
from harness.core.events import EventType
from harness.security.interface import (
    IPolicyEngine,
    PolicyDecision,
    PolicyEvaluationContext,
)
from harness.tools.interface import (
    ITool,
    ToolRequest,
    ToolResponse,
    ToolStatus,
)


class ToolManager:
    """Manages tool registration, policy enforcement, correlation IDs, and execution ledger."""

    def __init__(
        self,
        execution_id: str,
        policy_engine: IPolicyEngine,
        workspace_root: str = "./workspace",
        autonomy_level: AutonomyLevel = AutonomyLevel.BALANCED,
        on_event: Optional[Callable[[EventType, str, Dict[str, Any], Optional[str]], None]] = None,
    ):
        self.execution_id = execution_id
        self.policy_engine = policy_engine
        self.workspace_root = workspace_root
        self.autonomy_level = autonomy_level
        self._on_event = on_event
        self._tools: Dict[str, ITool] = {}
        self.tool_call_history: List[ToolResponse] = []

    def register_tool(self, tool: ITool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ITool]:
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        source_skill: Optional[str] = None,
        confirm_callback: Optional[Callable[[str], bool]] = None,
    ) -> ToolResponse:
        """Execute tool request through policy verification and ledger logging."""
        tool = self._tools.get(tool_name)
        if not tool:
            resp = ToolResponse(
                tool_request_id=f"req-err-{int(time.time()*1000)}",
                execution_id=self.execution_id,
                tool_name=tool_name,
                status=ToolStatus.ERROR,
                error=f"Unregistered tool: '{tool_name}'",
            )
            self.tool_call_history.append(resp)
            return resp

        req = ToolRequest(
            execution_id=self.execution_id,
            tool_name=tool_name,
            arguments=arguments,
            source_skill=source_skill,
        )

        # 1. Record TOOL_REQUEST
        if self._on_event:
            self._on_event(
                EventType.TOOL_REQUEST,
                "tool_manager",
                {"tool": tool_name, "arguments": arguments, "source_skill": source_skill},
                req.tool_request_id,
            )

        # 2. Policy Evaluation
        policy_ctx = PolicyEvaluationContext(
            execution_id=self.execution_id,
            autonomy_level=self.autonomy_level,
            tool_request=req,
            workspace_root=self.workspace_root,
        )
        policy_res = self.policy_engine.evaluate(policy_ctx)

        # 3. Record TOOL_POLICY_DECISION
        if self._on_event:
            self._on_event(
                EventType.TOOL_POLICY_DECISION,
                "policy_engine",
                {
                    "decision": policy_res.decision.value,
                    "reason": policy_res.reason,
                    "prompt": policy_res.requires_user_prompt,
                },
                req.tool_request_id,
            )

        # Handle Policy Decision
        if policy_res.decision == PolicyDecision.DENY:
            resp = ToolResponse(
                tool_request_id=req.tool_request_id,
                execution_id=self.execution_id,
                tool_name=tool_name,
                status=ToolStatus.DENIED,
                error=f"Denied by policy: {policy_res.reason}",
            )
        elif policy_res.decision == PolicyDecision.CONFIRM:
            confirmed = confirm_callback(policy_res.requires_user_prompt or "") if confirm_callback else False
            if not confirmed:
                resp = ToolResponse(
                    tool_request_id=req.tool_request_id,
                    execution_id=self.execution_id,
                    tool_name=tool_name,
                    status=ToolStatus.DENIED,
                    error="Action requires user confirmation which was declined or unavailable.",
                )
            else:
                resp = tool.execute(req)
        else:  # ALLOW
            resp = tool.execute(req)

        self.tool_call_history.append(resp)

        # 4. Record TOOL_RESPONSE
        if self._on_event:
            self._on_event(
                EventType.TOOL_RESPONSE,
                "tool_manager",
                {
                    "status": resp.status.value,
                    "output": resp.output,
                    "error": resp.error,
                    "duration_ms": resp.duration_ms,
                },
                req.tool_request_id,
            )

        return resp
