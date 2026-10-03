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
        workspace_manager: Optional[Any] = None,
    ):
        self.config = config or HarnessConfig()
        self.ledger = SQLiteEventLedger(db_path)
        self.policy_engine = policy_engine or DefaultPolicyEngine()

        if monitoring_manager is not None:
            self.monitoring_manager = monitoring_manager
        else:
            from harness.monitoring.manager import MonitoringManager
            self.monitoring_manager = MonitoringManager(
                on_sample=lambda sample: self._on_resource_sample(sample)
            )

        self.evaluation_engine = evaluation_engine

        if workspace_manager is not None:
            self.workspace_manager = workspace_manager
        elif self.config.workspace.git_enabled:
            from harness.workspace.manager import WorkspaceManager
            self.workspace_manager = WorkspaceManager(self.config.workspace.root)
        else:
            self.workspace_manager = None

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

    def get_model_provider(self, name: Optional[str] = None) -> Optional[IModelProvider]:
        """Get or lazily instantiate configured model provider."""
        provider_name = name or self.config.model.default_provider
        if provider_name in self.model_providers:
            return self.model_providers[provider_name]
        try:
            from harness.models.factory import ModelProviderRegistry
            provider = ModelProviderRegistry.create(
                provider_name,
                default_model=self.config.model.default_model,
            )
            self.model_providers[provider_name] = provider
            return provider
        except Exception:
            return None

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

        provider = self.get_model_provider(self.config.model.default_provider)
        manager = ExecutionManager(
            task=task_obj,
            config=self.config,
            ledger=self.ledger,
            policy_engine=self.policy_engine,
            model_provider=provider,
            workspace_manager=self.workspace_manager,
            execution_id=execution_id,
        )
        for skill in self.skills.values():
            manager.skill_manager.register_skill(skill)

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

    def _on_resource_sample(self, sample: Any) -> None:
        """Record a resource measurement event to the ledger."""
        from harness.core.events import EventType
        self.ledger.append(
            Event.create(
                execution_id=sample.execution_id,
                type=EventType.RESOURCE_SAMPLE,
                source="monitoring_manager",
                payload=sample.model_dump(),
            )
        )

    def get_live_resource_metrics(self, execution_id: str) -> Optional[Any]:
        """Fetch the latest live resource metrics sample for an active execution."""
        if not self.monitoring_manager:
            return None
        samples = self.monitoring_manager.get_samples(execution_id)
        if samples:
            return samples[-1]
        return self.monitoring_manager.sample(execution_id)

    def close(self) -> None:
        """Release database and system resources."""
        self.ledger.close()
