"""Top-level Harness object unifying execution, configuration, and observability."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.core.config import HarnessConfig
from harness.core.events import Event
from harness.core.interfaces import (
    EvaluationSummary,
    IEvaluationEngine,
    IMonitoringManager,
    IModelProvider,
    IPolicyEngine,
    ISkillSuite,
    ITool,
)
from harness.execution.manager import ExecutionManager
from harness.ledger.sqlite import SQLiteEventLedger
from harness.tasks.task import Task


class DefaultPolicyEngine(IPolicyEngine):
    """Default permissive policy for balanced/autonomous modes."""

    def evaluate(self, context) -> Any:
        from harness.core.interfaces import PolicyDecision, PolicyEvaluationResult
        return PolicyEvaluationResult(
            decision=PolicyDecision.ALLOW,
            reason="Default policy permits action",
        )


class Harness:
    """The central Local AI Harness orchestrator."""

    def __init__(
        self,
        config: Optional[HarnessConfig] = None,
        db_path: str = ":memory:",
        model_providers: Optional[Dict[str, IModelProvider]] = None,
        skills: Optional[Dict[str, ISkillSuite]] = None,
        tools: Optional[Dict[str, ITool]] = None,
        policy_engine: Optional[IPolicyEngine] = None,
        monitoring_manager: Optional[IMonitoringManager] = None,
        evaluation_engine: Optional[IEvaluationEngine] = None,
    ):
        self.config = config or HarnessConfig()
        self.ledger = SQLiteEventLedger(db_path)
        self.policy_engine = policy_engine or DefaultPolicyEngine()
        self.monitoring_manager = monitoring_manager
        self.evaluation_engine = evaluation_engine

        self.model_providers: Dict[str, IModelProvider] = model_providers or {}
        self.skills: Dict[str, ISkillSuite] = skills or {}
        self.tools: Dict[str, ITool] = tools or {}

        self.executions: Dict[str, ExecutionManager] = {}

    @classmethod
    def from_yaml_file(cls, path: str | Path, db_path: str = ":memory:", **kwargs) -> Harness:
        """Instantiate harness from a YAML configuration file."""
        config = HarnessConfig.from_file(path)
        return cls(config=config, db_path=db_path, **kwargs)

    @classmethod
    def from_yaml_str(cls, yaml_content: str, db_path: str = ":memory:", **kwargs) -> Harness:
        """Instantiate harness from a YAML string."""
        config = HarnessConfig.from_yaml(yaml_content)
        return cls(config=config, db_path=db_path, **kwargs)

    def register_model_provider(self, name: str, provider: IModelProvider) -> None:
        """Register a model inference provider backend."""
        self.model_providers[name] = provider

    def register_skill(self, skill: ISkillSuite) -> None:
        """Register a behavioral skill suite."""
        self.skills[skill.name] = skill

    def register_tool(self, tool: ITool) -> None:
        """Register an executable tool."""
        self.tools[tool.name] = tool

    def create_execution(
        self,
        task: Task | str,
        execution_id: Optional[str] = None,
    ) -> ExecutionManager:
        """Create and track a new logical agent execution."""
        task_obj = Task.from_prompt(task) if isinstance(task, str) else task

        provider = self.model_providers.get(self.config.model.default_provider)
        manager = ExecutionManager(
            task=task_obj,
            config=self.config,
            ledger=self.ledger,
            policy_engine=self.policy_engine,
            model_provider=provider,
            execution_id=execution_id,
        )
        self.executions[manager.execution_id] = manager
        return manager

    def get_execution(self, execution_id: str) -> Optional[ExecutionManager]:
        """Lookup an active execution by identifier."""
        return self.executions.get(execution_id)

    def list_executions(self) -> List[str]:
        """List all tracked execution IDs."""
        return list(self.executions.keys())

    def get_events(self, execution_id: str) -> List[Event]:
        """Fetch all ledger events for an execution."""
        return self.ledger.get_events(execution_id)

    def export_execution_jsonl(self, execution_id: str, file_path: str | Path) -> int:
        """Export execution ledger stream to JSONL file."""
        return self.ledger.export_jsonl(execution_id, file_path)

    def evaluate_execution(self, execution_id: str) -> Optional[EvaluationSummary]:
        """Compute evaluation metrics for an execution if evaluation engine is configured."""
        if not self.evaluation_engine:
            return None

        manager = self.executions.get(execution_id)
        events = self.ledger.get_events(execution_id)
        samples = manager.resource_samples if manager else []
        model_calls = manager.model_call_records if manager else []
        tool_responses = manager.tool_responses if manager else []

        return self.evaluation_engine.evaluate(
            execution_id=execution_id,
            events=events,
            resource_samples=samples,
            model_calls=model_calls,
            tool_responses=tool_responses,
        )

    def close(self) -> None:
        """Release database and system resources."""
        self.ledger.close()
