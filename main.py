#!/usr/bin/env python3
"""
AgentLab: Local AI Coding Harness & Dashboard
Main Application Entrypoint

Launches the complete Local AI Harness server and web dashboard with all
configurable parameters for model providers, model routing, workspace,
autonomy, sampling, and ledger persistence.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys
import threading
import time
import webbrowser
from typing import Dict, List, Optional

# Ensure the backend directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from harness.core.config import (
    AutonomyLevel,
    ExecutionConfig,
    HarnessConfig,
    ModelConfig,
    MonitoringConfig,
    ReportingConfig,
    RoutingConfig,
    SamplingConfig,
    SandboxConfig,
    WorkspaceConfig,
)
from harness.core.harness import Harness
from harness.models.factory import ModelProviderRegistry
from harness.skills.suites import (
    CodingSkillSuite,
    DebuggingSkillSuite,
    PlanningSkillSuite,
    TestingSkillSuite,
)
from harness.tools.fs import ListFilesTool, ReadFileTool, WriteFileTool
from harness.tools.git import GitTool
from harness.tools.shell import ShellTool
from harness.tools.testing import TestRunnerTool
from harness.ui.server import HarnessAPIServer


VERSION = "0.1.0"
logger = logging.getLogger("agentlab")


def build_parser() -> argparse.ArgumentParser:
    """Build and return command-line argument parser with all required parameters."""
    parser = argparse.ArgumentParser(
        prog="agentlab",
        description="AgentLab: Local AI Coding Harness & Real-time Web Dashboard",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Server & Networking
    net_group = parser.add_argument_group("Server & Network Options")
    net_group.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind the API and UI server.",
    )
    net_group.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port number to listen on.",
    )
    net_group.add_argument(
        "--open-browser",
        action="store_true",
        default=False,
        help="Automatically open the AgentLab web dashboard in the default browser on launch.",
    )

    # Model Provider & Default Model
    model_group = parser.add_argument_group("Model & Inference Options")
    model_group.add_argument(
        "--provider",
        choices=["ollama", "lmstudio"],
        default="ollama",
        help="Primary local LLM provider backend.",
    )
    model_group.add_argument(
        "--model",
        default="llama3.2",
        help="Default model identifier to use for agent reasoning.",
    )
    model_group.add_argument(
        "--provider-url",
        default=None,
        help="Custom base endpoint URL for provider (e.g. http://localhost:11434 for Ollama).",
    )

    # Skill-based Model Routing
    routing_group = parser.add_argument_group("Model Routing Options")
    routing_group.add_argument(
        "--routing",
        dest="routing",
        action="store_true",
        default=True,
        help="Enable dynamic model routing across different skills (default: enabled).",
    )
    routing_group.add_argument(
        "--no-routing",
        dest="routing",
        action="store_false",
        help="Disable dynamic model routing and use default model for all skills.",
    )
    routing_group.add_argument(
        "--planning-model",
        default=None,
        help="Specialized model for planning skill (defaults to --model).",
    )
    routing_group.add_argument(
        "--coding-model",
        default=None,
        help="Specialized model for coding skill (defaults to --model).",
    )
    routing_group.add_argument(
        "--testing-model",
        default=None,
        help="Specialized model for testing skill (defaults to --model).",
    )
    routing_group.add_argument(
        "--debugging-model",
        default=None,
        help="Specialized model for debugging skill (defaults to --model).",
    )

    # Execution & Autonomy
    exec_group = parser.add_argument_group("Execution & Autonomy Options")
    exec_group.add_argument(
        "--autonomy",
        choices=["restricted", "balanced", "autonomous"],
        default="balanced",
        help="Agent execution autonomy policy.",
    )
    exec_group.add_argument(
        "--max-duration",
        type=int,
        default=3600,
        help="Maximum execution duration timeout in seconds.",
    )
    exec_group.add_argument(
        "--max-recovery",
        type=int,
        default=2,
        help="Maximum automated self-healing recovery attempts on failure.",
    )

    # Sampling Parameters
    sample_group = parser.add_argument_group("LLM Sampling Parameters")
    sample_group.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="LLM sampling temperature (0.0 to 2.0).",
    )
    sample_group.add_argument(
        "--top-p",
        type=float,
        default=0.9,
        help="Top-p nucleus sampling probability (0.0 to 1.0).",
    )
    sample_group.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible completions.",
    )

    # Workspace & Ledger Persistence
    store_group = parser.add_argument_group("Workspace & Storage Options")
    store_group.add_argument(
        "--workspace",
        default="./workspace",
        help="Root directory where agent generates, edits, and verifies code.",
    )
    store_group.add_argument(
        "--db",
        default="./data/ledger.db",
        help="Path to SQLite database for audit event ledger and metrics.",
    )
    store_group.add_argument(
        "--sandbox",
        choices=["local", "docker"],
        default="local",
        help="Sandbox isolation runtime for command execution.",
    )
    store_group.add_argument(
        "--no-git",
        action="store_true",
        default=False,
        help="Disable automatic Git branch and checkpoint tracking in workspace.",
    )

    # General Configuration
    gen_group = parser.add_argument_group("General & Configuration")
    gen_group.add_argument(
        "--config",
        default=None,
        help="Optional path to custom YAML configuration file.",
    )
    gen_group.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Enable detailed debug-level logging.",
    )
    gen_group.add_argument(
        "--version",
        action="version",
        version=f"AgentLab v{VERSION}",
        help="Show program version and exit.",
    )

    return parser


def create_harness_config(args: argparse.Namespace) -> HarnessConfig:
    """Build unified HarnessConfig from command-line arguments and optional YAML config."""
    if args.config and Path(args.config).is_file():
        logger.info("Loading base configuration from %s", args.config)
        config = HarnessConfig.from_file(args.config)
    else:
        config = HarnessConfig()

    # Apply command-line overrides
    config.execution.autonomy = AutonomyLevel(args.autonomy)
    config.execution.max_duration_seconds = args.max_duration
    config.execution.max_recovery_attempts = args.max_recovery

    config.model.default_provider = args.provider
    config.model.default_model = args.model

    config.sampling.temperature = args.temperature
    config.sampling.top_p = args.top_p
    config.sampling.seed = args.seed

    workspace_path = Path(args.workspace).resolve()
    config.workspace.root = str(workspace_path)
    config.workspace.git_enabled = not args.no_git

    config.sandbox.runtime = args.sandbox

    # Setup routing rules
    config.routing.enabled = args.routing
    routing_rules: Dict[str, str] = {}
    if args.routing:
        if args.planning_model:
            routing_rules["planning"] = args.planning_model
        if args.coding_model:
            routing_rules["coding"] = args.coding_model
        if args.testing_model:
            routing_rules["testing"] = args.testing_model
        if args.debugging_model:
            routing_rules["debugging"] = args.debugging_model
    config.routing.rules = routing_rules

    return config


def initialize_harness(config: HarnessConfig, db_path: str, provider_url: Optional[str] = None) -> Harness:
    """Instantiate and configure the Harness with skills, tools, and model provider."""
    # Ensure workspace directory exists
    workspace_root = Path(config.workspace.root)
    workspace_root.mkdir(parents=True, exist_ok=True)

    # Ensure ledger database directory exists
    ledger_path = Path(db_path).resolve()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize standard file and execution tools
    tools = [
        WriteFileTool(workspace_root=str(workspace_root)),
        ReadFileTool(workspace_root=str(workspace_root)),
        ListFilesTool(workspace_root=str(workspace_root)),
        ShellTool(workspace_root=str(workspace_root)),
        GitTool(workspace_root=str(workspace_root)),
        TestRunnerTool(workspace_root=str(workspace_root)),
    ]

    # Initialize specialized skill suites
    skills = {
        "planning": PlanningSkillSuite(tools=tools),
        "coding": CodingSkillSuite(tools=tools),
        "testing": TestingSkillSuite(tools=tools),
        "debugging": DebuggingSkillSuite(tools=tools),
    }

    # Instantiate model provider
    provider_kwargs = {}
    if provider_url:
        provider_kwargs["base_url"] = provider_url

    try:
        model_provider = ModelProviderRegistry.create(
            config.model.default_provider,
            default_model=config.model.default_model,
            **provider_kwargs,
        )
    except Exception as ex:
        logger.warning("Could not pre-initialize model provider '%s': %s", config.model.default_provider, ex)
        model_provider = None

    # Instantiate Harness
    providers_dict = {config.model.default_provider: model_provider} if model_provider else {}
    harness = Harness(
        config=config,
        db_path=str(ledger_path),
        model_providers=providers_dict,
        skills=skills,
    )

    return harness


def print_banner(
    base_url: str,
    config: HarnessConfig,
    db_path: str,
    provider_status: str,
) -> None:
    """Print clean ASCII startup banner and configuration summary."""
    rules_summary = (
        ", ".join(f"{k} -> {v}" for k, v in config.routing.rules.items())
        if config.routing.rules
        else f"All skills -> {config.model.default_model}"
    )
    separator = "=" * 72
    banner = f"""
{separator}
  AgentLab Local AI Coding Harness & Dashboard v{VERSION}
{separator}
  Web Dashboard : {base_url}/
  REST API      : {base_url}/api/executions
  Benchmark API : {base_url}/api/benchmarks

  Provider      : {config.model.default_provider} ({provider_status})
  Default Model : {config.model.default_model}
  Model Routing : {"Enabled" if config.routing.enabled else "Disabled"} ({rules_summary})
  Autonomy Level: {config.execution.autonomy.value}
  Sampling      : temp={config.sampling.temperature}, top_p={config.sampling.top_p}, seed={config.sampling.seed}
  Workspace     : {config.workspace.root} (Git: {"enabled" if config.workspace.git_enabled else "disabled"})
  Ledger DB     : {db_path}
{separator}
  Press Ctrl+C to gracefully stop the server.
