"""Configurable policy engine for tool permissions and safety boundaries."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Set

from harness.core.config import AutonomyLevel
from harness.security.interface import (
    IPolicyEngine,
    PolicyDecision,
    PolicyEvaluationContext,
    PolicyEvaluationResult,
)


DANGEROUS_COMMAND_PATTERNS = [
    r"rm\s+-rf\s+[/~]",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",  # Fork bomb
    r"mkfs",
    r"dd\s+if=.*of=/dev",
    r"chmod\s+-R\s+777\s+/",
    r">\s*/dev/sd[a-z]",
]


class PolicyEngine(IPolicyEngine):
    """Enforces autonomy policy matrix and workspace boundary constraints."""

    def __init__(self, confirmed_by_user: bool = False):
        self.confirmed_by_user = confirmed_by_user

    def _is_blacklisted_command(self, cmd: str) -> bool:
        """Check if command matches forbidden destructive patterns."""
        for pattern in DANGEROUS_COMMAND_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return True
        return False

    def evaluate(self, context: PolicyEvaluationContext) -> PolicyEvaluationResult:
        tool_req = context.tool_request
        tool_name = tool_req.tool_name
        args = tool_req.arguments
        autonomy = context.autonomy_level

        # 1. Path safety verification for filesystem arguments
        for key in ["path", "directory", "test_path"]:
            rel_path = args.get(key)
            if rel_path and isinstance(rel_path, str):
                try:
                    root = Path(context.workspace_root).resolve()
                    target = (root / rel_path).resolve()
                    target.relative_to(root)
                except ValueError:
                    return PolicyEvaluationResult(
                        decision=PolicyDecision.DENY,
                        reason=f"Path '{rel_path}' escapes workspace boundary '{context.workspace_root}'",
                    )

        # 2. Command safety verification for shell tool
        if tool_name == "shell":
            cmd = args.get("command", "")
            if self._is_blacklisted_command(cmd):
                return PolicyEvaluationResult(
                    decision=PolicyDecision.DENY,
                    reason=f"Command matches blacklisted dangerous system pattern: '{cmd}'",
                )

        # 3. Autonomy policy matrix evaluation
        # Determine danger tier
        is_read_only = tool_name in ["read_file", "list_files"]
        is_high_risk = tool_name in ["shell"]
        is_normal = not is_read_only and not is_high_risk

        if autonomy == AutonomyLevel.AUTONOMOUS:
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                reason="Autonomous mode: all workspace-safe operations permitted.",
            )

        if autonomy == AutonomyLevel.BALANCED:
            if is_high_risk:
                if self.confirmed_by_user:
                    return PolicyEvaluationResult(
                        decision=PolicyDecision.ALLOW,
                        reason="High risk shell operation user-confirmed under balanced mode.",
                    )
                return PolicyEvaluationResult(
                    decision=PolicyDecision.CONFIRM,
                    reason="Balanced mode requires confirmation for high-risk shell execution.",
                    requires_user_prompt=f"Confirm execution of shell command: {args.get('command')}",
                )
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                reason="Balanced mode permits routine workspace operations.",
            )

        # RESTRICTED mode
        if is_read_only:
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                reason="Restricted mode permits read-only operations.",
            )

        if self.confirmed_by_user:
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                reason="User confirmed modification operation under restricted mode.",
            )

        return PolicyEvaluationResult(
            decision=PolicyDecision.CONFIRM,
            reason=f"Restricted mode requires user confirmation for modifying tool '{tool_name}'.",
            requires_user_prompt=f"Confirm tool invocation: {tool_name}",
        )
