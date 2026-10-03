"""Model router selecting inference models based on execution phase and skill requirements."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from harness.core.config import RoutingConfig


class ModelRouter:
    """Dynamically routes inference to specialized models per execution phase."""

    def __init__(
        self,
        default_model: str = "llama3.2:latest",
        rules: Optional[Dict[str, str]] = None,
        enabled: bool = True,
    ):
        self.default_model = default_model
        self.rules: Dict[str, str] = {k.lower(): v for k, v in (rules or {}).items()}
        self.enabled = enabled
        self.routing_history: List[Dict[str, Any]] = []

    @classmethod
    def from_config(cls, routing_config: RoutingConfig, default_model: str) -> ModelRouter:
        """Create router from harness configuration."""
        return cls(
            default_model=default_model,
            rules=routing_config.rules,
            enabled=routing_config.enabled,
        )

    def set_route(self, phase_or_skill: str, model_name: str) -> None:
        """Assign a specific model to a phase or skill."""
        self.rules[phase_or_skill.lower()] = model_name

    def resolve_model(self, phase_or_skill: str) -> str:
        """Resolve which model to use for given phase or skill."""
        if not self.enabled:
            return self.default_model
        return self.rules.get(phase_or_skill.lower(), self.default_model)

    def route_for_phase(
        self,
        execution_id: str,
        phase_or_skill: str,
        current_model: str,
    ) -> Dict[str, Any]:
        """Determine if model transition is needed and record telemetry."""
        target_model = self.resolve_model(phase_or_skill)
        transitioned = target_model != current_model

        record = {
            "execution_id": execution_id,
            "phase": phase_or_skill,
            "previous_model": current_model,
            "selected_model": target_model,
            "transitioned": transitioned,
            "reason": f"Routing rule matched for '{phase_or_skill}'" if transitioned else "Default model retained",
        }
        self.routing_history.append(record)
        return record
