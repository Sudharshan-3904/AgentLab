"""UI and API Server package for Local AI Harness."""

from typing import Any

__all__ = ["APIServerManager", "HarnessAPIServer"]


def __getattr__(name: str) -> Any:
    if name in ("APIServerManager", "HarnessAPIServer"):
        from harness.ui.server import APIServerManager, HarnessAPIServer

        mapping = {
            "APIServerManager": APIServerManager,
            "HarnessAPIServer": HarnessAPIServer,
        }
        return mapping[name]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
