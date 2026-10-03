"""Configuration schema and loading utilities for Local AI Harness."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from pydantic import BaseModel, Field, field_validator


class AutonomyLevel(str, Enum):
    """User autonomy levels for execution policy control."""
    RESTRICTED = "restricted"
    BALANCED = "balanced"
    AUTONOMOUS = "autonomous"


class HarnessMetaConfig(BaseModel):
    name: str = Field(default="local-coding-harness", description="Identifier name of the harness")
    version: str = Field(default="0.1", description="Harness version")


class ExecutionConfig(BaseModel):
    autonomy: AutonomyLevel = Field(default=AutonomyLevel.BALANCED, description="Autonomy level")
    max_duration_seconds: int = Field(default=3600, ge=1, description="Maximum execution timeout in seconds")
    max_recovery_attempts: int = Field(default=1, ge=0, description="Maximum automated recovery attempts")


class ModelConfig(BaseModel):
    default_provider: str = Field(default="ollama", description="Default model provider (ollama, lmstudio)")
    default_model: str = Field(default="llama3.2", description="Default model name")


class RoutingConfig(BaseModel):
    enabled: bool = Field(default=True, description="Enable dynamic model routing")
    rules: Dict[str, str] = Field(default_factory=dict, description="Phase to model routing rules")


class SamplingConfig(BaseModel):
    temperature: float = Field(default=0.2, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: float = Field(default=0.9, ge=0.0, le=1.0, description="Top-p sampling")
    seed: Optional[int] = Field(default=42, description="Random seed for reproducibility")


class WorkspaceConfig(BaseModel):
    root: str = Field(default="./workspace", description="Path to the workspace root directory")
    git_enabled: bool = Field(default=True, description="Enable Git checkpoints and rollback")


class SandboxConfig(BaseModel):
    runtime: str = Field(default="docker", description="Sandbox runtime type: docker, local, etc.")
    network: bool = Field(default=False, description="Allow network access in sandbox")


class MonitoringConfig(BaseModel):
    cpu: bool = Field(default=True, description="Monitor CPU utilization and time")
    ram: bool = Field(default=True, description="Monitor RAM utilization")
    gpu: bool = Field(default=True, description="Monitor GPU utilization")
    vram: bool = Field(default=True, description="Monitor VRAM utilization")
    power: bool = Field(default=True, description="Monitor power draw where supported")
    temperature: bool = Field(default=True, description="Monitor temperature where supported")
    interval_ms: int = Field(default=500, ge=50, description="Resource sampling interval in milliseconds")


class ReportingConfig(BaseModel):
    advanced_mode: bool = Field(default=False, description="Enable advanced telemetry and report generation")


class HarnessConfig(BaseModel):
    """Complete configuration specification for Local AI Harness."""

    harness: HarnessMetaConfig = Field(default_factory=HarnessMetaConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    reporting: ReportingConfig = Field(default_factory=ReportingConfig)

    @classmethod
    def from_yaml(cls, yaml_content: str) -> HarnessConfig:
        """Parse configuration from YAML string."""
        data = yaml.safe_load(yaml_content) or {}
        return cls.model_validate(data)

    @classmethod
    def from_file(cls, path: str | Path) -> HarnessConfig:
        """Load configuration from a YAML file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return cls.from_yaml(f.read())

    def to_yaml(self) -> str:
        """Export configuration to standard YAML string."""
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)


class ReproducibilityProfile(BaseModel):
    """Profile describing environment and parameters for audit/reproducibility."""

    seed: Optional[int] = 42
    model: Dict[str, Any] = Field(default_factory=lambda: {
        "provider": "ollama",
        "name": "llama3.2",
        "version": "unknown",
        "quantization": "unknown",
    })
    sampling: Dict[str, Any] = Field(default_factory=lambda: {
        "temperature": 0.2,
        "top_p": 0.9,
    })
    runtime: Dict[str, Any] = Field(default_factory=lambda: {
        "harness_version": "0.1",
        "python_version": "unknown",
        "os": "unknown",
        "backend_version": "unknown",
    })
    hardware: Dict[str, Any] = Field(default_factory=lambda: {
        "cpu": "unknown",
        "ram_gb": "unknown",
        "gpu": "unknown",
        "vram_gb": "unknown",
    })
    execution: Dict[str, Any] = Field(default_factory=lambda: {
        "concurrency": 1,
    })