"""
    print(banner, flush=True)


def main() -> None:
    """Main CLI entrypoint to launch AgentLab."""
    parser = build_parser()
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Build configuration and initialize harness
    config = create_harness_config(args)
    harness = initialize_harness(config, args.db, args.provider_url)

    # Check provider health
    provider = harness.get_model_provider(config.model.default_provider)
    if provider:
        try:
            health = provider.health()
            if health.available:
                provider_status = f"Online, latency: {health.latency_ms:.1f}ms"
            else:
                provider_status = f"Offline ({health.message})"
        except Exception as ex:
            provider_status = f"Unreachable ({ex})"
    else:
        provider_status = "Not registered"

    # Start HTTP REST and UI Dashboard Server
    server = HarnessAPIServer(args.host, args.port, harness)

    # Print startup banner
    print_banner(
        base_url=server.base_url,
        config=config,
        db_path=args.db,
        provider_status=provider_status,
    )

    # Automatically launch browser if requested
    if args.open_browser:
        def _open():
            time.sleep(0.5)
            webbrowser.open(server.base_url)

        threading.Thread(target=_open, daemon=True).start()

    # Serve requests until interrupted
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[AgentLab] Shutting down server gracefully...")
    finally:
        server.server_close()
        print("[AgentLab] Server stopped.")


if __name__ == "__main__":
    main()
