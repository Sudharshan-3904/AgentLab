"""Tests for harness configuration schemas and loading."""

import pytest
from pydantic import ValidationError
from harness.core.config import (
    AutonomyLevel,
    HarnessConfig,
    ReproducibilityProfile,
)


def test_default_config():
    config = HarnessConfig()
    assert config.harness.name == "local-coding-harness"
    assert config.harness.version == "0.1"
    assert config.execution.autonomy == AutonomyLevel.BALANCED
    assert config.execution.max_duration_seconds == 3600
    assert config.execution.max_recovery_attempts == 1
    assert config.model.default_provider == "ollama"
    assert config.model.default_model == "llama3.2:latest"
    assert config.routing.enabled is True
    assert config.sampling.temperature == 0.2
    assert config.sampling.top_p == 0.9
    assert config.sampling.seed == 42
    assert config.workspace.git_enabled is True
    assert config.sandbox.runtime == "docker"
    assert config.sandbox.network is False
    assert config.monitoring.cpu is True
    assert config.monitoring.interval_ms == 500
    assert config.reporting.advanced_mode is False


def test_load_from_yaml_string():
    yaml_data = """
harness:
  name: test-harness
  version: "0.2"
execution:
  autonomy: autonomous
  max_duration_seconds: 1800
  max_recovery_attempts: 2
model:
  default_provider: lmstudio
  default_model: qwen2.5-coder
sampling:
  temperature: 0.5
  top_p: 0.95
  seed: 123
"""
    config = HarnessConfig.from_yaml(yaml_data)
    assert config.harness.name == "test-harness"
    assert config.execution.autonomy == AutonomyLevel.AUTONOMOUS
    assert config.execution.max_duration_seconds == 1800
    assert config.execution.max_recovery_attempts == 2
    assert config.model.default_provider == "lmstudio"
    assert config.model.default_model == "qwen2.5-coder"
    assert config.sampling.temperature == 0.5
    assert config.sampling.seed == 123


def test_to_yaml_and_roundtrip():
    config = HarnessConfig()
    yaml_str = config.to_yaml()
    reloaded = HarnessConfig.from_yaml(yaml_str)
    assert reloaded.harness.name == config.harness.name
    assert reloaded.execution.autonomy == config.execution.autonomy
    assert reloaded.model.default_provider == config.model.default_provider


def test_config_validation_errors():
    # Invalid autonomy
    with pytest.raises(ValidationError):
        HarnessConfig.from_yaml("execution:\n  autonomy: hyper_drive")

    # Invalid temperature > 2.0
    with pytest.raises(ValidationError):
        HarnessConfig.from_yaml("sampling:\n  temperature: 3.5")

    # Invalid interval_ms < 50
    with pytest.raises(ValidationError):
        HarnessConfig.from_yaml("monitoring:\n  interval_ms: 10")


def test_reproducibility_profile():
    profile = ReproducibilityProfile(seed=999)
    assert profile.seed == 999
    assert profile.model["provider"] == "ollama"
    assert profile.sampling["temperature"] == 0.2
    assert profile.execution["concurrency"] == 1
